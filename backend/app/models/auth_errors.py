class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class RateLimitExceededError(Exception):

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class WeakPasswordError(Exception):
    pass
