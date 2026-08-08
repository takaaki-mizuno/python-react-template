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
