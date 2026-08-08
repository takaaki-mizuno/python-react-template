from uuid import UUID


class RoleNotFoundError(Exception):

    def __init__(self, role_codes: set[str] | frozenset[str]) -> None:
        super().__init__(", ".join(sorted(role_codes)))
        self.role_codes = frozenset(role_codes)


class PermissionNotFoundError(Exception):

    def __init__(self, permission_codes: set[str] | frozenset[str]) -> None:
        super().__init__(", ".join(sorted(permission_codes)))
        self.permission_codes = frozenset(permission_codes)


class AuthorizationUserNotFoundError(Exception):

    def __init__(self, user_id: UUID) -> None:
        super().__init__(str(user_id))
        self.user_id = user_id
