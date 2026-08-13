import asyncio
import fnmatch
import logging
from collections.abc import AsyncIterator

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.libraries.redis_login_rate_limiter import RedisLoginRateLimiter

pytestmark = pytest.mark.asyncio


def _constant_breaker_clock() -> float:
    return 0.0


class FakePipeline:

    def __init__(self, redis_client: "FakeRedis", *, transaction: bool) -> None:
        self._redis = redis_client
        self.transaction = transaction
        self.commands: list[tuple] = []

    def zcount(self, key: str, minimum, maximum) -> "FakePipeline":
        self.commands.append(("zcount", key, minimum, maximum))
        return self

    def zremrangebyscore(self, key: str, minimum, maximum) -> "FakePipeline":
        self.commands.append(("zremrangebyscore", key, minimum, maximum))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> "FakePipeline":
        self.commands.append(("zadd", key, mapping))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self.commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list:
        if self._redis.execute_exception is not None:
            raise self._redis.execute_exception
        if self._redis.block_execute_event is not None:
            await self._redis.block_execute_event.wait()
        self._redis.executed_pipelines.append(self)
        results = []
        for command in self.commands:
            name = command[0]
            if name == "zcount":
                _, key, minimum, maximum = command
                results.append(self._redis.zcount_sync(key, minimum, maximum))
            elif name == "zremrangebyscore":
                _, key, minimum, maximum = command
                results.append(self._redis.zremrangebyscore_sync(key, minimum, maximum))
            elif name == "zadd":
                _, key, mapping = command
                results.append(self._redis.zadd_sync(key, mapping))
            elif name == "expire":
                _, key, seconds = command
                self._redis.expirations[key] = seconds
                results.append(True)
        return results


class FakeRedis:

    def __init__(self) -> None:
        self.now_seconds = 100
        self.now_microseconds = 0
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.expirations: dict[str, int] = {}
        self.deleted_keys: list[str] = []
        self.created_pipelines: list[FakePipeline] = []
        self.executed_pipelines: list[FakePipeline] = []
        self.time_calls = 0
        self.time_exception: Exception | None = None
        self.execute_exception: Exception | None = None
        self.block_time_event: asyncio.Event | None = None
        self.block_execute_event: asyncio.Event | None = None
        self.closed = False

    async def time(self) -> tuple[int, int]:
        self.time_calls += 1
        if self.time_exception is not None:
            raise self.time_exception
        if self.block_time_event is not None:
            await self.block_time_event.wait()
        return self.now_seconds, self.now_microseconds

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        pipeline = FakePipeline(self, transaction=transaction)
        self.created_pipelines.append(pipeline)
        return pipeline

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.sorted_sets:
                deleted += 1
                del self.sorted_sets[key]
            self.deleted_keys.append(key)
        return deleted

    async def scan_iter(self, match: str, count: int = 100) -> AsyncIterator[str]:
        del count
        for key in list(self.sorted_sets):
            if fnmatch.fnmatch(key, match):
                yield key

    async def aclose(self) -> None:
        self.closed = True

    def zcount_sync(self, key: str, minimum, maximum) -> int:
        min_score = float(minimum)
        max_score = float("inf") if maximum == "+inf" else float(maximum)
        return sum(min_score <= score <= max_score
                   for score in self.sorted_sets.get(key, {}).values())

    def zremrangebyscore_sync(self, key: str, minimum, maximum) -> int:
        del minimum
        exclusive = isinstance(maximum, str) and maximum.startswith("(")
        max_score = float(maximum[1:] if exclusive else maximum)
        bucket = self.sorted_sets.get(key, {})
        removed_members = [
            member for member, score in bucket.items()
            if (score < max_score if exclusive else score <= max_score)
        ]
        for member in removed_members:
            del bucket[member]
        if not bucket and key in self.sorted_sets:
            del self.sorted_sets[key]
        return len(removed_members)

    def zadd_sync(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.sorted_sets.setdefault(key, {})
        before = len(bucket)
        bucket.update(mapping)
        return len(bucket) - before


def _limiter(
    redis_client: FakeRedis,
    *,
    unavailable_policy: str = "fail_closed",
    operation_deadline_seconds: float = 0.1,
    circuit_breaker_failures: int = 2,
    circuit_breaker_cooldown_seconds: float = 1.0,
    breaker_clock=None,
) -> RedisLoginRateLimiter:
    if breaker_clock is None:
        breaker_clock = _constant_breaker_clock
    return RedisLoginRateLimiter(
        window_seconds=10,
        registration_window_seconds=30,
        max_failures_per_email_ip=2,
        max_failures_per_ip=3,
        max_failures_per_email=3,
        max_registrations_per_ip=2,
        max_oidc_authorizations_per_ip=2,
        redis_client=redis_client,
        key_prefix="test:auth:rate_limit",
        unavailable_policy=unavailable_policy,
        operation_deadline_seconds=operation_deadline_seconds,
        circuit_breaker_failures=circuit_breaker_failures,
        circuit_breaker_cooldown_seconds=circuit_breaker_cooldown_seconds,
        breaker_clock=breaker_clock,
    )


async def test_is_allowed_uses_redis_time_and_pipelined_zcount_without_writes() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True

    pipeline = redis_client.executed_pipelines[0]
    assert redis_client.time_calls == 1
    assert [command[0] for command in pipeline.commands] == ["zcount", "zcount", "zcount"]
    assert pipeline.transaction is False


async def test_is_allowed_counts_window_start_inclusively() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)
    key = limiter._bucket_key("email_ip", "127.0.0.1:user@example.com")
    redis_client.sorted_sets[key] = {"outside": 89.999, "boundary": 90.0}

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True

    redis_client.sorted_sets[key]["inside"] = 99.0

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False


