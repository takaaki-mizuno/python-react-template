import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from app.models.error import ProblemDetails, ProblemError
from app.models.problem_types import (PROBLEM_TYPES, normalize_problem_code, problem_type_for_code,
                                      problem_type_for_status)

logger = logging.getLogger(__name__)
RESERVED_PROBLEM_DETAILS_MEMBERS = {
    "type",
    "title",
    "status",
    "detail",
    "instance",
    "code",
    "errors",
}


def api_error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    errors: Sequence[ProblemError | dict[str, Any]] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> FastAPIHTTPException:
    detail: dict[str, Any] = {
        "code": code,
        "detail": message,
    }
    if errors:
        detail["errors"] = list(errors)
    if extensions:
        detail.update(extensions)
    return FastAPIHTTPException(
        status_code=status_code,
        detail=detail,
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
    code, detail, errors, extensions = _error_parts(exc.status_code, exc.detail)
    return problem_response(
        status_code=exc.status_code,
        code=code,
        detail=detail,
        errors=errors,
        extensions=extensions,
        request_path=request.url.path,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return await unhandled_exception_handler(request, exc)
    errors = [_validation_error_item(error) for error in exc.errors()]
    return problem_response(
        status_code=422,
        code="validation_error",
        detail="Request validation failed.",
        errors=errors,
        request_path=request.url.path,
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
    return problem_response(
        status_code=500,
        code="internal_server_error",
        detail="Internal server error",
        request_path=request.url.path,
    )


def _error_parts(
    status_code: int,
    detail: Any,
) -> tuple[str, str, list[ProblemError | dict[str, Any]], dict[str, Any]]:
    if isinstance(detail, dict):
        code = str(detail.get("code") or problem_type_for_status(status_code).code)
        message = str(detail.get("detail") or _default_detail(status_code))
        raw_errors = detail.get("errors") or []
        errors = raw_errors if isinstance(raw_errors, list) else [raw_errors]
        extensions = {
            key: value
            for key, value in detail.items() if key not in {"code", "detail", "errors"}
        }
        return code, message, errors, extensions
    if isinstance(detail, str):
        return problem_type_for_status(status_code).code, detail, [], {}
    return problem_type_for_status(status_code).code, _default_detail(status_code), [], {}


def problem_response(
    status_code: int,
    code: str,
    detail: str,
    errors: Sequence[ProblemError | dict[str, Any]] | None = None,
    extensions: Mapping[str, Any] | None = None,
    request_path: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    if status_code == 401:
        response_headers.setdefault("Cache-Control", "no-store")
    normalized_code = normalize_problem_code(code)
    if normalized_code not in PROBLEM_TYPES:
        logger.warning(
            "Unknown problem code %s for status %s; using status fallback",
            code,
            status_code,
        )
    problem_type = problem_type_for_code(code, fallback_status=status_code)
    error_items = list(errors) if errors is not None else None
    safe_extensions = _safe_problem_extensions(extensions)
    payload = ProblemDetails(
        type=problem_type.type,
        title=problem_type.title,
        status=status_code,
        detail=detail,
        instance=request_path,
        code=problem_type.code,
        errors=error_items or None,
        **safe_extensions,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
        media_type="application/problem+json",
    )


def _validation_error_item(error: dict[str, Any]) -> ProblemError:
    location_parts = list(error.get("loc", []))
    location = str(location_parts[0]) if location_parts else None
    field_path = location_parts[1:]
    kwargs: dict[str, Any] = {
        "location": location,
        "detail": str(error.get("msg", "Invalid input")),
        "code": str(error.get("type", "value_error")),
    }
    if location == "body" and field_path:
        kwargs["pointer"] = _json_pointer(field_path)
    elif location in {"query", "path", "header", "cookie"} and field_path:
        kwargs["parameter"] = str(field_path[0])
    return ProblemError(**kwargs)


def _safe_problem_extensions(extensions: Mapping[str, Any] | None) -> dict[str, Any]:
    if not extensions:
        return {}
    safe_extensions = dict(extensions)
    reserved_keys = sorted(set(safe_extensions) & RESERVED_PROBLEM_DETAILS_MEMBERS)
    for key in reserved_keys:
        logger.warning("Reserved Problem Details extension member %s was dropped", key)
        safe_extensions.pop(key, None)
    return safe_extensions


def _json_pointer(parts: Sequence[Any]) -> str:
    escaped_parts = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "#/" + "/".join(escaped_parts)


def _default_detail(status_code: int) -> str:
    if status_code == 500:
        return "Internal server error"
    return "HTTP error"
