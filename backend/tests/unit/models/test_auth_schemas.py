import pytest
from pydantic import ValidationError

from app.models.auth_schemas import AccountDeletionRequest


def test_account_deletion_request_accepts_camel_case_confirm_email() -> None:
    request = AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com"})

    assert request.confirm_email == "user@example.com"
    assert request.password is None


def test_account_deletion_request_accepts_password() -> None:
    request = AccountDeletionRequest.model_validate({
        "confirmEmail": "user@example.com",
        "password": "Password123!",
    })

    assert request.password == "Password123!"


def test_account_deletion_request_accepts_internal_field_name() -> None:
    request = AccountDeletionRequest.model_validate({"confirm_email": "user@example.com"})

    assert request.confirm_email == "user@example.com"


def test_account_deletion_request_dumps_confirm_email_by_alias() -> None:
    payload = AccountDeletionRequest(confirm_email="user@example.com").model_dump(by_alias=True)

    assert payload["confirmEmail"] == "user@example.com"
    assert "confirm_email" not in payload


def test_account_deletion_request_forbids_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate({
            "confirmEmail": "user@example.com",
            "unexpected": True,
        })


def test_account_deletion_request_requires_confirm_email() -> None:
    with pytest.raises(ValidationError):
        AccountDeletionRequest.model_validate({"password": "Password123!"})
