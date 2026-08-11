from uuid import UUID

from app.usecases.authorization_audit import role_audit_detail


def test_role_audit_detail_omits_source_key_when_source_is_none() -> None:
    detail = role_audit_detail(
        source=None,
        actor_user_id=None,
        target_user_id=UUID("00000000-0000-0000-0000-000000000001"),
        role_code="admin",
        resulting_roles=("admin", ),
    )

    assert detail == {
        "actorUserId": None,
        "targetUserId": "00000000-0000-0000-0000-000000000001",
        "roleCode": "admin",
        "resultingRoles": ["admin"],
    }


def test_role_audit_detail_includes_source_when_present() -> None:
    detail = role_audit_detail(
        source="cli",
        actor_user_id=UUID("00000000-0000-0000-0000-000000000002"),
        target_user_id=UUID("00000000-0000-0000-0000-000000000001"),
        role_code="admin",
        resulting_roles=("admin", "member"),
    )

    assert detail == {
        "source": "cli",
        "actorUserId": "00000000-0000-0000-0000-000000000002",
        "targetUserId": "00000000-0000-0000-0000-000000000001",
        "roleCode": "admin",
        "resultingRoles": ["admin", "member"],
    }
