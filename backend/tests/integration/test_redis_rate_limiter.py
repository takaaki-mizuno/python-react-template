import asyncio
import os
import subprocess
import sys
import textwrap
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
import redis.asyncio as redis

from app.libraries.redis_login_rate_limiter import RedisLoginRateLimiter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.redis_rate_limiter,
    pytest.mark.asyncio,
]

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _redis_url() -> str:
    redis_url = os.getenv("TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("TEST_REDIS_URL is required for Redis rate limiter integration tests")
    return redis_url


def _limiter(
    redis_client,
    prefix: str,
    *,
    window_seconds: int = 10,
    operation_deadline_seconds: float = 0.8,
    circuit_breaker_failures: int = 5,
) -> RedisLoginRateLimiter:
    return RedisLoginRateLimiter(
        window_seconds=window_seconds,
        registration_window_seconds=30,
        max_failures_per_email_ip=2,
        max_failures_per_ip=3,
        max_failures_per_email=3,
        max_registrations_per_ip=2,
        max_oidc_authorizations_per_ip=2,
        redis_client=redis_client,
        key_prefix=prefix,
        unavailable_policy="fail_closed",
        operation_deadline_seconds=operation_deadline_seconds,
        circuit_breaker_failures=circuit_breaker_failures,
        circuit_breaker_cooldown_seconds=10,
    )


@pytest_asyncio.fixture
async def redis_context():
    client = redis.Redis.from_url(
        _redis_url(),
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
        max_connections=5,
    )
    prefix = f"test:auth:rate_limit:{uuid4().hex}"
    limiter = _limiter(client, prefix)
    try:
        yield client, prefix, limiter
    finally:
        await limiter.reset_for_tests()
        await client.aclose()


async def test_redis_rate_limiter_shares_state_between_two_instances(redis_context) -> None:
    client, prefix, first_limiter = redis_context
    second_limiter = _limiter(client, prefix)

    await first_limiter.record_failure("127.0.0.1", "user@example.com")
    await first_limiter.record_failure("127.0.0.1", "user@example.com")

    assert await second_limiter.is_allowed("127.0.0.1", "user@example.com") is False


async def test_redis_rate_limiter_shares_state_across_processes(redis_context) -> None:
    _client, prefix, parent_limiter = redis_context
    script = textwrap.dedent(f"""
        import asyncio
        import os
        import redis.asyncio as redis

        from app.libraries.redis_login_rate_limiter import RedisLoginRateLimiter

        async def main():
            client = redis.Redis.from_url(os.environ["TEST_REDIS_URL"], max_connections=2)
            limiter = RedisLoginRateLimiter(
                window_seconds=10,
                registration_window_seconds=30,
                max_failures_per_email_ip=2,
                max_failures_per_ip=3,
                max_failures_per_email=3,
                max_registrations_per_ip=2,
                max_oidc_authorizations_per_ip=2,
                redis_client=client,
                key_prefix={ prefix!r },
                unavailable_policy="fail_closed",
                operation_deadline_seconds=0.8,
                circuit_breaker_failures=5,
                circuit_breaker_cooldown_seconds=10,
            )
            await limiter.record_failure("127.0.0.1", "user@example.com")
            await limiter.record_failure("127.0.0.1", "user@example.com")
            await client.aclose()

        asyncio.run(main())
    """)

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=BACKEND_DIR,
        env={
            **os.environ, "TEST_REDIS_URL": _redis_url()
        },
    )

    assert await parent_limiter.is_allowed("127.0.0.1", "user@example.com") is False


async def test_redis_rate_limiter_scores_are_redis_epoch_seconds(redis_context) -> None:
    client, _prefix, limiter = redis_context
    before_seconds, _ = await client.time()

    await limiter.record_failure("127.0.0.1", "user@example.com")

    key = limiter._bucket_key("email_ip", "127.0.0.1:user@example.com")
    scored_members = await client.zrange(key, 0, -1, withscores=True)
    after_seconds, _ = await client.time()
    assert scored_members
    score = scored_members[0][1]
    assert float(before_seconds) <= score <= float(after_seconds) + 1
    assert score > 1_700_000_000


async def test_redis_deadline_timeout_does_not_poison_next_command_response() -> None:
    client = redis.Redis.from_url(
        _redis_url(),
        max_connections=1,
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
    )
    key = f"test:auth:rate_limit:blocking:{uuid4().hex}"
    marker_key = f"{key}:marker"
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(client.blpop(key, timeout=1), timeout=0.05)

        assert await client.ping() is True
        assert await client.set(marker_key, "ok") is True
    finally:
        await client.delete(key, marker_key)
        await client.aclose()


async def test_redis_pool_exhaustion_does_not_open_breaker_with_real_pool() -> None:
    pool = redis.BlockingConnectionPool.from_url(
        _redis_url(),
        max_connections=1,
        timeout=0.05,
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
    )
    client = redis.Redis.from_pool(pool)
    prefix = f"test:auth:rate_limit:pool:{uuid4().hex}"
    blocking_key = f"{prefix}:blocking"
    limiter = _limiter(
        client,
        prefix,
        window_seconds=10,
        operation_deadline_seconds=0.2,
        circuit_breaker_failures=1,
    )
    blocking_task = asyncio.create_task(client.blpop(blocking_key, timeout=1))
    try:
        await asyncio.sleep(0.05)

        assert await limiter.is_allowed("127.0.0.1", "user@example.com") is False

        blocking_task.cancel()
        with suppress(asyncio.CancelledError):
            await blocking_task

        assert await limiter.is_allowed("127.0.0.1", "user@example.com") is True
    finally:
        blocking_task.cancel()
        with suppress(asyncio.CancelledError):
            await blocking_task
        await client.delete(blocking_key)
        await limiter.reset_for_tests()
        await client.aclose()


async def test_redis_rate_limiter_record_success_on_one_instance_clears_email_ip_for_other_instance(
    redis_context, ) -> None:
    client, prefix, first_limiter = redis_context
    second_limiter = _limiter(client, prefix)
    await first_limiter.record_failure("127.0.0.1", "user@example.com")
    await first_limiter.record_failure("127.0.0.1", "user@example.com")

    await second_limiter.record_success("127.0.0.1", "user@example.com")

    assert await first_limiter.is_allowed("127.0.0.1", "user@example.com") is True


async def test_redis_rate_limiter_window_expires_across_instances(redis_context) -> None:
    client, prefix, first_limiter = redis_context
    first_limiter = _limiter(client, prefix, window_seconds=1)
    second_limiter = _limiter(client, prefix, window_seconds=1)
    await first_limiter.record_failure("127.0.0.1", "user@example.com")
    await first_limiter.record_failure("127.0.0.1", "user@example.com")
    assert await second_limiter.is_allowed("127.0.0.1", "user@example.com") is False

    await asyncio.sleep(1.1)

    assert await second_limiter.is_allowed("127.0.0.1", "user@example.com") is True
