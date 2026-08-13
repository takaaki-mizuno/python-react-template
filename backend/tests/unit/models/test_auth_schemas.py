import pytest
from pydantic import ValidationError

from app.models.auth_schemas import AccountDeletionRequest, CsrfTokenResponse, LoginRequest


def test_account_deletion_request_accepts_snake_case_confirm_email() -> None:
    request = AccountDeletionRequest.model_validate({"confirm_email": "user@example.com"})

    assert request.confirm_email == "user@example.com"
    assert request.password is None


def test_account_deletion_request_accepts_password() -> None:
    request = AccountDeletionRequest.model_validate({
        "confirm_email": "user@example.com",
        "password": "Password123!",
    })

    assert request.password == "Password123!"


def test_account_deletion_request_rejects_camel_case_confirm_email() -> None:
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com"})


def test_account_deletion_request_accepts_python_field_name() -> None:
    request = AccountDeletionRequest.model_validate({"confirm_email": "user@example.com"})

    assert request.confirm_email == "user@example.com"


def test_account_deletion_request_dumps_confirm_email_as_snake_case() -> None:
    payload = AccountDeletionRequest(confirm_email="user@example.com").model_dump()

    assert payload["confirm_email"] == "user@example.com"
    assert "confirmEmail" not in payload


def test_account_deletion_request_forbids_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate({
            "confirm_email": "user@example.com",
            "unexpected": True,
        })


def test_account_deletion_request_requires_confirm_email() -> None:
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate({"password": "Password123!"})


def test_login_request_forbids_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({
            "email": "user@example.com",
            "password": "Password123!",
            "remember_me": True,
        })


def test_csrf_token_response_forbids_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        CsrfTokenResponse.model_validate({
            "csrf_token": "token",
            "expires_at": 1786440600,
        })
