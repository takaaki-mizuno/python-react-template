from datetime import timedelta
from uuid import uuid4

import pytest

from app.config.auth import AuthSettings
from app.libraries.auth_session_issuer import calculate_session_expiry, replace_auth_session
from app.libraries.clock import utcnow
from app.models.auth_session import AuthSession
from app.models.user import User


class AuthRepositoryStub:

    def __init__(self) -> None:
        self.active_session: AuthSession | None = None
        self.revoked_session_ids: list = []
        self.created_sessions: list[AuthSession] = []

    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        del token_hash
        return self.active_session

    async def revoke_session(self, session_id) -> None:
        self.revoked_session_ids.append(session_id)

    async def create_session(self, **kwargs) -> AuthSession:
        session = AuthSession(**kwargs)
        self.created_sessions.append(session)
        return session


def test_calculate_session_expiry_uses_earlier_of_absolute_and_idle_ttl() -> None:
    auth_settings = AuthSettings(
        _env_file=None,
        AUTH_SESSION_ABSOLUTE_TTL_SECONDS=3600,
        AUTH_SESSION_IDLE_TTL_SECONDS=300,
    )
    issued_at = utcnow()

    assert calculate_session_expiry(auth_settings, issued_at,
                                    issued_at) == (issued_at + timedelta(seconds=300))


@pytest.mark.asyncio
async def test_replace_auth_session_revokes_existing_session_and_creates_new_session() -> None:
    auth_settings = AuthSettings(_env_file=None)
    repository = AuthRepositoryStub()
    existing_session = AuthSession(
        id=uuid4(),
        user_id=uuid4(),
        session_token_hash="old-session-hash",
        csrf_token_hash="old-csrf-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository.active_session = existing_session
    user = User(id=uuid4(), email="user@example.com", password_hash="hash")

    session, session_token, csrf_token = await replace_auth_session(
        repository,
        auth_settings,
        user,
        current_session_token="old-session-token",
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert repository.revoked_session_ids == [existing_session.id]
    assert repository.created_sessions == [session]
    assert session.user_id == user.id
    assert session_token
    assert csrf_token
    assert session.ip_address == "127.0.0.1"
    assert session.user_agent == "test-agent"
