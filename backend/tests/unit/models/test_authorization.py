from logging import getLogger
from uuid import uuid4

from app.config.authorization import (DEFAULT_AUTHORIZATION_DEFINITIONS,
                                      DEFAULT_AUTHORIZATION_PERMISSIONS,
                                      authorization_config_errors, permission_catalog_by_code,
                                      permissions_for_role_codes, resolve_user_authorization,
                                      role_catalog_by_code, roles_with_permissions,
                                      unknown_role_codes, user_authorization_from_role_codes)
from app.models.authorization import PermissionDefinition, RoleDefinition, UserAuthorization
from app.models.user import User


def test_authorization_domain_results_use_immutable_sets() -> None:
    user = User(email="user@example.com", password_hash="hash")

    authorization = UserAuthorization(
        user_id=user.id,
        roles=frozenset({"admin"}),
        permissions=frozenset({"admin:access"}),
    )

    assert authorization.user_id == user.id
    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})


def test_default_definition_shapes_are_explicit() -> None:
    role = RoleDefinition(
        code="admin",
        display_name="Admin",
        description="Admin role",
        permission_codes=("admin:access", ),
    )
    permission = PermissionDefinition(
        code="admin:access",
        display_name="Admin access",
    )

    assert role.permission_codes == ("admin:access", )
    assert permission.description is None


def test_default_authorization_config_is_valid() -> None:
    assert authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        DEFAULT_AUTHORIZATION_DEFINITIONS,
    ) == []


def test_role_catalog_by_code_rejects_duplicate_role_codes() -> None:
    errors = authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        (
            RoleDefinition("admin", "Admin", permission_codes=("admin:access", )),
            RoleDefinition("admin", "Admin duplicate", permission_codes=("admin:access", )),
        ),
    )

    assert errors == ["Duplicate role codes: admin"]


def test_permission_catalog_by_code_rejects_duplicate_permission_codes() -> None:
    errors = authorization_config_errors(
        (
            PermissionDefinition("admin:access", "Admin access"),
            PermissionDefinition("admin:access", "Admin access duplicate"),
        ),
        DEFAULT_AUTHORIZATION_DEFINITIONS,
    )

    assert errors == ["Duplicate permission codes: admin:access"]


def test_authorization_config_rejects_unknown_role_permission_reference() -> None:
    errors = authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        (RoleDefinition("admin", "Admin", permission_codes=("missing:permission", )), ),
    )

    assert errors == ["Role admin references unknown permissions: missing:permission"]


def test_authorization_config_rejects_codes_longer_than_storage_contract() -> None:
    errors = authorization_config_errors(
        (PermissionDefinition("p" * 121, "Too long"), ),
        (RoleDefinition("r" * 65, "Too long", permission_codes=()), ),
    )

    assert errors == [
        "Permission code exceeds 120 characters: " + "p" * 121,
        "Role code exceeds 64 characters: " + "r" * 65,
    ]


def test_authorization_config_rejects_empty_codes() -> None:
    errors = authorization_config_errors(
        (PermissionDefinition("", "Empty"), ),
        (RoleDefinition("", "Empty", permission_codes=()), ),
    )

    assert errors == [
        "Permission code must not be empty.",
        "Role code must not be empty.",
    ]


def test_authorization_config_rejects_empty_catalogs() -> None:
    errors = authorization_config_errors((), ())

    assert errors == [
        "Permission catalog must not be empty.",
        "Role catalog must not be empty.",
    ]


def test_permissions_for_role_codes_resolves_permissions_from_code_catalog() -> None:
    permissions = permissions_for_role_codes(("admin", ))

    assert permissions == frozenset({"admin:access"})


def test_permissions_for_role_codes_ignores_unknown_role_codes() -> None:
    permissions = permissions_for_role_codes(("missing", "admin"))

    assert permissions == frozenset({"admin:access"})


def test_unknown_role_codes_reports_unknown_assignments() -> None:
    assert unknown_role_codes(("missing", "admin", "missing")) == frozenset({"missing"})


def test_user_authorization_from_role_codes_filters_unknown_roles_and_permissions() -> None:
    authorization = user_authorization_from_role_codes(
        user_id=uuid4(),
        role_codes=("missing", "admin"),
    )

    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})


def test_resolve_user_authorization_logs_unknown_roles(caplog) -> None:
    user_id = uuid4()

    authorization = resolve_user_authorization(
        user_id=user_id,
        role_codes=("missing", "admin"),
        logger=getLogger(__name__),
    )

    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})
    assert "Unknown authorization role codes ignored" in caplog.text
    assert "missing" in caplog.text


def test_roles_with_permissions_returns_catalog_for_admin_api() -> None:
    roles = roles_with_permissions()
    permissions = permission_catalog_by_code()
    role_catalog = role_catalog_by_code()

    assert set(role_catalog) == {"admin"}
    assert set(permissions) == {"admin:access"}
    assert roles[0].code == "admin"
    assert roles[0].permissions == ("admin:access", )
