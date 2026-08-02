import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.controllers.auth_controller import router as auth_router
from app.controllers.healthz_controller import router as healthz_router
from app.controllers.sample_controller import router as sample_router

logger = logging.getLogger(__name__)
API_PREFIX = "/api"
STATIC_DIRECTORY = Path(__file__).resolve().parents[2] / "static"
_STATIC_API_PREFIX = API_PREFIX.strip("/").lower()
_RESERVED_BACKEND_PATHS = {"docs", "redoc", "openapi.json"}
_STATIC_ASSET_EXTENSIONS = {
    ".avif",
    ".css",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".otf",
    ".pdf",
    ".png",
    ".svg",
    ".ttf",
    ".txt",
    ".wasm",
    ".webmanifest",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
}


class SPAStaticFiles(StaticFiles):

    async def get_response(self, path: str, scope: Scope) -> Response:
        if _is_api_path(path) or _is_reserved_backend_path(path):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or not _is_spa_navigation(path, scope):
                raise
            return await super().get_response("index.html", scope)


def setup_routes(
    app: FastAPI,
    static_directory: Path | None = None,
) -> FastAPI:
    app = _setup_api_routes(app)
    directory = static_directory or STATIC_DIRECTORY
    index_file = directory / "index.html"
    if not index_file.exists():
        logger.warning(
            "Static index.html does not exist; skipping SPA mount: %s",
            index_file,
        )
        return app
    app.mount("/",
              SPAStaticFiles(directory=directory, html=True),
              name="static")
    return app


def _setup_api_routes(app: FastAPI) -> FastAPI:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(healthz_router)
    router.include_router(sample_router)
    app.include_router(router, prefix=API_PREFIX)
    return app


def _is_api_path(path: str) -> bool:
    normalized_path = path.strip("/").lower()
    return (normalized_path == _STATIC_API_PREFIX
            or normalized_path.startswith(f"{_STATIC_API_PREFIX}/"))


def _is_reserved_backend_path(path: str) -> bool:
    return path.strip("/").lower() in _RESERVED_BACKEND_PATHS


def _is_spa_navigation(path: str, scope: Scope) -> bool:
    if scope["method"] not in {"GET", "HEAD"}:
        return False
    if _is_static_asset_path(path):
        return False
    accept = Headers(scope=scope).get("accept", "")
    normalized_accept = accept.lower()
    return "text/html" in normalized_accept or "*/*" in normalized_accept


def _is_static_asset_path(path: str) -> bool:
    normalized_path = path.strip("/").lower()
    if normalized_path == "assets" or normalized_path.startswith("assets/"):
        return True
    return any(
        normalized_path.endswith(extension)
        for extension in _STATIC_ASSET_EXTENSIONS)
