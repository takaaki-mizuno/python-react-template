from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter


def test_rate_limiter_blocks_after_threshold():
    limiter = InMemoryLoginRateLimiter(
        window_seconds=900,
        max_attempts_per_email_ip=2,
        max_attempts_per_ip=10,
    )

    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is False


def test_rate_limiter_reset_clears_state():
    limiter = InMemoryLoginRateLimiter(
        window_seconds=900,
        max_attempts_per_email_ip=1,
        max_attempts_per_ip=10,
    )

    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is False

    limiter.reset()

    assert limiter.allow("127.0.0.1", "user@example.com") is True


def test_rate_limiter_discards_expired_bucket_keys():
    now = 100.0
    limiter = InMemoryLoginRateLimiter(
        window_seconds=10,
        max_attempts_per_email_ip=2,
        max_attempts_per_ip=10,
        clock=lambda: now,
    )
    limiter.allow("127.0.0.1", "expired@example.com")

    now = 111.0
    limiter.allow("127.0.0.2", "current@example.com")

    assert "127.0.0.1:expired@example.com" not in limiter._email_ip_buckets
    assert "127.0.0.1" not in limiter._ip_buckets
