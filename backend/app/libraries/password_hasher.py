from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def validate_password_policy(raw_password: str) -> tuple[bool, str | None]:
    if len(raw_password) < 12:
        return False, "Password must be at least 12 characters long"
    if len(raw_password) > 128:
        return False, "Password must be 128 characters or fewer"
    return True, None


def hash_password(raw_password: str) -> str:
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return password_hash.verify(raw_password, hashed_password)
