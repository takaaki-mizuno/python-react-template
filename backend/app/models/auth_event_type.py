from enum import StrEnum


class AuthEventType(StrEnum):
    REGISTER_SUCCESS = "register_success"
    REGISTER_FAILED = "register_failed"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_REJECTED = "session_rejected"
    USER_MARKED_DELETED = "user_marked_deleted"
    ACCOUNT_DELETION_REAUTH_FAILED = "account_deletion_reauth_failed"
    SESSION_REVOKED_DELETED_USER = "session_revoked_deleted_user"
    SESSION_REVOKED_INACTIVE_USER = "session_revoked_inactive_user"
    OIDC_LOGIN_SUCCESS = "oidc_login_success"
    OIDC_LOGIN_FAILED = "oidc_login_failed"
    OIDC_IDENTITY_LINKED = "oidc_identity_linked"
    OIDC_USER_PROVISIONED = "oidc_user_provisioned"
    OIDC_REAUTH_SUCCESS = "oidc_reauth_success"
    OIDC_REAUTH_FAILED = "oidc_reauth_failed"
    ROLE_GRANTED = "role_granted"
    ROLE_REVOKED = "role_revoked"
