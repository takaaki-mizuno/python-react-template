from enum import StrEnum


class AuthEventType(StrEnum):
    REGISTER_SUCCESS = "register_success"
    REGISTER_FAILED = "register_failed"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_REJECTED = "session_rejected"
