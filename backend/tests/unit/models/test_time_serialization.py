from datetime import UTC, datetime

import pytest

from app.models.time_serialization import unix_timestamp_seconds


def test_unix_timestamp_seconds_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        unix_timestamp_seconds(datetime(2026, 1, 1, 0, 0, 0))


def test_unix_timestamp_seconds_floors_before_epoch() -> None:
    assert unix_timestamp_seconds(datetime(1969, 12, 31, 23, 59, 59, 500000, tzinfo=UTC)) == -1
