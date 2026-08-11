from datetime import datetime, timedelta

from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.libraries.clock import utcnow
from app.libraries.session_tokens import generate_token, hash_token
from app.models.auth_session import AuthSession
from app.models.user import User


def calculate_session_expiry(
    auth_settings: AuthSettings,
    issued_at: datetime,
    last_seen_at: datetime,
) -> datetime:
    absolute_expires_at = issued_at + timedelta(
        seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS, )
    idle_expires_at = last_seen_at + timedelta(
        seconds=auth_settings.AUTH_SESSION_IDLE_TTL_SECONDS, )
    return min(absolute_expires_at, idle_expires_at)


async def replace_auth_session(
    auth_repository: AuthRepositoryInterface,
    auth_settings: AuthSettings,
    user: User,
    current_session_token: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[AuthSession, str, str]:
    if current_session_token:
        existing_session = await auth_repository.find_active_session_by_token_hash(
            hash_token(current_session_token), )
        if existing_session:
            await auth_repository.revoke_session(existing_session.id)

    session_token = generate_token()
    csrf_token = generate_token()
    issued_at = utcnow()
    expires_at = calculate_session_expiry(auth_settings, issued_at, issued_at)
    session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        issued_at=issued_at,
        last_seen_at=issued_at,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return session, session_token, csrf_token
