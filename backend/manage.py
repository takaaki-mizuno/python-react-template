from pathlib import Path

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

from app.config.database import get_database_settings

app = typer.Typer()
ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(ALEMBIC_INI))


@app.command()
def serve(host: str = "0.0.0.0", port: str = "8000"):
    import uvicorn

    uvicorn.run(app="app.main:app", host=host, port=int(port), reload=True)


@app.command("db-upgrade")
def db_upgrade(revision: str = "head"):
    alembic_command.upgrade(_alembic_config(), revision)


@app.command("db-downgrade")
def db_downgrade(revision: str = typer.Argument(...)):
    alembic_command.downgrade(_alembic_config(), revision)


@app.command("db-check")
def db_check():
    settings = get_database_settings()
    if "ALEMBIC_DATABASE_URL" not in settings.model_fields_set:
        typer.secho(
            "ALEMBIC_DATABASE_URL must be configured explicitly for db-check.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    typer.secho(
        f"Checking database: {_format_database_target(settings.ALEMBIC_DATABASE_URL)}",
        err=True,
    )
    alembic_command.check(_alembic_config())


def _format_database_target(database_url: str) -> str:
    url = make_url(database_url)
    if url.host:
        port = f":{url.port}" if url.port else ""
        database = f"/{url.database}" if url.database else ""
        return f"{url.drivername}://{url.host}{port}{database}"
    return f"{url.drivername}:{url.database or ''}"


@app.command()
def version():
    print("Version: 1.0.0")


if __name__ == "__main__":
    app()
