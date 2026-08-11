from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address

import pytest

from app.libraries.sqlalchemy_types import InetString, UnixTimestampMillis


def test_inet_string_accepts_valid_ipv4_string():
    assert InetString().process_bind_param("192.0.2.1", None) == "192.0.2.1"


def test_inet_string_converts_ipv4_result_to_string():
    assert InetString().process_result_value(IPv4Address("192.0.2.1"), None) == "192.0.2.1"


def test_inet_string_converts_ipv6_result_to_string():
    assert InetString().process_result_value(IPv6Address("2001:db8::1"), None) == "2001:db8::1"


def test_inet_string_strips_ipv6_scope_id_before_binding():
    assert InetString().process_bind_param("fe80::1%lo0", None) == "fe80::1"


def test_inet_string_keeps_none_values():
    inet_string = InetString()

    assert inet_string.process_bind_param(None, None) is None
    assert inet_string.process_result_value(None, None) is None


def test_inet_string_rejects_invalid_ip_string():
    with pytest.raises(ValueError):
        InetString().process_bind_param("invalid-ip", None)


def test_unix_timestamp_millis_binds_aware_datetime_as_integer_milliseconds():
    value = datetime(2026, 8, 11, 1, 2, 3, 456000, tzinfo=UTC)

    assert UnixTimestampMillis().process_bind_param(value, None) == 1786410123456


def test_unix_timestamp_millis_restores_integer_milliseconds_to_utc_datetime():
    assert UnixTimestampMillis().process_result_value(1786410123456, None) == datetime(2026,
                                                                                       8,
                                                                                       11,
                                                                                       1,
                                                                                       2,
                                                                                       3,
                                                                                       456000,
                                                                                       tzinfo=UTC)


def test_unix_timestamp_millis_truncates_sub_millisecond_microseconds():
    value = datetime(2026, 8, 11, 1, 2, 3, 456789, tzinfo=UTC)
    timestamp = UnixTimestampMillis().process_bind_param(value, None)

    assert timestamp == 1786410123456
    assert UnixTimestampMillis().process_result_value(timestamp, None) == datetime(2026,
                                                                                   8,
                                                                                   11,
                                                                                   1,
                                                                                   2,
                                                                                   3,
                                                                                   456000,
                                                                                   tzinfo=UTC)


def test_unix_timestamp_millis_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware datetime"):
        UnixTimestampMillis().process_bind_param(datetime(2026, 8, 11, 1, 2, 3), None)


def test_unix_timestamp_millis_keeps_none_values():
    timestamp_type = UnixTimestampMillis()

    assert timestamp_type.process_bind_param(None, None) is None
    assert timestamp_type.process_result_value(None, None) is None
