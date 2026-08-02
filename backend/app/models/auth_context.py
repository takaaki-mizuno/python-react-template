from dataclasses import dataclass

from app.models.auth_session import AuthSession
from app.models.user import User


@dataclass(slots=True)
class AuthenticatedSessionContext:
    user: User
    session: AuthSession


@dataclass(slots=True)
class IssuedAuthSession:
    user: User
    session: AuthSession
    session_token: str
    csrf_token: str
