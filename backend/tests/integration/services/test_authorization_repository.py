from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.authorization import Permission, PermissionDefinition, Role, RoleDefinition
from app.models.authorization_errors import PermissionNotFoundError, RoleNotFoundError
from app.models.user import User
from app.services.auth_repository import AuthRepository
from app.services.authorization_repository import AuthorizationRepository
from app.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration


@pytest.fixture
def async_session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def authorization_repository(async_session_factory):
    return AuthorizationRepository(unit_of_work=UnitOfWork(session_factory=async_session_factory))


@pytest.fixture
def auth_repository(async_session_factory):
    return AuthRepository(unit_of_work=UnitOfWork(session_factory=async_session_factory))


async def test_upsert_role_definition_keeps_updated_at_when_definition_is_unchanged(
    authorization_repository,
    async_session,
):
    definition = RoleDefinition("admin", "Admin", "Administrators")
    await authorization_repository.upsert_role_definition(definition)
    sentinel = datetime(2026, 1, 1, tzinfo=UTC)
    role = (await async_session.execute(select(Role).where(Role.code == "admin"))).scalar_one()
    role.updated_at = sentinel
    await async_session.commit()

    await authorization_repository.upsert_role_definition(definition)

    async_session.expire_all()
    unchanged_role = (await
                      async_session.execute(select(Role).where(Role.code == "admin"))).scalar_one()
    assert unchanged_role.updated_at == sentinel

    await authorization_repository.upsert_role_definition(
        RoleDefinition("admin", "Administrator", "Administrators"))

    async_session.expire_all()
    changed_role = (await
                    async_session.execute(select(Role).where(Role.code == "admin"))).scalar_one()
    assert changed_role.display_name == "Administrator"
    assert changed_role.updated_at != sentinel


async def test_upsert_permission_definition_keeps_updated_at_when_definition_is_unchanged(
    authorization_repository,
    async_session,
):
    definition = PermissionDefinition("admin:access", "Admin access", "Access admin")
    await authorization_repository.upsert_permission_definition(definition)
    sentinel = datetime(2026, 1, 1, tzinfo=UTC)
    permission = (await async_session.execute(
        select(Permission).where(Permission.code == "admin:access"))).scalar_one()
    permission.updated_at = sentinel
    await async_session.commit()

    await authorization_repository.upsert_permission_definition(definition)

    async_session.expire_all()
    unchanged_permission = (await async_session.execute(
        select(Permission).where(Permission.code == "admin:access"))).scalar_one()
    assert unchanged_permission.updated_at == sentinel

    await authorization_repository.upsert_permission_definition(
        PermissionDefinition("admin:access", "Admin console access", "Access admin"))

    async_session.expire_all()
    changed_permission = (await async_session.execute(
        select(Permission).where(Permission.code == "admin:access"))).scalar_one()
    assert changed_permission.display_name == "Admin console access"
    assert changed_permission.updated_at != sentinel


async def test_replace_role_permissions_raises_permission_not_found(authorization_repository, ):
    await authorization_repository.upsert_role_definition(RoleDefinition("admin", "Admin"))

    with pytest.raises(PermissionNotFoundError) as exc_info:
        await authorization_repository.replace_role_permissions("admin", ("missing:permission", ))

    assert exc_info.value.permission_codes == frozenset({"missing:permission"})


async def test_replace_user_roles_grants_revokes_and_returns_permissions(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("role-target@example.com", "hash")
    await authorization_repository.upsert_permission_definition(
        PermissionDefinition("admin:access", "Admin access"))
    await authorization_repository.upsert_permission_definition(
        PermissionDefinition("users:read", "Read users"))
    await authorization_repository.upsert_role_definition(RoleDefinition("admin", "Admin"))
    await authorization_repository.upsert_role_definition(RoleDefinition("viewer", "Viewer"))
    await authorization_repository.replace_role_permissions("admin", ("admin:access", ))
    await authorization_repository.replace_role_permissions("viewer", ("users:read", ))

    first_result = await authorization_repository.replace_user_roles(
        user.id,
        ("viewer", ),
        assigned_by_user_id=None,
    )
    second_result = await authorization_repository.replace_user_roles(
        user.id,
        ("admin", ),
        assigned_by_user_id=None,
    )

    assert first_result.granted_role_codes == ("viewer", )
    assert second_result.granted_role_codes == ("admin", )
    assert second_result.revoked_role_codes == ("viewer", )
    assert second_result.current_role_codes == ("admin", )
    assert second_result.current_permission_codes == ("admin:access", )


async def test_get_user_authorization_allows_inactive_and_ignores_deleted(
    authorization_repository,
    auth_repository,
    async_session,
):
    inactive_user = await auth_repository.create_user("inactive-authz@example.com", "hash")
    deleted_user = await auth_repository.create_user("deleted-authz@example.com", "hash")
    inactive_record = await async_session.get(User, inactive_user.id)
    inactive_record.is_active = False
    await async_session.commit()
    await auth_repository.mark_user_deleted(
        deleted_user.id,
        datetime.now(UTC),
        session_id=None,
        ip_address=None,
    )

    inactive_authorization = await authorization_repository.get_user_authorization(inactive_user.id)

    assert inactive_authorization is not None
    assert inactive_authorization.user_id == inactive_user.id
    assert await authorization_repository.get_user_authorization(deleted_user.id) is None
    assert await authorization_repository.get_user_authorization(uuid4()) is None


async def test_replace_user_roles_raises_role_not_found(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("missing-role-target@example.com", "hash")

    with pytest.raises(RoleNotFoundError) as exc_info:
        await authorization_repository.replace_user_roles(user.id, ("missing", ), None)

    assert exc_info.value.role_codes == frozenset({"missing"})


async def test_delete_roles_for_user_removes_only_target_assignments(
    authorization_repository,
    auth_repository,
):
    target_user = await auth_repository.create_user("delete-roles-target@example.com", "hash")
    other_user = await auth_repository.create_user("delete-roles-other@example.com", "hash")
    await authorization_repository.upsert_role_definition(RoleDefinition("admin", "Admin"))
    await authorization_repository.replace_user_roles(target_user.id, ("admin", ), None)
    await authorization_repository.replace_user_roles(other_user.id, ("admin", ), None)

    deleted_count = await authorization_repository.delete_roles_for_user(target_user.id)

    target_authorization = await authorization_repository.get_user_authorization(target_user.id)
    other_authorization = await authorization_repository.get_user_authorization(other_user.id)
    assert deleted_count == 1
    assert target_authorization is not None
    assert target_authorization.roles == frozenset()
    assert other_authorization is not None
    assert other_authorization.roles == frozenset({"admin"})
