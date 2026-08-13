import asyncio
import hashlib
import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from time import monotonic
from typing import Any, Protocol, TypeVar

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface

logger = logging.getLogger(__name__)

_T = TypeVar("_T")
_POOL_EXHAUSTION_WARNING_INTERVAL_SECONDS = 1.0


class _RedisPipeline(Protocol):

    def zcount(self, key: str, minimum, maximum) -> "_RedisPipeline":
        ...

    def zremrangebyscore(self, key: str, minimum, maximum) -> "_RedisPipeline":
        ...

    def zadd(self, key: str, mapping: dict[str, float]) -> "_RedisPipeline":
        ...

    def expire(self, key: str, seconds: int) -> "_RedisPipeline":
        ...

    def execute(self) -> Awaitable[list[Any]]:
        ...


class _RedisClient(Protocol):

    def time(self) -> Awaitable[tuple[int, int]]:
        ...

    def pipeline(self, transaction: bool = True, shard_hint: str | None = None) -> Any:
        ...

    def delete(self, *keys: str | bytes | memoryview) -> Awaitable[int]:
        ...

    def scan_iter(self, match: str, count: int = 100) -> AsyncIterator[str | bytes]:
        ...

    def aclose(self) -> Awaitable[None]:
        ...


class RedisLoginRateLimiter(LoginRateLimiterInterface):

    def __init__(
        self,
        *,
        window_seconds: int,
        registration_window_seconds: int,
        max_failures_per_email_ip: int,
        max_failures_per_ip: int,
        max_failures_per_email: int,
        max_registrations_per_ip: int,
        max_oidc_authorizations_per_ip: int,
        redis_client: _RedisClient,
        key_prefix: str,
        unavailable_policy: str,
        operation_deadline_seconds: float,
        circuit_breaker_failures: int,
        circuit_breaker_cooldown_seconds: float,
        breaker_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._registration_window_seconds = registration_window_seconds
        self._max_failures_per_email_ip = max_failures_per_email_ip
        self._max_failures_per_ip = max_failures_per_ip
        self._max_failures_per_email = max_failures_per_email
        self._max_registrations_per_ip = max_registrations_per_ip
        self._max_oidc_authorizations_per_ip = max_oidc_authorizations_per_ip
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._unavailable_policy = unavailable_policy
        self._operation_deadline_seconds = operation_deadline_seconds
        self._circuit_breaker_failures = circuit_breaker_failures
        self._circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._breaker_clock = breaker_clock
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None
        self._circuit_open_warning_logged = False
        self._pool_exhaustion_warning_logged_at: float | None = None

    async def is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        return await self._run_check_operation(
            "is_allowed",
            lambda: self._is_allowed(ip_address, normalized_email),
        )

    async def is_account_deletion_reauth_allowed(
        self,
        ip_address: str,
        normalized_email: str,
    ) -> bool:
        return await self._run_check_operation(
            "is_account_deletion_reauth_allowed",
            lambda: self._is_account_deletion_reauth_allowed(ip_address, normalized_email),
        )

    async def record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool = True,
    ) -> None:
        await self._run_record_operation(
            "record_failure",
            lambda: self._record_failure(ip_address, normalized_email, include_email_bucket),
        )

    async def record_success(self, ip_address: str, normalized_email: str) -> None:
        await self._run_record_operation(
            "record_success",
            lambda: self._redis.delete(self._email_ip_key(ip_address, normalized_email)),
        )

    async def is_registration_allowed(self, ip_address: str) -> bool:
        return await self._run_check_operation(
            "is_registration_allowed",
            lambda: self._is_registration_allowed(ip_address),
        )

    async def record_registration(self, ip_address: str) -> None:
        await self._run_record_operation(
            "record_registration",
            lambda: self._record(
                [self._bucket_key("registration_ip", ip_address)],
                self._registration_window_seconds,
            ),
        )

    async def is_oidc_authorization_allowed(self, ip_address: str) -> bool:
        return await self._run_check_operation(
            "is_oidc_authorization_allowed",
            lambda: self._is_oidc_authorization_allowed(ip_address),
        )

    async def record_oidc_authorization(self, ip_address: str) -> None:
        await self._run_record_operation(
            "record_oidc_authorization",
            lambda: self._record(
                [self._bucket_key("oidc_authorization_ip", ip_address)],
                self._window_seconds,
            ),
        )

    async def aclose(self) -> None:
        aclose = getattr(self._redis, "aclose", None)
        if aclose is not None:
            await aclose()

    async def reset_for_tests(self) -> None:
        """Delete only this limiter prefix. Intended for Redis integration cleanup."""
        keys = [
            key async for key in self._redis.scan_iter(match=f"{self._key_prefix}:*", count=100)
        ]
        if keys:
            await self._redis.delete(*keys)

    async def _is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        counts = await self._count_active(
            [
                self._email_ip_key(ip_address, normalized_email),
                self._bucket_key("ip", ip_address),
                self._bucket_key("email", normalized_email),
            ],
            self._window_seconds,
        )
        return (counts[0] < self._max_failures_per_email_ip
                and counts[1] < self._max_failures_per_ip
                and counts[2] < self._max_failures_per_email)

    async def _is_account_deletion_reauth_allowed(
        self,
        ip_address: str,
        normalized_email: str,
    ) -> bool:
        counts = await self._count_active(
            [
                self._email_ip_key(ip_address, normalized_email),
                self._bucket_key("ip", ip_address),
            ],
            self._window_seconds,
        )
        return counts[0] < self._max_failures_per_email_ip and counts[1] < self._max_failures_per_ip

    async def _record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool,
    ) -> None:
        keys = [
            self._email_ip_key(ip_address, normalized_email),
            self._bucket_key("ip", ip_address),
        ]
        if include_email_bucket:
            keys.append(self._bucket_key("email", normalized_email))
        await self._record(keys, self._window_seconds)

    async def _is_registration_allowed(self, ip_address: str) -> bool:
        counts = await self._count_active(
            [self._bucket_key("registration_ip", ip_address)],
            self._registration_window_seconds,
        )
        return counts[0] < self._max_registrations_per_ip

    async def _is_oidc_authorization_allowed(self, ip_address: str) -> bool:
        counts = await self._count_active(
            [self._bucket_key("oidc_authorization_ip", ip_address)],
            self._window_seconds,
        )
        return counts[0] < self._max_oidc_authorizations_per_ip

    async def _count_active(self, keys: Sequence[str], window_seconds: int) -> list[int]:
        now = await self._redis_time_seconds()
        window_start = now - window_seconds
        pipeline = self._redis.pipeline(transaction=False)
        for key in keys:
            pipeline.zcount(key, window_start, "+inf")
        return [int(count) for count in await pipeline.execute()]

    async def _record(self, keys: Sequence[str], window_seconds: int) -> None:
        now = await self._redis_time_seconds()
        window_start = now - window_seconds
        pipeline = self._redis.pipeline(transaction=True)
        expires_in = int(window_seconds) + 1
        for key in keys:
            member = f"{now:.6f}:{secrets.token_hex(8)}"
            pipeline.zremrangebyscore(key, "-inf", f"({window_start}")
            pipeline.zadd(key, {member: now})
            pipeline.expire(key, expires_in)
        await pipeline.execute()

    async def _redis_time_seconds(self) -> float:
        seconds, microseconds = await self._redis.time()
        return float(seconds) + float(microseconds) / 1_000_000

    def _email_ip_key(self, ip_address: str, normalized_email: str) -> str:
        return self._bucket_key("email_ip", f"{ip_address}:{normalized_email}")

    def _bucket_key(self, scope: str, raw_key: str) -> str:
        digest = hashlib.sha256(f"{scope}:{raw_key}".encode()).hexdigest()
        return f"{self._key_prefix}:{scope}:{digest}"

    async def _run_check_operation(
        self,
        operation: str,
        operation_factory: Callable[[], Awaitable[bool]],
    ) -> bool:
        result = await self._run_operation(operation, operation_factory)
        if result is not None:
            return result
        return self._unavailable_policy == "fail_open"

    async def _run_record_operation(
        self,
        operation: str,
        operation_factory: Callable[[], Awaitable[object]],
    ) -> None:
        await self._run_operation(operation, operation_factory)

    async def _run_operation(
        self,
        operation: str,
        operation_factory: Callable[[], Awaitable[_T]],
    ) -> _T | None:
        if self._circuit_is_open():
            self._log_unavailable(operation)
            return None
        try:
            result = await asyncio.wait_for(
                operation_factory(),
                timeout=self._operation_deadline_seconds,
            )
        except (RedisError, TimeoutError, OSError) as error:
            if self._is_pool_exhaustion(error):
                self._log_pool_exhaustion(operation)
                return None
            self._mark_failure(operation)
            return None
        self._mark_success()
        return result

    def _is_pool_exhaustion(self, error: BaseException) -> bool:
        if not isinstance(error, RedisConnectionError):
            return False
        message = str(error)
        return "Too many connections" in message or "No connection available" in message

    def _circuit_is_open(self) -> bool:
        if self._circuit_opened_at is None:
            return False
        if self._breaker_clock() - self._circuit_opened_at < self._circuit_breaker_cooldown_seconds:
            return True
        self._circuit_opened_at = None
        self._circuit_open_warning_logged = False
        return False

    def _mark_failure(self, operation: str) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_breaker_failures:
            self._circuit_opened_at = self._breaker_clock()
            self._circuit_open_warning_logged = False
        self._log_unavailable(operation)

    def _mark_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None
        self._circuit_open_warning_logged = False

    def _log_unavailable(self, operation: str) -> None:
        if self._circuit_opened_at is not None and self._circuit_open_warning_logged:
            return
        self._emit_unavailable_warning(operation)
        if self._circuit_opened_at is not None:
            self._circuit_open_warning_logged = True

    def _log_pool_exhaustion(self, operation: str) -> None:
        now = self._breaker_clock()
        if (self._pool_exhaustion_warning_logged_at is not None
                and now - self._pool_exhaustion_warning_logged_at
                < _POOL_EXHAUSTION_WARNING_INTERVAL_SECONDS):
            return
        self._emit_unavailable_warning(operation)
        self._pool_exhaustion_warning_logged_at = now

    def _emit_unavailable_warning(self, operation: str) -> None:
        logger.warning(
            "auth_rate_limiter.redis_unavailable policy=%s operation=%s",
            self._unavailable_policy,
            operation,
        )
