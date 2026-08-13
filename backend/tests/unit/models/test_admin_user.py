from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models.admin_user import (AdminUserDetail, AdminUserListQuery, AdminUserRecord,
                                   AdminUserUpdateChanges)
from app.models.admin_user_schemas import (AdminUserCreateRequest, AdminUserListItemResponse,
                                           AdminUserResponse, AdminUserUpdateRequest)
from app.models.user import User


def _user() -> User:
    return User(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@example.com",
        password_hash="hash",
        is_active=True,
        registered_at=datetime(2026, 1, 1, tzinfo=UTC),
        modified_at=datetime(2026, 1, 2, tzinfo=UTC),
        created_at=datetime(2026, 1, 4, tzinfo=UTC),
        updated_at=datetime(2026, 1, 5, tzinfo=UTC),
        last_logged_in_at=datetime(2026, 1, 3, tzinfo=UTC),
    )


def test_admin_user_list_query_keeps_filters() -> None:
    query = AdminUserListQuery(search="admin", is_active=True, role="admin")

    assert query.search == "admin"
    assert query.is_active is True
    assert query.role == "admin"


def test_admin_user_domain_models_keep_user_and_authorization_values() -> None:
    user = _user()
    record = AdminUserRecord(user=user, roles=("admin", "member"))
    detail = AdminUserDetail(user=user, roles=("admin", ), permissions=("admin:access", ))
    changes = AdminUserUpdateChanges(
        email="new@example.com",
        password=None,
        is_active=False,
        roles=("member", ),
        fields_set=frozenset({"email", "is_active", "roles"}),
    )

    assert record.user is user
    assert record.roles == ("admin", "member")
    assert detail.permissions == ("admin:access", )
    assert changes.fields_set == frozenset({"email", "is_active", "roles"})


def test_admin_user_response_serializes_snake_case_unix_timestamp_seconds() -> None:
    user = _user()
    list_item = AdminUserListItemResponse.from_record(AdminUserRecord(user=user, roles=("admin", )))
    detail = AdminUserResponse.from_detail(
        AdminUserDetail(user=user, roles=("admin", ), permissions=("admin:access", )))

    assert list_item.model_dump(mode="json") == {
        "id": str(user.id),
        "email": "admin@example.com",
        "is_active": True,
        "created_at": 1767225600,
        "updated_at": 1767312000,
        "last_login_at": 1767398400,
        "roles": ["admin"],
    }
    assert detail.model_dump(mode="json")["permissions"] == ["admin:access"]


def test_admin_user_requests_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AdminUserCreateRequest.model_validate({
            "email": "admin@example.com",
            "password": "Password@123!",
            "unknown": "value",
        })


def test_admin_user_update_rejects_null_non_nullable_patch_fields() -> None:
    for field_name in ("email", "password", "is_active", "roles"):
        with pytest.raises(ValidationError):
            AdminUserUpdateRequest.model_validate({field_name: None})


def test_admin_user_update_keeps_empty_patch_fields_set() -> None:
    request = AdminUserUpdateRequest.model_validate({})

    assert request.model_fields_set == set()


def test_admin_user_update_accepts_roles_and_snake_case_status() -> None:
    request = AdminUserUpdateRequest.model_validate({"is_active": False, "roles": ["admin"]})

    assert request.is_active is False
    assert request.roles == ["admin"]
    assert request.model_fields_set == {"is_active", "roles"}
