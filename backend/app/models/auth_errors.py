class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class RateLimitExceededError(Exception):
    pass


class WeakPasswordError(Exception):
    pass
