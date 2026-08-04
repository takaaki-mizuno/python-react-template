import logging
from collections import OrderedDict, deque
from collections.abc import Callable
from time import monotonic

from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface

logger = logging.getLogger(__name__)


class InMemoryLoginRateLimiter(LoginRateLimiterInterface):

    def __init__(
        self,
        window_seconds: int,
        registration_window_seconds: int,
        max_failures_per_email_ip: int,
        max_failures_per_ip: int,
        max_failures_per_email: int,
        max_registrations_per_ip: int,
        max_buckets_per_scope: int,
        clock: Callable[[], float] = monotonic,
    ):
        self._window_seconds = window_seconds
        self._registration_window_seconds = registration_window_seconds
        self._max_failures_per_email_ip = max_failures_per_email_ip
        self._max_failures_per_ip = max_failures_per_ip
        self._max_failures_per_email = max_failures_per_email
        self._max_registrations_per_ip = max_registrations_per_ip
        self._max_buckets_per_scope = max_buckets_per_scope
        self._clock = clock
        self._email_ip_buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._ip_buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._email_buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._registration_ip_buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._cap_warning_scopes: set[str] = set()

    def is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        now = self._clock()
        email_ip_bucket = self._get_existing_bucket(
            self._email_ip_buckets,
            self._email_ip_key(ip_address, normalized_email),
            now,
            self._window_seconds,
        )
        ip_bucket = self._get_existing_bucket(self._ip_buckets, ip_address, now,
                                              self._window_seconds)
        email_bucket = self._get_existing_bucket(
            self._email_buckets,
            normalized_email,
            now,
            self._window_seconds,
        )

        return (len(email_ip_bucket) < self._max_failures_per_email_ip
                and len(ip_bucket) < self._max_failures_per_ip
                and len(email_bucket) < self._max_failures_per_email)

    def is_account_deletion_reauth_allowed(
        self,
        ip_address: str,
        normalized_email: str,
    ) -> bool:
        now = self._clock()
        email_ip_bucket = self._get_existing_bucket(
            self._email_ip_buckets,
            self._email_ip_key(ip_address, normalized_email),
            now,
            self._window_seconds,
        )
        ip_bucket = self._get_existing_bucket(self._ip_buckets, ip_address, now,
                                              self._window_seconds)

        return (len(email_ip_bucket) < self._max_failures_per_email_ip
                and len(ip_bucket) < self._max_failures_per_ip)

    def record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool = True,
    ) -> None:
        now = self._clock()
        email_ip_bucket = self._get_or_create_bucket(
            self._email_ip_buckets,
            self._email_ip_key(ip_address, normalized_email),
            now,
            self._window_seconds,
            "email_ip",
        )
        if email_ip_bucket is not None:
            email_ip_bucket.append(now)
        ip_bucket = self._get_or_create_bucket(self._ip_buckets, ip_address, now,
                                               self._window_seconds, "ip")
        if ip_bucket is not None:
            ip_bucket.append(now)
        if include_email_bucket:
            email_bucket = self._get_or_create_bucket(
                self._email_buckets,
                normalized_email,
                now,
                self._window_seconds,
                "email",
            )
            if email_bucket is not None:
                email_bucket.append(now)

    def record_success(self, ip_address: str, normalized_email: str) -> None:
        self._email_ip_buckets.pop(self._email_ip_key(ip_address, normalized_email), None)

    def is_registration_allowed(self, ip_address: str) -> bool:
        now = self._clock()
        bucket = self._get_existing_bucket(
            self._registration_ip_buckets,
            ip_address,
            now,
            self._registration_window_seconds,
        )
        return len(bucket) < self._max_registrations_per_ip

    def record_registration(self, ip_address: str) -> None:
        now = self._clock()
        bucket = self._get_or_create_bucket(
            self._registration_ip_buckets,
            ip_address,
            now,
            self._registration_window_seconds,
            "registration_ip",
        )
        if bucket is not None:
            bucket.append(now)

    def reset(self) -> None:
        self._email_ip_buckets.clear()
        self._ip_buckets.clear()
        self._email_buckets.clear()
        self._registration_ip_buckets.clear()
        self._cap_warning_scopes.clear()

    def _get_existing_bucket(
        self,
        buckets: OrderedDict[str, deque[float]],
        key: str,
        now: float,
        window_seconds: int,
    ) -> deque[float]:
        bucket = buckets.get(key)
        if bucket is None:
            return deque()
        self._trim(bucket, now, window_seconds)
        if not bucket:
            del buckets[key]
            return deque()
        return bucket

    def _get_or_create_bucket(
        self,
        buckets: OrderedDict[str, deque[float]],
        key: str,
        now: float,
        window_seconds: int,
        scope_name: str,
    ) -> deque[float] | None:
        bucket = self._get_existing_bucket(buckets, key, now, window_seconds)
        if bucket:
            buckets.move_to_end(key)
            return bucket
        if len(buckets) >= self._max_buckets_per_scope:
            self._evict_expired_buckets(buckets, now, window_seconds)
        if len(buckets) >= self._max_buckets_per_scope:
            self._warn_bucket_cap_reached(scope_name)
            return None
        bucket = deque()
        buckets[key] = bucket
        return bucket

    def _trim(self, bucket: deque[float], now: float, window_seconds: int) -> None:
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

    def _evict_expired_buckets(
        self,
        buckets: OrderedDict[str, deque[float]],
        now: float,
        window_seconds: int,
    ) -> None:
        while buckets and len(buckets) >= self._max_buckets_per_scope:
            key, bucket = next(iter(buckets.items()))
            self._trim(bucket, now, window_seconds)
            if not bucket:
                del buckets[key]
                continue
            return

    def _warn_bucket_cap_reached(self, scope_name: str) -> None:
        if scope_name not in self._cap_warning_scopes:
            logger.warning(
                "Rate limiter %s bucket cap reached; dropping new bucket",
                scope_name,
            )
            self._cap_warning_scopes.add(scope_name)

    def _email_ip_key(self, ip_address: str, normalized_email: str) -> str:
        return f"{ip_address}:{normalized_email}"
