from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession

OidcAuthorizationPurpose = Literal["login", "account_deletion_reauth"]


@dataclass(frozen=True)
class OidcAuthorizationRequest:
    provider_id: str
    state: str
    nonce: str
    code_challenge: str
    prompt: str | None = None
    max_age: int | None = None
    login_hint: str | None = None


@dataclass(frozen=True)
class OidcAuthorizationUrl:
    provider_id: str
    url: str


@dataclass(frozen=True)
class OidcAuthorizationStartResult:
    provider_id: str
    authorization_url: str
    browser_binding_cookie_name: str
    browser_binding_cookie_value: str
    browser_binding_cookie_max_age: int


@dataclass(frozen=True)
class OidcCallbackInput:
    provider_id: str
    code: str
    state: str


@dataclass(frozen=True)
class OidcTokenSetForValidation:
    id_token: str


@dataclass(frozen=True)
class OidcVerifiedClaims:
    provider_id: str
    issuer: str
    audience: str
    subject: str
    email: str | None
    email_verified: bool
    issued_at: datetime
    expires_at: datetime
    auth_time: datetime | None
    claims_json: dict


@dataclass(frozen=True)
class OidcCallbackResult:
    redirect_path: str
    issued_session: IssuedAuthSession | None = None
    reauthenticated_context: AuthenticatedSessionContext | None = None