async def test_record_failure_trims_scores_strictly_older_than_window_start() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)
    key = limiter._bucket_key("email_ip", "127.0.0.1:user@example.com")
    redis_client.sorted_sets[key] = {"outside": 89.999, "boundary": 90.0}

    await limiter.record_failure("127.0.0.1", "user@example.com")

    scores = redis_client.sorted_sets[key].values()
    assert 89.999 not in scores
    assert 90.0 in scores
    assert 100.0 in scores


async def test_record_failure_blocks_by_email_ip_bucket() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    await limiter.record_failure("127.0.0.1", "user@example.com")
    await limiter.record_failure("127.0.0.1", "user@example.com")

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False


async def test_record_failure_blocks_by_ip_bucket_across_emails() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    await limiter.record_failure("127.0.0.1", "a@example.com")
    await limiter.record_failure("127.0.0.1", "b@example.com")
    await limiter.record_failure("127.0.0.1", "c@example.com")

    assert await limiter.is_allowed("127.0.0.1", "d@example.com") is False


async def test_record_failure_blocks_by_email_bucket_across_ips() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    await limiter.record_failure("127.0.0.1", "user@example.com")
    await limiter.record_failure("127.0.0.2", "user@example.com")
    await limiter.record_failure("127.0.0.3", "user@example.com")

    assert await limiter.is_allowed("127.0.0.4", "user@example.com") is False


async def test_register_style_failure_can_skip_email_bucket() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    for index in range(4):
        await limiter.record_failure(
            f"127.0.0.{index}",
            "victim@example.com",
            include_email_bucket=False,
        )

    assert await limiter.is_allowed("127.0.0.10", "victim@example.com") is True


async def test_account_deletion_reauth_allowed_ignores_email_only_bucket() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    for index in range(3):
        await limiter.record_failure(f"127.0.10.{index}", "victim@example.com")

    assert await limiter.is_allowed("127.0.10.99", "victim@example.com") is False
    assert await limiter.is_account_deletion_reauth_allowed(
        "127.0.10.99",
        "victim@example.com",
    ) is True


async def test_record_success_deletes_only_matching_email_ip_bucket() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)
    await limiter.record_failure("127.0.0.1", "user@example.com")
    await limiter.record_failure("127.0.0.1", "other@example.com")
    await limiter.record_failure("127.0.0.2", "user@example.com")

    await limiter.record_success("127.0.0.1", "user@example.com")

    matching_key = limiter._bucket_key("email_ip", "127.0.0.1:user@example.com")
    other_key = limiter._bucket_key("email_ip", "127.0.0.1:other@example.com")
    assert matching_key in redis_client.deleted_keys
    assert other_key not in redis_client.deleted_keys


async def test_registration_bucket_uses_registration_window() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)
    await limiter.record_registration("127.0.0.1")
    await limiter.record_registration("127.0.0.1")

    assert await limiter.is_registration_allowed("127.0.0.1") is False
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True


async def test_oidc_authorization_bucket_uses_auth_window() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)
    await limiter.record_oidc_authorization("127.0.11.1")
    await limiter.record_oidc_authorization("127.0.11.1")

    assert await limiter.is_oidc_authorization_allowed("127.0.11.1") is False
    assert await limiter.is_registration_allowed("127.0.11.1") is True


