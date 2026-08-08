from app.models.authorization import PermissionDefinition, RoleDefinition

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
