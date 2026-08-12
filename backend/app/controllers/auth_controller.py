from logging import Logger
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.config.oidc import OidcSettings
from app.controllers.auth_dependencies import (get_account_deletion_usecase, get_auth_settings,
                                               get_auth_usecase, get_client_ip, get_logger,
                                               get_oauth_oidc_usecase, get_oidc_settings,
                                               get_user_agent, require_current_session)
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.libraries.auth_cookies import (clear_auth_cookie, csrf_cookie_name, session_cookie_name,
                                        set_auth_cookie)
from app.libraries.session_tokens import hash_token
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (AccountDeletionConfirmationMismatchError,
                                    AccountDeletionInvalidPasswordError,
                                    AccountDeletionOidcReauthRequiredError,
                                    AccountDeletionReauthRequiredError, EmailAlreadyRegisteredError,
                                    InvalidCredentialsError, RateLimitExceededError,
                                    WeakPasswordError)
from app.models.auth_schemas import (AccountDeletionRequest, AuthUserResponse, CsrfTokenResponse,
                                     LoginRequest, RegisterRequest, UpdateAuthUserRequest)
from app.models.error import ErrorResponse
from app.models.language import DEFAULT_LANGUAGE_CODE, is_supported_language_code
# yapf: disable
from app.models.oidc_errors import (OidcAuthorizationRateLimitedError,
                                    OidcBrowserBindingMismatchError, OidcCallbackFlowError,
                                    OidcClaimsValidationError, OidcEmailNotVerifiedError,
                                    OidcIdentityLinkDisabledError, OidcIdentityLinkRequiredError,
                                    OidcIdentityUnavailableError, OidcProviderAccessDeniedError,
                                    OidcProviderMetadataError, OidcProviderNotConfiguredError,
                                    OidcProviderUnavailableError, OidcProvisioningDisabledError,
                                    OidcReauthAuthenticationRequiredError,
                                    OidcReauthAuthTimeRequiredError, OidcReauthStaleError,
                                    OidcReauthSubjectMismatchError, OidcStateMismatchError,
                                    OidcTokenExchangeError)
from app.models.user import AuthUserUpdateChanges

# yapf: enable

router = APIRouter(prefix="/auth", tags=["auth"])

ErrorResponses = dict[int | str, dict[str, Any]]

ME_ERROR_RESPONSES: ErrorResponses = {
    401: {
        "model": ErrorResponse
    },
}
REGISTER_ERROR_RESPONSES: ErrorResponses = {
    403: {
        "model": ErrorResponse
    },
    409: {
        "model": ErrorResponse
    },
    422: {
        "model": ErrorResponse
    },
    429: {
        "model": ErrorResponse
    },
}
LOGIN_ERROR_RESPONSES: ErrorResponses = {
    401: {
        "model": ErrorResponse
    },
    403: {
        "model": ErrorResponse
    },
    422: {
        "model": ErrorResponse
    },
    429: {
        "model": ErrorResponse
    },
}
LOGOUT_ERROR_RESPONSES: ErrorResponses = {
    403: {
        "model": ErrorResponse
    },
}
DELETE_ACCOUNT_ERROR_RESPONSES: ErrorResponses = {
    400: {
        "model": ErrorResponse
    },
    401: {
        "model": ErrorResponse
    },
    403: {
        "model": ErrorResponse
    },
    422: {
        "model": ErrorResponse
    },
    429: {
        "model": ErrorResponse
    },
}


def is_secure_request(
    request: Request,
    auth_settings: AuthSettings,
) -> bool:
    if auth_settings.AUTH_COOKIE_SECURE is not None:
        return auth_settings.AUTH_COOKIE_SECURE
    return True


def set_session_cookie(
    response: Response,
    session_token: str,
    secure: bool,
    max_age_seconds: int,
    auth_settings: AuthSettings,
) -> None:
    set_auth_cookie(
        response,
        key=session_cookie_name(auth_settings),
        value=session_token,
        httponly=True,
        secure=secure,
        max_age_seconds=max_age_seconds,
    )


