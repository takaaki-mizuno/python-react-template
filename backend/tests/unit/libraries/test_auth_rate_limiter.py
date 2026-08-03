from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter


def _limiter(now_ref: list[float] | None = None) -> InMemoryLoginRateLimiter:
    now = now_ref or [100.0]
    return InMemoryLoginRateLimiter(
        window_seconds=10,
        registration_window_seconds=30,
        max_failures_per_email_ip=2,
        max_failures_per_ip=3,
        max_failures_per_email=3,
        max_registrations_per_ip=2,
        max_buckets_per_scope=3,
        clock=lambda: now[0],
    )


def test_is_allowed_does_not_append_to_buckets():
    limiter = _limiter()

    assert limiter.is_allowed("127.0.0.1", "user@example.com") is True

    assert "127.0.0.1:user@example.com" not in limiter._email_ip_buckets
    assert "127.0.0.1" not in limiter._ip_buckets
    assert "user@example.com" not in limiter._email_buckets


def test_record_failure_blocks_by_email_ip_bucket():
    limiter = _limiter()

    limiter.record_failure("127.0.0.1", "user@example.com")
    limiter.record_failure("127.0.0.1", "user@example.com")

    assert limiter.is_allowed("127.0.0.1", "user@example.com") is False


def test_record_failure_blocks_by_ip_bucket_across_emails():
    limiter = _limiter()

    limiter.record_failure("127.0.0.1", "a@example.com")
    limiter.record_failure("127.0.0.1", "b@example.com")
    limiter.record_failure("127.0.0.1", "c@example.com")

    assert limiter.is_allowed("127.0.0.1", "d@example.com") is False


def test_record_failure_blocks_by_email_bucket_across_ips():
    limiter = _limiter()

    limiter.record_failure("127.0.0.1", "user@example.com")
    limiter.record_failure("127.0.0.2", "user@example.com")
    limiter.record_failure("127.0.0.3", "user@example.com")

    assert limiter.is_allowed("127.0.0.4", "user@example.com") is False


def test_register_style_failure_can_skip_email_bucket():
    limiter = _limiter()

    for index in range(4):
        limiter.record_failure(
            f"127.0.0.{index}",
            "victim@example.com",
            include_email_bucket=False,
        )

    assert limiter.is_allowed("127.0.0.10", "victim@example.com") is True


def test_record_success_clears_only_matching_email_ip_bucket():
    limiter = _limiter()
    limiter.record_failure("127.0.0.1", "user@example.com")
    limiter.record_failure("127.0.0.1", "other@example.com")
    limiter.record_failure("127.0.0.2", "user@example.com")

    limiter.record_success("127.0.0.1", "user@example.com")

    assert "127.0.0.1:user@example.com" not in limiter._email_ip_buckets
    assert "127.0.0.1:other@example.com" in limiter._email_ip_buckets
    assert "127.0.0.2:user@example.com" in limiter._email_ip_buckets
    assert len(limiter._ip_buckets["127.0.0.1"]) == 2
    assert len(limiter._email_buckets["user@example.com"]) == 2


def test_registration_bucket_is_separate_and_records_successes():
    limiter = _limiter()

    assert limiter.is_registration_allowed("127.0.0.1") is True
    limiter.record_registration("127.0.0.1")
    limiter.record_registration("127.0.0.1")

    assert limiter.is_registration_allowed("127.0.0.1") is False
    assert limiter.is_allowed("127.0.0.1", "user@example.com") is True


def test_registration_bucket_uses_registration_window():
    now = [100.0]
    limiter = _limiter(now)
    limiter.record_registration("127.0.0.1")
    limiter.record_registration("127.0.0.1")

    now[0] = 121.0
    assert limiter.is_registration_allowed("127.0.0.1") is False

    now[0] = 131.0
    assert limiter.is_registration_allowed("127.0.0.1") is True


