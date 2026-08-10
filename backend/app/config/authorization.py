from collections import Counter
from collections.abc import Iterable
from logging import Logger
from uuid import UUID

from app.models.authorization import (PermissionDefinition, RoleDefinition, RoleWithPermissions,
                                      UserAuthorization)

ROLE_CODE_MAX_LENGTH = 64
PERMISSION_CODE_MAX_LENGTH = 120

DEFAULT_AUTHORIZATION_PERMISSIONS: tuple[PermissionDefinition, ...] = (PermissionDefinition(
    code="admin:access",
    display_name="Admin access",
    description="Access administrative endpoints.",
), )

DEFAULT_AUTHORIZATION_DEFINITIONS: tuple[RoleDefinition, ...] = (RoleDefinition(
    code="admin",
    display_name="Admin",
    description="Full administrative access for this template.",
    permission_codes=("admin:access", ),
), )


def permission_catalog_by_code(
    permissions: tuple[PermissionDefinition, ...] = DEFAULT_AUTHORIZATION_PERMISSIONS,
) -> dict[str, PermissionDefinition]:
    return {permission.code: permission for permission in permissions}


def role_catalog_by_code(
    roles: tuple[RoleDefinition, ...] = DEFAULT_AUTHORIZATION_DEFINITIONS,
) -> dict[str, RoleDefinition]:
    return {role.code: role for role in roles}


def authorization_config_errors(
    permissions: tuple[PermissionDefinition, ...] = DEFAULT_AUTHORIZATION_PERMISSIONS,
    roles: tuple[RoleDefinition, ...] = DEFAULT_AUTHORIZATION_DEFINITIONS,
) -> list[str]:
    errors: list[str] = []
    permission_counts = Counter(permission.code for permission in permissions)
    role_counts = Counter(role.code for role in roles)
    duplicate_permissions = sorted(code for code, count in permission_counts.items() if count > 1)
    duplicate_roles = sorted(code for code, count in role_counts.items() if count > 1)
    empty_permissions = sorted(code for code in permission_counts if not code)
    empty_roles = sorted(code for code in role_counts if not code)
    oversized_permissions = sorted(code for code in permission_counts
                                   if code and len(code) > PERMISSION_CODE_MAX_LENGTH)
    oversized_roles = sorted(code for code in role_counts
                             if code and len(code) > ROLE_CODE_MAX_LENGTH)
    if duplicate_permissions:
        errors.append(f"Duplicate permission codes: {', '.join(duplicate_permissions)}")
    if duplicate_roles:
        errors.append(f"Duplicate role codes: {', '.join(duplicate_roles)}")
    if not permissions:
        errors.append("Permission catalog must not be empty.")
    if not roles:
        errors.append("Role catalog must not be empty.")
    if empty_permissions:
        errors.append("Permission code must not be empty.")
    if empty_roles:
        errors.append("Role code must not be empty.")
    for code in oversized_permissions:
        errors.append(f"Permission code exceeds 120 characters: {code}")
    for code in oversized_roles:
        errors.append(f"Role code exceeds 64 characters: {code}")
    permission_codes = frozenset(permission_counts)
    for role in roles:
        missing_permissions = sorted(frozenset(role.permission_codes) - permission_codes)
        if missing_permissions:
            errors.append(f"Role {role.code} references unknown permissions: "
                          f"{', '.join(missing_permissions)}")
    return errors


def unknown_role_codes(role_codes: Iterable[str]) -> frozenset[str]:
    roles = role_catalog_by_code()
    return frozenset(code for code in role_codes if code not in roles)


def permissions_for_role_codes(role_codes: Iterable[str]) -> frozenset[str]:
    roles = role_catalog_by_code()
    permissions: set[str] = set()
    for role_code in role_codes:
        role = roles.get(role_code)
        if role is None:
            continue
        permissions.update(role.permission_codes)
    return frozenset(permissions)


def user_authorization_from_role_codes(
    user_id: UUID,
    role_codes: Iterable[str],
) -> UserAuthorization:
    normalized_role_codes = tuple(dict.fromkeys(role_codes))
    roles = role_catalog_by_code()
    known_role_codes = tuple(code for code in normalized_role_codes if code in roles)
    return UserAuthorization(
        user_id=user_id,
        roles=frozenset(known_role_codes),
        permissions=permissions_for_role_codes(known_role_codes),
    )


def resolve_user_authorization(
    user_id: UUID,
    role_codes: Iterable[str],
    logger: Logger,
) -> UserAuthorization:
    normalized_role_codes = tuple(dict.fromkeys(role_codes))
    unknown_codes = unknown_role_codes(normalized_role_codes)
    if unknown_codes:
        logger.warning(
            "Unknown authorization role codes ignored for user_id=%s role_codes=%s",
            user_id,
            sorted(unknown_codes),
        )
    return user_authorization_from_role_codes(user_id, normalized_role_codes)


def roles_with_permissions() -> list[RoleWithPermissions]:
    return [
        RoleWithPermissions(
            code=role.code,
            display_name=role.display_name,
            description=role.description,
            permissions=tuple(sorted(dict.fromkeys(role.permission_codes))),
        ) for role in sorted(DEFAULT_AUTHORIZATION_DEFINITIONS, key=lambda role: role.code)
    ]
