from starlette.responses import Response

from app.config.auth import AuthSettings

SESSION_COOKIE_BASE_NAME = "session_token"
CSRF_COOKIE_NAME = "csrf_token"


def session_cookie_name(settings: AuthSettings) -> str:
    return f"{settings.AUTH_SESSION_COOKIE_PREFIX}{SESSION_COOKIE_BASE_NAME}"


def csrf_cookie_name() -> str:
    return CSRF_COOKIE_NAME


def set_auth_cookie(
    response: Response,
    key: str,
    value: str,
    httponly: bool,
    secure: bool,
    max_age_seconds: int,
) -> None:
    _validate_host_prefix(key=key, secure=secure)
    response.set_cookie(
        key=key,
        value=value,
        httponly=httponly,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age_seconds,
    )


def clear_auth_cookie(
    response: Response,
    key: str,
    httponly: bool,
    secure: bool,
) -> None:
    _validate_host_prefix(key=key, secure=secure)
    response.set_cookie(
        key=key,
        value="",
        httponly=httponly,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=0,
    )


def _validate_host_prefix(key: str, secure: bool) -> None:
    if key.startswith("__Host-") and not secure:
        raise ValueError("__Host- cookies must use Secure=True, Path=/, and no Domain.")