def set_csrf_cookie(
    response: Response,
    csrf_token: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    set_auth_cookie(
        response,
        key=csrf_cookie_name(),
        value=csrf_token,
        httponly=False,
        secure=secure,
        max_age_seconds=max_age_seconds,
    )


def clear_session_cookie(
    response: Response,
    secure: bool,
    auth_settings: AuthSettings,
) -> None:
    clear_auth_cookie(
        response,
        key=session_cookie_name(auth_settings),
        httponly=True,
        secure=secure,
    )


def clear_csrf_cookie(response: Response, secure: bool) -> None:
    clear_auth_cookie(
        response,
        key=csrf_cookie_name(),
        httponly=False,
        secure=secure,
    )


def oidc_binding_cookie_name_for_state(state: str) -> str:
    return f"oidc_binding_{hash_token(state)[:16]}"


def set_oidc_binding_cookie(
    response: Response,
    key: str,
    value: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    set_auth_cookie(
        response,
        key=key,
        value=value,
        httponly=True,
        secure=secure,
        max_age_seconds=max_age_seconds,
    )


def clear_oidc_binding_cookie(response: Response, key: str, secure: bool) -> None:
    clear_auth_cookie(
        response,
        key=key,
        httponly=True,
        secure=secure,
    )


def merge_redirect_query(redirect_path: str, **updates: str | None) -> str:
    parsed = urlparse(redirect_path)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in updates.items():
        if value is None:
            query_items.pop(key, None)
        else:
            query_items[key] = value
    return urlunparse((
        "",
        "",
        parsed.path or "/",
        "",
        urlencode(query_items),
        parsed.fragment,
    ))


OIDC_KNOWN_ERRORS = (
    OidcProviderNotConfiguredError,
    OidcAuthorizationRateLimitedError,
    OidcStateMismatchError,
    OidcBrowserBindingMismatchError,
    OidcTokenExchangeError,
    OidcProviderAccessDeniedError,
    OidcClaimsValidationError,
    OidcEmailNotVerifiedError,
    OidcProvisioningDisabledError,
    OidcIdentityLinkRequiredError,
    OidcIdentityLinkDisabledError,
    OidcIdentityUnavailableError,
    OidcReauthAuthenticationRequiredError,
    OidcReauthSubjectMismatchError,
    OidcReauthAuthTimeRequiredError,
    OidcReauthStaleError,
    OidcProviderUnavailableError,
    OidcProviderMetadataError,
)


def oidc_redirect(redirect_path: str) -> RedirectResponse:
    return RedirectResponse(redirect_path, status_code=303)


def oidc_start_failure_redirect(redirect_path: str, error: Exception) -> RedirectResponse:
    return RedirectResponse(
        merge_redirect_query(
            redirect_path,
            oidcError=oidc_error_code_for_exception(error),
            oidcReauth=None,
        ),
        status_code=303,
    )


def unwrap_oidc_error(error: Exception) -> Exception:
    if isinstance(error, OidcCallbackFlowError):
        return error.error
    return error


def is_known_oidc_error(error: Exception) -> bool:
    return isinstance(unwrap_oidc_error(error), OIDC_KNOWN_ERRORS)


def oidc_error_code_for_exception(error: Exception) -> str:
    mapping: dict[type[Exception], str] = {
        OidcProviderNotConfiguredError: "OIDC_PROVIDER_NOT_CONFIGURED",
        OidcAuthorizationRateLimitedError: "OIDC_AUTHORIZATION_RATE_LIMITED",
        OidcStateMismatchError: "OIDC_STATE_MISMATCH",
        OidcBrowserBindingMismatchError: "OIDC_BROWSER_BINDING_MISMATCH",
        OidcTokenExchangeError: "OIDC_TOKEN_EXCHANGE_FAILED",
        OidcProviderAccessDeniedError: "OIDC_PROVIDER_ACCESS_DENIED",
        OidcClaimsValidationError: "OIDC_CLAIMS_VALIDATION_FAILED",
        OidcEmailNotVerifiedError: "OIDC_EMAIL_NOT_VERIFIED",
        OidcProvisioningDisabledError: "OIDC_PROVISIONING_DISABLED",
        OidcIdentityLinkRequiredError: "OIDC_IDENTITY_LINK_REQUIRED",
        OidcIdentityLinkDisabledError: "OIDC_IDENTITY_LINK_DISABLED",
        OidcIdentityUnavailableError: "OIDC_IDENTITY_UNAVAILABLE",
        OidcReauthAuthenticationRequiredError: "OIDC_REAUTH_AUTHENTICATION_REQUIRED",
        OidcReauthSubjectMismatchError: "OIDC_REAUTH_SUBJECT_MISMATCH",
        OidcReauthAuthTimeRequiredError: "OIDC_REAUTH_AUTH_TIME_REQUIRED",
        OidcReauthStaleError: "OIDC_REAUTH_STALE",
        OidcProviderUnavailableError: "OIDC_PROVIDER_UNAVAILABLE",
        OidcProviderMetadataError: "OIDC_PROVIDER_METADATA_INVALID",
    }
    for error_type, code in mapping.items():
        if isinstance(unwrap_oidc_error(error), error_type):
            return code
    return "OIDC_UNEXPECTED_ERROR"


def oidc_loggable_error_description(error_description: str | None) -> str | None:
    if error_description is None:
        return None
    normalized = " ".join(error_description.split())
    if len(normalized) > 512:
        return f"{normalized[:512]}..."
    return normalized


def oidc_callback_failure_redirect(
    error: Exception,
    *,
    binding_cookie_name: str | None,
    secure: bool,
    logger: Logger,
) -> RedirectResponse:
    error_code = oidc_error_code_for_exception(error)
    if not is_known_oidc_error(error):
        logger.exception("Unexpected OIDC callback failure")
    if isinstance(error, OidcCallbackFlowError):
        purpose = error.purpose
        redirect_path = error.redirect_path
    else:
        purpose = "login"
        redirect_path = "/app"
    if purpose == "account_deletion_reauth":
        target = merge_redirect_query(
            redirect_path,
            oidcError=error_code,
            oidcReauth=None,
        )
    else:
        target = merge_redirect_query(
            "/login",
            oidcError=error_code,
            oidcReauth=None,
        )
    response = oidc_redirect(target)
    if binding_cookie_name is not None:
        clear_oidc_binding_cookie(response, binding_cookie_name, secure=secure)
    return response


@router.get("/oidc/providers")
async def list_oidc_providers(
        response: Response,
        oidc_settings: OidcSettings = Depends(get_oidc_settings),
) -> dict[str, list[dict[str, str]]]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "providers": [{
            "providerId": provider.provider_id,
            "displayName": provider.display_name,
        } for provider in oidc_settings.providers]
    }


@router.get("/oidc/{provider_id}/start")
async def start_oidc_login(
        provider_id: str,
        request: Request,
        redirect: str | None = None,
        language_code_param: str | None = Query(default=None, alias="languageCode"),
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: OAuthOidcUsecaseInterface = Depends(get_oauth_oidc_usecase),
        logger: Logger = Depends(get_logger),
) -> RedirectResponse:
    language_code = (language_code_param if language_code_param is not None
                     and is_supported_language_code(language_code_param) else
                     DEFAULT_LANGUAGE_CODE if language_code_param is not None else None)
    try:
        result = await usecase.start_authorization(
            provider_id=provider_id,
            redirect_path=redirect,
            purpose="login",
            current_session=None,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            language_code=language_code,
        )
    except OIDC_KNOWN_ERRORS as error:
        return oidc_start_failure_redirect("/login", error)
    except Exception as error:
        logger.exception("Unexpected OIDC authorization start failure")
        return oidc_start_failure_redirect("/login", error)
    response = oidc_redirect(result.authorization_url)
    set_oidc_binding_cookie(
        response,
        key=result.browser_binding_cookie_name,
        value=result.browser_binding_cookie_value,
        secure=is_secure_request(request, auth_settings),
        max_age_seconds=result.browser_binding_cookie_max_age,
    )
    return response


@router.get("/oidc/{provider_id}/reauth")
async def start_oidc_reauth(
        provider_id: str,
        request: Request,
        redirect: str | None = None,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        auth_usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
        usecase: OAuthOidcUsecaseInterface = Depends(get_oauth_oidc_usecase),
        logger: Logger = Depends(get_logger),
) -> RedirectResponse:
    auth_context = await auth_usecase.authenticate_session(
        session_token=request.cookies.get(session_cookie_name(auth_settings)),
        ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
        user_agent=get_user_agent(request),
    )
    if auth_context is None:
        return oidc_start_failure_redirect(
            "/login",
            OidcReauthAuthenticationRequiredError("Current session is required"),
        )
    try:
        result = await usecase.start_authorization(
            provider_id=provider_id,
            redirect_path=redirect,
            purpose="account_deletion_reauth",
            current_session=auth_context,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
        )
    except OIDC_KNOWN_ERRORS as error:
        return oidc_start_failure_redirect("/app/settings", error)
    except Exception as error:
        logger.exception("Unexpected OIDC reauthorization start failure")
        return oidc_start_failure_redirect("/app/settings", error)
    response = oidc_redirect(result.authorization_url)
    set_oidc_binding_cookie(
        response,
        key=result.browser_binding_cookie_name,
        value=result.browser_binding_cookie_value,
        secure=is_secure_request(request, auth_settings),
        max_age_seconds=result.browser_binding_cookie_max_age,
    )
    return response


@router.get("/oidc/{provider_id}/callback")
async def complete_oidc_callback(
        provider_id: str,
        request: Request,
        state: str | None = None,
        code: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        auth_usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
        oidc_usecase: OAuthOidcUsecaseInterface = Depends(get_oauth_oidc_usecase),
        logger: Logger = Depends(get_logger),
) -> RedirectResponse:
    secure = is_secure_request(request, auth_settings)
    binding_cookie_name = oidc_binding_cookie_name_for_state(state) if state else None
    if error is not None:
        logger.info(
            "OIDC provider returned callback error",
            extra={
                "provider_id": provider_id,
                "oidc_error": error,
                "oidc_error_description": oidc_loggable_error_description(error_description),
            },
        )
        if state is None:
            return oidc_callback_failure_redirect(
                OidcStateMismatchError(),
                binding_cookie_name=binding_cookie_name,
                secure=secure,
                logger=logger,
            )
        binding_cookie_name = oidc_binding_cookie_name_for_state(state)
        try:
            current_session = await auth_usecase.authenticate_session(
                session_token=request.cookies.get(session_cookie_name(auth_settings)),
                ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
                user_agent=get_user_agent(request),
            )
            await oidc_usecase.complete_error_callback(
                provider_id=provider_id,
                state=state,
                browser_binding_cookie_value=request.cookies.get(binding_cookie_name),
                provider_error=OidcProviderAccessDeniedError(error),
                current_session=current_session,
                ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
                user_agent=get_user_agent(request),
            )
        except Exception as callback_error:
            return oidc_callback_failure_redirect(
                callback_error,
                binding_cookie_name=binding_cookie_name,
                secure=secure,
                logger=logger,
            )
    if state is None or code is None:
        return oidc_callback_failure_redirect(
            OidcStateMismatchError(),
            binding_cookie_name=binding_cookie_name,
            secure=secure,
            logger=logger,
        )
    binding_cookie_name = oidc_binding_cookie_name_for_state(state)
    try:
        current_session = await auth_usecase.authenticate_session(
            session_token=request.cookies.get(session_cookie_name(auth_settings)),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
        result = await oidc_usecase.complete_callback(
            provider_id=provider_id,
            state=state,
            code=code,
            browser_binding_cookie_value=request.cookies.get(binding_cookie_name),
            current_session=current_session,
            current_session_token=request.cookies.get(session_cookie_name(auth_settings)),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except Exception as callback_error:
        return oidc_callback_failure_redirect(
            callback_error,
            binding_cookie_name=binding_cookie_name,
            secure=secure,
            logger=logger,
        )

    if result.issued_session is not None:
        response = oidc_redirect(
            merge_redirect_query(
                result.redirect_path,
                oidcError=None,
                oidcReauth=None,
            ))
        set_session_cookie(
            response,
            result.issued_session.session_token,
            secure=secure,
            max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
            auth_settings=auth_settings,
        )
        set_csrf_cookie(
            response,
            result.issued_session.csrf_token,
            secure=secure,
            max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        )
    else:
        csrf_token = await auth_usecase.issue_csrf_token(session_token=request.cookies.get(
            session_cookie_name(auth_settings)), )
        response = oidc_redirect(
            merge_redirect_query(
                result.redirect_path,
                oidcError=None,
                oidcReauth="success",
            ))
        set_csrf_cookie(
            response,
            csrf_token,
            secure=secure,
            max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        )
    if binding_cookie_name is not None:
        clear_oidc_binding_cookie(response, binding_cookie_name, secure=secure)
    return response


@router.get("/csrf", response_model=CsrfTokenResponse)
async def get_csrf(
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> CsrfTokenResponse:
    response.headers["Cache-Control"] = "no-store"
    existing_csrf_token = request.cookies.get(csrf_cookie_name())
    if existing_csrf_token:
        session_token = request.cookies.get(session_cookie_name(auth_settings))
        if not session_token:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

        csrf_status = await usecase.validate_session_csrf(
            session_token=session_token,
            csrf_token=existing_csrf_token,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
        if csrf_status in {
                SessionCsrfStatus.VALID,
                SessionCsrfStatus.NO_SESSION,
        }:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

    csrf_token = await usecase.issue_csrf_token(session_token=request.cookies.get(
        session_cookie_name(auth_settings)), )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=is_secure_request(request, auth_settings),
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return CsrfTokenResponse(csrfToken=csrf_token)


@router.get("/me", response_model=AuthUserResponse, responses=ME_ERROR_RESPONSES)
async def get_me(
    response: Response,
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
) -> AuthUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return _auth_user_response(auth_context)


@router.patch("/me", response_model=AuthUserResponse, responses=ME_ERROR_RESPONSES)
async def update_me(
        payload: UpdateAuthUserRequest,
        response: Response,
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthUserResponse:
    response.headers["Cache-Control"] = "no-store"
    updated_context = await usecase.update_current_user(
        auth_context,
        AuthUserUpdateChanges(
            language_code=payload.language_code,
            fields_set=frozenset(payload.model_fields_set),
        ),
    )
    return _auth_user_response(updated_context)


@router.delete(
    "/me",
    status_code=204,
    responses=DELETE_ACCOUNT_ERROR_RESPONSES,
)
async def delete_me(
    payload: AccountDeletionRequest,
    request: Request,
    response: Response,
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
    auth_settings: AuthSettings = Depends(get_auth_settings),
    account_deletion_usecase: AccountDeletionUsecaseInterface = Depends(
        get_account_deletion_usecase),
) -> Response:
    try:
        await account_deletion_usecase.delete_account(
            auth_context=auth_context,
            confirm_email=payload.confirm_email,
            password=payload.password,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except AccountDeletionConfirmationMismatchError as error:
        raise api_error(
            400,
            "ACCOUNT_DELETION_CONFIRMATION_MISMATCH",
            "Account deletion confirmation did not match",
        ) from error
    except AccountDeletionReauthRequiredError as error:
        raise api_error(
            400,
            "ACCOUNT_DELETION_REAUTH_REQUIRED",
            "Password confirmation is required",
        ) from error
    except AccountDeletionInvalidPasswordError as error:
        raise api_error(
            400,
            "ACCOUNT_DELETION_INVALID_PASSWORD",
            "Password confirmation failed",
        ) from error
    except AccountDeletionOidcReauthRequiredError as error:
        raise api_error(
            400,
            "ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED",
            "OIDC reauthentication is required",
            details=error.linked_providers,
        ) from error
    except RateLimitExceededError as error:
        raise api_error(
            429,
            "ACCOUNT_DELETION_REAUTH_RATE_LIMITED",
            "Too many account deletion confirmation attempts",
            headers={
                "Retry-After":
                str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error

    secure = is_secure_request(request, auth_settings)
    clear_session_cookie(response, secure=secure, auth_settings=auth_settings)
    clear_csrf_cookie(response, secure=secure)
    response.status_code = 204
    return response


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=201,
    responses=REGISTER_ERROR_RESPONSES,
)
async def register(
        payload: RegisterRequest,
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthUserResponse:
    try:
        issued_session = await usecase.register(
            email=payload.email,
            password=payload.password,
            language_code=payload.language_code,
            current_session_token=request.cookies.get(session_cookie_name(auth_settings)),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except EmailAlreadyRegisteredError as error:
        raise api_error(
            409,
            "EMAIL_ALREADY_REGISTERED",
            "Email already registered",
        ) from error
    except RateLimitExceededError as error:
        raise api_error(
            429,
            "REGISTER_RATE_LIMITED",
            "Too many register attempts",
            headers={
                "Retry-After":
                str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error
    except WeakPasswordError as error:
        raise api_error(422, "WEAK_PASSWORD", str(error)) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        issued_session.session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        auth_settings=auth_settings,
    )
    set_csrf_cookie(
        response,
        issued_session.csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return _auth_user_response(issued_session)


@router.post(
    "/login",
    response_model=AuthUserResponse,
    responses=LOGIN_ERROR_RESPONSES,
)
async def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthUserResponse:
    try:
        issued_session = await usecase.login(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get(session_cookie_name(auth_settings)),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except InvalidCredentialsError as error:
        raise api_error(401, "INVALID_CREDENTIALS", "Unauthorized") from error
    except RateLimitExceededError as error:
        raise api_error(
            429,
            "LOGIN_RATE_LIMITED",
            "Too many login attempts",
            headers={
                "Retry-After":
                str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        issued_session.session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        auth_settings=auth_settings,
    )
    set_csrf_cookie(
        response,
        issued_session.csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return _auth_user_response(issued_session)


@router.post(
    "/logout",
    status_code=204,
    responses=LOGOUT_ERROR_RESPONSES,
)
async def logout(
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> Response:
    secure = is_secure_request(request, auth_settings)
    await usecase.logout(
        request.cookies.get(session_cookie_name(auth_settings)),
        ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
        user_agent=get_user_agent(request),
    )
    clear_session_cookie(response, secure=secure, auth_settings=auth_settings)
    clear_csrf_cookie(response, secure=secure)
    response.status_code = 204
    return response


def _auth_user_response(
    source: AuthenticatedSessionContext | IssuedAuthSession, ) -> AuthUserResponse:
    return AuthUserResponse(
        id=source.user.id,
        email=source.user.email,
        roles=sorted(source.roles),
        permissions=sorted(source.permissions),
        language_code=source.user.language_code,
    )
