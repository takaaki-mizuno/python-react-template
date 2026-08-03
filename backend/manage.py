import tomllib
from pathlib import Path
from typing import Annotated

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

from app.config import get_config
from app.config.database import DatabaseSettings, get_database_settings

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
    alembic_command.upgrade(_alembic_config(), revision)


@app.command("db-downgrade")
def db_downgrade(revision: str = typer.Argument(...)) -> None:
    alembic_command.downgrade(_alembic_config(), revision)


@app.command("db-check")
def db_check() -> None:
    settings = _get_explicit_database_settings("db-check")
    typer.secho(
        f"Checking database: {_format_database_target(settings.ALEMBIC_DATABASE_URL)}",
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


def _get_explicit_database_settings(command_name: str) -> DatabaseSettings:
    settings = get_database_settings()
    if "ALEMBIC_DATABASE_URL" not in settings.model_fields_set:
        typer.secho(
            f"ALEMBIC_DATABASE_URL must be configured explicitly for {command_name}.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
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
