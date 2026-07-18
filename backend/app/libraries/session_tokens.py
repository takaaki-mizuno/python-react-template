import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    # Tokens are high-entropy random values, so an unsalted lookup hash is enough.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
