from collections import deque
from collections.abc import Callable
from time import monotonic


class InMemoryLoginRateLimiter:

    def __init__(
        self,
        window_seconds: int,
        max_attempts_per_email_ip: int,
        max_attempts_per_ip: int,
        clock: Callable[[], float] = monotonic,
    ):
        self._window_seconds = window_seconds
        self._max_attempts_per_email_ip = max_attempts_per_email_ip
        self._max_attempts_per_ip = max_attempts_per_ip
        self._clock = clock
        self._email_ip_buckets: dict[str, deque[float]] = {}
        self._ip_buckets: dict[str, deque[float]] = {}

    def allow(self, ip_address: str, normalized_email: str) -> bool:
        now = self._clock()
        self._cleanup_expired_buckets(now)
        email_ip_key = f"{ip_address}:{normalized_email}"
        email_ip_bucket = self._email_ip_buckets.setdefault(
            email_ip_key, deque())
        ip_bucket = self._ip_buckets.setdefault(ip_address, deque())

        if len(email_ip_bucket) >= self._max_attempts_per_email_ip:
            return False
        if len(ip_bucket) >= self._max_attempts_per_ip:
            return False

        email_ip_bucket.append(now)
        ip_bucket.append(now)
        return True

    def _cleanup_expired_buckets(self, now: float) -> None:
        for buckets in (self._email_ip_buckets, self._ip_buckets):
            for key, bucket in list(buckets.items()):
                self._trim(bucket, now)
                if not bucket:
                    del buckets[key]

    def _trim(self, bucket: deque[float], now: float) -> None:
        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()

    def reset(self) -> None:
        self._email_ip_buckets.clear()
        self._ip_buckets.clear()
