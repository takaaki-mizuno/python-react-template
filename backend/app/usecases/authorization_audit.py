from uuid import UUID


def role_audit_detail(
    *,
    source: str | None,
    actor_user_id: UUID | None,
    target_user_id: UUID,
    role_code: str,
    resulting_roles: tuple[str, ...],
) -> dict[str, object]:
    """Build role audit detail; omit the source key entirely when source is None."""
    detail: dict[str, object] = {
        "actorUserId": str(actor_user_id) if actor_user_id is not None else None,
        "targetUserId": str(target_user_id),
        "roleCode": role_code,
        "resultingRoles": list(resulting_roles),
    }
    if source is not None:
        detail = {"source": source, **detail}
    return detail
