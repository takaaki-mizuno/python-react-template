from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.controllers.auth_controller import router as auth_router
from app.controllers.healthz_controller import router as healthz_router
from app.controllers.sample_controller import router as sample_router
from app.models.status import Status


def setup_routes(app: FastAPI) -> FastAPI:
    app = _setup_api_routes(app)
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    return app


def _setup_api_routes(app: FastAPI) -> FastAPI:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(healthz_router)
    router.include_router(sample_router)
    app.include_router(router, prefix="/api")
    return app