def test_only_touched_buckets_are_trimmed():
    now = [100.0]
    limiter = _limiter(now)
    limiter.record_failure("127.0.0.1", "expired@example.com")
    limiter.record_failure("127.0.0.2", "current@example.com")

    now[0] = 111.0
    assert limiter.is_allowed("127.0.0.2", "current@example.com") is True

    assert "127.0.0.1:expired@example.com" in limiter._email_ip_buckets
    assert "127.0.0.2:current@example.com" not in limiter._email_ip_buckets


def test_bucket_cap_drops_new_buckets_without_evicting_active_email_buckets(caplog):
    limiter = _limiter()

    for index in range(4):
        limiter.record_failure(f"127.0.0.{index}", f"user{index}@example.com")

    assert len(limiter._email_buckets) == 3
    assert "user0@example.com" in limiter._email_buckets
    assert "Rate limiter email bucket cap reached" in caplog.text


def test_bucket_cap_does_not_block_new_untracked_keys():
    limiter = _limiter()

    for index in range(6):
        limiter.record_failure(
            f"127.0.1.{index}",
            f"user{index}@example.com",
        )

    assert limiter.is_allowed("127.0.1.99", "new-user@example.com") is True


def test_bucket_cap_preserves_existing_email_bucket_during_flood():
    limiter = _limiter()
    for index in range(3):
        limiter.record_failure(f"127.0.2.{index}", "victim@example.com")

    for index in range(10):
        limiter.record_failure(
            f"127.0.3.{index}",
            f"flood{index}@example.com",
        )

    assert limiter.is_allowed("127.0.4.1", "victim@example.com") is False
    assert limiter.is_allowed("127.0.4.2", "brand-new@example.com") is True


def test_registration_bucket_cap_does_not_block_new_untracked_ips():
    limiter = _limiter()

    for index in range(6):
        limiter.record_registration(f"127.0.5.{index}")

    assert limiter.is_registration_allowed("127.0.5.99") is True
    assert "__overflow__" not in limiter._registration_ip_buckets


def test_bucket_cap_reclaims_expired_oldest_buckets():
    now = [100.0]
    limiter = _limiter(now)
    for index in range(3):
        limiter.record_failure(f"127.0.6.{index}", f"user{index}@example.com")

    now[0] = 111.0
    limiter.record_failure("127.0.6.99", "new-user@example.com")

    assert "user0@example.com" not in limiter._email_buckets
    assert "new-user@example.com" in limiter._email_buckets
    assert len(limiter._email_buckets) == 3


def test_reset_allows_bucket_cap_warning_to_be_logged_again(caplog):
    limiter = _limiter()
    for index in range(4):
        limiter.record_failure(f"127.0.7.{index}", f"user{index}@example.com")
    limiter.reset()

    for index in range(4):
        limiter.record_failure(f"127.0.8.{index}", f"other{index}@example.com")

    assert caplog.text.count("Rate limiter email bucket cap reached") == 2


def test_is_allowed_does_not_refresh_bucket_lru_order():
    limiter = _limiter()
    for index in range(3):
        limiter.record_failure(f"127.0.0.{index}", f"user{index}@example.com")

    limiter.is_allowed("127.0.0.0", "user0@example.com")

    assert list(limiter._ip_buckets.keys()) == [
        "127.0.0.0",
        "127.0.0.1",
        "127.0.0.2",
    ]


def test_record_failure_refreshes_bucket_lru_order():
    limiter = _limiter()
    for index in range(3):
        limiter.record_failure(f"127.0.9.{index}", f"user{index}@example.com")

    limiter.record_failure("127.0.9.0", "user0@example.com")

    assert list(limiter._ip_buckets.keys()) == [
        "127.0.9.1",
        "127.0.9.2",
        "127.0.9.0",
    ]


def test_reset_clears_all_buckets():
    limiter = _limiter()
    limiter.record_failure("127.0.0.1", "user@example.com")
    limiter.record_registration("127.0.0.1")

    limiter.reset()

    assert limiter._email_ip_buckets == {}
    assert limiter._ip_buckets == {}
    assert limiter._email_buckets == {}
    assert limiter._registration_ip_buckets == {}
