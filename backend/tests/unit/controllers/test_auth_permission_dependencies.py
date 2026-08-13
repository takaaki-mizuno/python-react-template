from datetime import timedelta
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.error_handlers import register_error_handlers
from app.controllers import auth_dependencies
from app.controllers.auth_dependencies import require_any_permission, require_permission
from app.libraries.clock import utcnow
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_session import AuthSession
from app.models.user import User

require_admin_access = require_permission("admin:access")


def test_require_permission_allows_context_with_permission() -> None:
    app = _app_with_permission("admin:access")
    client = TestClient(app)

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_require_permission_rejects_context_without_permission() -> None:
    app = _app_with_permission()
    client = TestClient(app)

    response = client.get("/protected")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_require_any_permission_allows_any_matching_permission() -> None:
    app = _app_with_any_permission("users:read")
    client = TestClient(app)

    response = client.get("/protected")

    assert response.status_code == 200


def test_require_any_permission_rejects_empty_permission_set() -> None:
    try:
        require_any_permission(set())
    except ValueError as error:
        assert "permission_codes" in str(error)
    else:
        raise AssertionError("require_any_permission should reject empty permission set")


def _app_with_permission(*permissions: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/protected")
    async def protected(
            _auth_context: AuthenticatedSessionContext = Depends(require_admin_access), ):
        return {"ok": True}

    app.dependency_overrides[
        auth_dependencies.require_current_session] = lambda: _context(permissions)
    return app


def _app_with_any_permission(*permissions: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    require_read_or_admin = require_any_permission({"users:read", "admin:access"})

    @app.get("/protected")
    async def protected(
            _auth_context: AuthenticatedSessionContext = Depends(require_read_or_admin), ):
        return {"ok": True}

    app.dependency_overrides[
        auth_dependencies.require_current_session] = lambda: _context(permissions)
    return app


def _context(permissions: tuple[str, ...]) -> AuthenticatedSessionContext:
    user = User(id=uuid4(), email="user@example.com", password_hash="hash")
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset({"admin"}) if permissions else frozenset(),
        permissions=frozenset(permissions),
    )
