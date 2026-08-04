from uuid import UUID


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class RateLimitExceededError(Exception):

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class AccountDeletionConfirmationMismatchError(Exception):
    pass


class AccountDeletionReauthRequiredError(Exception):
    pass


class AccountDeletionInvalidPasswordError(Exception):
    pass


class WeakPasswordError(Exception):
    pass


class UserNotFoundError(Exception):

    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User not found: {user_id}")
        self.user_id = user_id


class AuthSessionNotFoundError(Exception):

    def __init__(self, session_id: UUID) -> None:
        super().__init__(f"AuthSession not found: {session_id}")
        self.session_id = session_id
