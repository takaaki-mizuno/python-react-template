import typer

app = typer.Typer()


@app.command()
def serve(host: str = "0.0.0.0", port: str = "8000"):
    import uvicorn

    uvicorn.run(app="app.main:app", host=host, port=int(port), reload=True)


@app.command()
def db_upgrade(revision: str = "head"):
    from alembic import command
    from alembic.config import Config

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, revision)


@app.command()
def db_downgrade(revision: str = "base"):
    from alembic import command
    from alembic.config import Config

    alembic_config = Config("alembic.ini")
    command.downgrade(alembic_config, revision)


@app.command()
def version():
    print("Version: 1.0.0")


if __name__ == "__main__":
    app()
