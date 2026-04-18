import typer

app = typer.Typer()

@app.command()
def serve(host: str = '0.0.0.0', port: str = '8000'):
    import uvicorn
    uvicorn.run(app='app.main:app',
                host=host,
                port=int(port),
                reload=True)


@app.command()
def version():
    print('Version: 1.0.0')


if __name__ == "__main__":
    app()