from app.libraries.password_hasher import (hash_password,
                                           validate_password_policy,
                                           verify_password)


def test_password_hash_round_trip():
    hashed_password = hash_password("Password123!")

    assert verify_password("Password123!", hashed_password) is True


def test_password_policy_rejects_short_password():
    is_valid, message = validate_password_policy("short")

    assert is_valid is False
    assert message == "Password must be at least 12 characters long"
