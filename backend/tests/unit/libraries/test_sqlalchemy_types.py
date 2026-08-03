from ipaddress import IPv4Address, IPv6Address

import pytest

from app.libraries.sqlalchemy_types import InetString


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
