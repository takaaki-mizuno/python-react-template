from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.authorization import UserRole
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


async def test_replace_user_roles_grants_and_revokes_role_codes(
    authorization_repository,
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("role-target@example.com", "hash")

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

    rows = (await async_session.execute(
        select(UserRole.role_code).where(col(UserRole.user_id) == user.id).order_by(
            UserRole.role_code))).scalars().all()
    assert rows == ["admin"]
    assert first_result.granted_role_codes == ("viewer", )
    assert second_result.granted_role_codes == ("admin", )
    assert second_result.revoked_role_codes == ("viewer", )
    assert second_result.current_role_codes == ("admin", )


async def test_get_user_role_codes_returns_sorted_assignments(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("role-list@example.com", "hash")
    await authorization_repository.replace_user_roles(
        user.id,
        ("viewer", "admin"),
        assigned_by_user_id=None,
    )

    role_codes = await authorization_repository.get_user_role_codes(user.id)

    assert role_codes == ("admin", "viewer")


async def test_unknown_role_assignment_inspection_and_prune(
    authorization_repository,
    auth_repository,
):
    known_user = await auth_repository.create_user("known-role@example.com", "hash")
    unknown_user = await auth_repository.create_user("unknown-role@example.com", "hash")
    await authorization_repository.replace_user_roles(known_user.id, ("admin", ), None)
    await authorization_repository.replace_user_roles(unknown_user.id, ("deleted-role", ), None)

    assignments = await authorization_repository.list_unknown_role_assignments(frozenset({"admin"}))
    deleted_count = await authorization_repository.delete_unknown_role_assignments(
        frozenset({"admin"}))

    assert [(assignment.user_id, assignment.role_code)
            for assignment in assignments] == [(unknown_user.id, "deleted-role")]
    assert deleted_count == 1
    assert await authorization_repository.get_user_role_codes(known_user.id) == ("admin", )
    assert await authorization_repository.get_user_role_codes(unknown_user.id) == ()


async def test_delete_roles_for_user_removes_only_target_assignments(
    authorization_repository,
    auth_repository,
):
    target_user = await auth_repository.create_user("delete-roles-target@example.com", "hash")
    other_user = await auth_repository.create_user("delete-roles-other@example.com", "hash")
    await authorization_repository.replace_user_roles(target_user.id, ("admin", ), None)
    await authorization_repository.replace_user_roles(other_user.id, ("admin", ), None)

    deleted_count = await authorization_repository.delete_roles_for_user(target_user.id)

    assert deleted_count == 1
    assert await authorization_repository.get_user_role_codes(target_user.id) == ()
    assert await authorization_repository.get_user_role_codes(other_user.id) == ("admin", )


async def test_get_user_role_codes_returns_empty_for_missing_user(authorization_repository) -> None:
    assert await authorization_repository.get_user_role_codes(uuid4()) == ()
