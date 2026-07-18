from app.libraries.session_tokens import generate_token, hash_token


def test_hash_token_uses_sha256_for_lookup_hash():
    assert hash_token("session-token") == (
        "c101e911469c969171040b50d70543313cf968fdef5bacc780776f8fb399ab36")


def test_generate_token_is_not_empty():
    assert generate_token()


def test_generate_token_has_expected_entropy_and_is_unique():
    tokens = {generate_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)
    assert all(len(hash_token(token)) == 64 for token in tokens)
    assert all(hash_token(token) != token for token in tokens)
