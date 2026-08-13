from dataclasses import dataclass


@dataclass(frozen=True)
class ProblemType:
    code: str
    type: str
    title: str
    status: int


def _problem_type(code: str, title: str, status: int) -> ProblemType:
    return ProblemType(
        code=code,
        type=f"/problems/{code}",
        title=title,
        status=status,
    )


PROBLEM_TYPES: dict[str, ProblemType] = {
    "bad_request":
    _problem_type("bad_request", "Bad request", 400),
    "unauthorized":
    _problem_type("unauthorized", "Unauthorized", 401),
    "forbidden":
    _problem_type("forbidden", "Forbidden", 403),
    "permission_denied":
    _problem_type("permission_denied", "Permission denied", 403),
    "not_found":
    _problem_type("not_found", "Not found", 404),
    "method_not_allowed":
    _problem_type("method_not_allowed", "Method not allowed", 405),
    "not_acceptable":
    _problem_type("not_acceptable", "Not acceptable", 406),
    "conflict":
    _problem_type("conflict", "Conflict", 409),
    "unsupported_media_type":
    _problem_type(
        "unsupported_media_type",
        "Unsupported media type",
        415,
    ),
    "validation_error":
    _problem_type("validation_error", "Validation error", 422),
    "rate_limited":
    _problem_type("rate_limited", "Rate limited", 429),
    "internal_server_error":
    _problem_type(
        "internal_server_error",
        "Internal server error",
        500,
    ),
    "csrf_validation_failed":
    _problem_type(
        "csrf_validation_failed",
        "CSRF validation failed",
        403,
    ),
    "invalid_admin_user_query":
    _problem_type(
        "invalid_admin_user_query",
        "Invalid admin user query",
        422,
    ),
    "email_already_registered":
    _problem_type(
        "email_already_registered",
        "Email already registered",
        409,
    ),
    "weak_password":
    _problem_type("weak_password", "Weak password", 422),
    "role_not_found":
    _problem_type("role_not_found", "Role not found", 422),
    "user_not_found":
    _problem_type("user_not_found", "User not found", 404),
    "sample_item_invalid_cursor":
    _problem_type(
        "sample_item_invalid_cursor",
        "Invalid sample item cursor",
        400,
    ),
    "sample_item_not_found":
    _problem_type(
        "sample_item_not_found",
        "Sample item not found",
        404,
    ),
    "account_deletion_confirmation_mismatch":
    _problem_type(
        "account_deletion_confirmation_mismatch",
        "Account deletion confirmation mismatch",
        400,
    ),
    "account_deletion_reauth_required":
    _problem_type(
        "account_deletion_reauth_required",
        "Account deletion reauthentication required",
        400,
    ),
    "account_deletion_invalid_password":
    _problem_type(
        "account_deletion_invalid_password",
        "Account deletion invalid password",
        400,
    ),
    "account_deletion_oidc_reauth_required":
    _problem_type(
        "account_deletion_oidc_reauth_required",
        "Account deletion OIDC reauthentication required",
        400,
    ),
    "account_deletion_reauth_rate_limited":
    _problem_type(
        "account_deletion_reauth_rate_limited",
        "Account deletion reauthentication rate limited",
        429,
    ),
    "invalid_credentials":
    _problem_type("invalid_credentials", "Invalid credentials", 401),
    "register_rate_limited":
    _problem_type("register_rate_limited", "Register rate limited", 429),
    "login_rate_limited":
    _problem_type("login_rate_limited", "Login rate limited", 429),
}

_STATUS_DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_server_error",
}


def normalize_problem_code(code: str) -> str:
    return code.lower()


def problem_type_for_code(code: str, fallback_status: int) -> ProblemType:
    normalized_code = normalize_problem_code(code)
    if normalized_code in PROBLEM_TYPES:
        return PROBLEM_TYPES[normalized_code]
    return problem_type_for_status(fallback_status)


def problem_type_for_status(status_code: int) -> ProblemType:
    default_code = _STATUS_DEFAULT_CODES.get(status_code)
    if default_code is not None:
        return PROBLEM_TYPES[default_code]
    return ProblemType(
        code="http_error",
        type="/problems/http_error",
        title="HTTP error",
        status=status_code,
    )
