from enum import StrEnum


class SessionCsrfStatus(StrEnum):
    VALID = "valid"
    MISMATCH = "mismatch"
    NO_SESSION = "no_session"
