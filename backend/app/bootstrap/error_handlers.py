import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from app.models.error import ErrorDetail, ErrorFieldDetail, ErrorResponse

logger = logging.getLogger(__name__)

_DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def api_error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    details: Sequence[ErrorFieldDetail | dict[str, Any]] | None = None,
) -> FastAPIHTTPException:
    return FastAPIHTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": list(details or []),
        },
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return await unhandled_exception_handler(request, exc)
    code, message, details = _error_parts(exc.status_code, exc.detail)
    return json_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return await unhandled_exception_handler(request, exc)
    details = [
        ErrorFieldDetail(
            loc=list(error.get("loc", [])),
            message=str(error.get("msg", "Invalid input")),
            type=str(error.get("type", "value_error")),
        ) for error in exc.errors()
    ]
    return json_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Validation failed",
        details=details,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return json_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error",
    )


def _error_parts(
    status_code: int,
    detail: Any,
) -> tuple[str, str, list[ErrorFieldDetail | dict[str, Any]]]:
    if isinstance(detail, dict):
        code = str(detail.get("code") or _default_error_code(status_code))
        message = str(detail.get("message") or _default_error_message(status_code))
        raw_details = detail.get("details") or []
        details = raw_details if isinstance(raw_details, list) else [raw_details]
        return code, message, details
    if isinstance(detail, str):
        return _default_error_code(status_code), detail, []
    return _default_error_code(status_code), _default_error_message(status_code), []


def json_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Sequence[ErrorFieldDetail | dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    if status_code == 401:
        response_headers.setdefault("Cache-Control", "no-store")
    payload = ErrorResponse(error=ErrorDetail(
        code=code,
        message=message,
        details=list(details or []),
    ))
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=response_headers,
    )


def _default_error_code(status_code: int) -> str:
    if status_code in _DEFAULT_ERROR_CODES:
        return _DEFAULT_ERROR_CODES[status_code]
    if status_code >= 500:
        return "INTERNAL_SERVER_ERROR"
    return "HTTP_ERROR"


def _default_error_message(status_code: int) -> str:
    if status_code == 500:
        return "Internal server error"
    return "HTTP error"
