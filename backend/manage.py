import asyncio
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from injector import Injector
from sqlalchemy.engine import make_url

from app.bootstrap.cli import run_with_container
from app.config import get_config
from app.config.database import DatabaseSettings, get_alembic_database_url, get_database_settings
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface

app = typer.Typer()
BACKEND_DIR = Path(__file__).resolve().parent
PYPROJECT_TOML = BACKEND_DIR / "pyproject.toml"
ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(ALEMBIC_INI))


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
    reload: Annotated[
        bool | None,
        typer.Option("--reload/--no-reload", help="Enable or disable uvicorn reload."),
    ] = None,
    workers: Annotated[int, typer.Option(min=1, help="Number of uvicorn worker processes.")] = 1,
    log_level: Annotated[str, typer.Option(help="Uvicorn log level.")] = "info",
) -> None:
    import uvicorn

    effective_reload = _default_reload() if reload is None else reload
    if effective_reload and workers > 1:
        typer.secho(
            "--reload cannot be used with --workers greater than 1.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    uvicorn.run(
        app="app.main:app",
        host=host,
        port=port,
        reload=effective_reload,
        workers=workers,
        log_level=log_level,
    )


def _default_reload() -> bool:
    return get_config().ENVIRONMENT.lower() in {"local", "development"}


@app.command("db-upgrade")
def db_upgrade(revision: str = "head") -> None:
    _get_explicit_database_settings("db-upgrade")
    alembic_command.upgrade(_alembic_config(), revision)


@app.command("db-downgrade")
def db_downgrade(
    revision: Annotated[
        str,
        typer.Option("--revision", "-r", help="Target Alembic revision to downgrade to."),
    ],
) -> None:
    _get_explicit_database_settings("db-downgrade")
    alembic_command.downgrade(_alembic_config(), revision)


@app.command("db-check")
def db_check() -> None:
    settings = _get_explicit_database_settings("db-check")
    typer.secho(
        f"Checking database: {_format_database_target(get_alembic_database_url(settings))}",
        err=True,
    )
    alembic_command.check(_alembic_config())


@app.command("db-revision")
def db_revision(
    message: Annotated[str, typer.Option("--message", "-m", help="Revision message.")],
    autogenerate: Annotated[bool,
                            typer.Option(
                                help="Populate migration script from metadata diff.")] = False,
    rev_id: Annotated[str | None,
                      typer.Option("--rev-id", help="Explicit revision id.")] = None,
) -> None:
    _get_explicit_database_settings("db-revision")
    config = _alembic_config()
    if autogenerate:
        _ensure_database_is_at_head(config)
    alembic_command.revision(config, message=message, autogenerate=autogenerate, rev_id=rev_id)


@app.command("db-prune-auth")
def db_prune_auth(
    expired_sessions_before: Annotated[
        str | None,
        typer.Option(help="Delete auth sessions with expires_at before this timestamp."),
    ] = None,
    audit_logs_before: Annotated[
        str | None,
        typer.Option(help="Delete auth audit logs with created_at before this timestamp."),
    ] = None,
    oidc_states_before: Annotated[
        str | None,
        typer.Option(
            help="Delete OIDC authorization states with expires_at before this timestamp."),
    ] = None,
) -> None:
    if expired_sessions_before is None and audit_logs_before is None and oidc_states_before is None:
        typer.secho(
            "Specify at least one of --expired-sessions-before, --audit-logs-before, "
            "or --oidc-states-before.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    expired_sessions_before_at = _parse_cli_datetime(
        expired_sessions_before,
        "--expired-sessions-before",
    )
    audit_logs_before_at = _parse_cli_datetime(audit_logs_before, "--audit-logs-before")
    oidc_states_before_at = _parse_cli_datetime(oidc_states_before, "--oidc-states-before")
    _get_explicit_database_settings("db-prune-auth")

    async def operation(container: Injector) -> None:
        repository = container.get(AuthRepositoryInterface)
        if audit_logs_before_at is not None:
            deleted_logs = await repository.delete_audit_logs_created_before(audit_logs_before_at)
            typer.echo(f"Deleted audit logs: {deleted_logs}")
        if expired_sessions_before_at is not None:
            deleted_sessions = await repository.delete_sessions_expired_before(
                expired_sessions_before_at)
            typer.echo(f"Deleted expired sessions: {deleted_sessions}")
        if oidc_states_before_at is not None:
            deleted_oidc_states = await repository.delete_oidc_states_expired_before(
                oidc_states_before_at)
            typer.echo(f"Deleted OIDC authorization states: {deleted_oidc_states}")

    asyncio.run(run_with_container(operation))


def _parse_cli_datetime(value: str | None, option_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed_value = datetime.fromisoformat(value)
    except ValueError as exc:
        typer.secho(
            f"{option_name} must be an ISO 8601 datetime.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2) from exc
    if parsed_value.tzinfo is None or parsed_value.utcoffset() is None:
        typer.secho(
            f"{option_name} must include a timezone offset.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    return parsed_value


def _get_explicit_database_settings(command_name: str) -> DatabaseSettings:
    settings = get_database_settings()
    if "DATABASE_URL" not in settings.model_fields_set:
        typer.secho(
            f"DATABASE_URL must be configured explicitly for {command_name}.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    try:
        get_alembic_database_url(settings)
    except ValueError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    return settings


def _ensure_database_is_at_head(config: AlembicConfig) -> None:
    alembic_command.current(config, check_heads=True)


def _format_database_target(database_url: str) -> str:
    url = make_url(database_url)
    if url.host:
        port = f":{url.port}" if url.port else ""
        database = f"/{url.database}" if url.database else ""
        return f"{url.drivername}://{url.host}{port}{database}"
    return f"{url.drivername}:{url.database or ''}"


@app.command()
def version() -> None:
    project = tomllib.loads(PYPROJECT_TOML.read_text(encoding="utf-8"))
    print(f"Version: {project['project']['version']}")


if __name__ == "__main__":
    app()
