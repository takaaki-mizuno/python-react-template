from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .container import build_container
from .route import setup_routes


def create_app(environment: str = 'local'):
    injector = build_container()
    app = FastAPI(title="Fast API Template", )
    app.state.injector = injector
    app = setup_routes(app)

    return app