async def test_redis_keys_do_not_contain_raw_email_or_ip() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    await limiter.record_failure("127.0.0.1", "user@example.com")

    assert redis_client.sorted_sets
    for key in redis_client.sorted_sets:
        assert "user@example.com" not in key
        assert "127.0.0.1" not in key


async def test_redis_unavailable_fail_closed_blocks_checks_and_logs_unavailable_code(
        caplog) -> None:
    redis_client = FakeRedis()
    redis_client.time_exception = OSError("redis unavailable")
    limiter = _limiter(redis_client, unavailable_policy="fail_closed")

    with caplog.at_level(logging.WARNING):
        assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False

    assert "auth_rate_limiter.redis_unavailable" in caplog.text
    assert "user@example.com" not in caplog.text
    assert "127.0.0.1" not in caplog.text


async def test_redis_unavailable_fail_open_allows_checks_and_drops_records() -> None:
    redis_client = FakeRedis()
    redis_client.time_exception = OSError("redis unavailable")
    limiter = _limiter(redis_client, unavailable_policy="fail_open")

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True
    await limiter.record_failure("127.0.0.1", "user@example.com")

    assert redis_client.sorted_sets == {}


async def test_operation_deadline_limits_total_redis_wait() -> None:
    redis_client = FakeRedis()
    redis_client.block_time_event = asyncio.Event()
    limiter = _limiter(redis_client, operation_deadline_seconds=0.01)

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False


async def test_deadline_timeout_marks_operation_unavailable_without_running_later_pipeline_commands(
) -> None:
    redis_client = FakeRedis()
    redis_client.block_execute_event = asyncio.Event()
    limiter = _limiter(redis_client, operation_deadline_seconds=0.01)

    await limiter.record_failure("127.0.0.1", "user@example.com")

    assert redis_client.executed_pipelines == []
    assert redis_client.sorted_sets == {}


async def test_circuit_breaker_skips_redis_until_cooldown_expires() -> None:
    redis_client = FakeRedis()
    redis_client.time_exception = OSError("redis unavailable")
    now = [0.0]
    limiter = _limiter(
        redis_client,
        circuit_breaker_failures=1,
        circuit_breaker_cooldown_seconds=1.0,
        breaker_clock=lambda: now[0],
    )

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False
    redis_client.time_exception = None
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False
    assert redis_client.time_calls == 1

    now[0] = 1.1
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True
    assert redis_client.time_calls == 2


@pytest.mark.parametrize("message", ["Too many connections", "No connection available."])
async def test_pool_exhaustion_does_not_open_circuit_breaker(message: str) -> None:
    redis_client = FakeRedis()
    redis_client.time_exception = RedisConnectionError(message)
    limiter = _limiter(redis_client, circuit_breaker_failures=1)

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False

    redis_client.time_exception = None
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True
    assert redis_client.time_calls == 2


async def test_pool_exhaustion_logs_are_rate_limited(caplog) -> None:
    redis_client = FakeRedis()
    redis_client.time_exception = RedisConnectionError("No connection available.")
    now = [0.0]
    limiter = _limiter(redis_client, circuit_breaker_failures=1, breaker_clock=lambda: now[0])

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False
        now[0] = 1.1
        assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False

    assert caplog.text.count("auth_rate_limiter.redis_unavailable") == 2


async def test_circuit_breaker_resets_consecutive_failure_count_after_success() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client, circuit_breaker_failures=2)
    redis_client.time_exception = OSError("redis unavailable")
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False
    redis_client.time_exception = None
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True
    redis_client.time_exception = OSError("redis unavailable")
    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False
    redis_client.time_exception = None

    assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True


async def test_record_failure_pipeline_uses_transaction() -> None:
    redis_client = FakeRedis()
    limiter = _limiter(redis_client)

    await limiter.record_failure("127.0.0.1", "user@example.com")

    assert redis_client.created_pipelines[-1].transaction is True


@pytest.mark.parametrize("unavailable_policy", ["fail_open", "fail_closed"])
async def test_record_failure_pipeline_failure_has_documented_policy(
    caplog,
    unavailable_policy: str,
) -> None:
    redis_client = FakeRedis()
    redis_client.execute_exception = OSError("write failed")
    limiter = _limiter(redis_client, unavailable_policy=unavailable_policy)

    with caplog.at_level(logging.WARNING):
        await limiter.record_failure("127.0.0.1", "user@example.com")

    assert "auth_rate_limiter.redis_unavailable" in caplog.text
    assert redis_client.sorted_sets == {}
