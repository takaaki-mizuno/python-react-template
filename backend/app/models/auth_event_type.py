from enum import StrEnum


class AuthEventType(StrEnum):
    REGISTER_SUCCESS = "register_success"
    REGISTER_FAILED = "register_failed"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_REJECTED = "session_rejected"
    USER_MARKED_DELETED = "user_marked_deleted"
    SESSION_REVOKED_DELETED_USER = "session_revoked_deleted_user"
    SESSION_REVOKED_INACTIVE_USER = "session_revoked_inactive_user"
