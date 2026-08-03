from starlette.requests import Request

from app.libraries.client_ip import parse_trusted_proxy_networks, resolve_client_ip


def _request(
    client_host: str | None,
    forwarded_for: str | None = None,
    forwarded_for_headers: list[str] | None = None,
) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    for header_value in forwarded_for_headers or []:
        headers.append((b"x-forwarded-for", header_value.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": headers,
    }
    if client_host is not None:
        scope["client"] = (client_host, 12345)
    return Request(scope)


def test_resolve_client_ip_ignores_xff_without_trusted_proxy():
    request = _request("203.0.113.10", "198.51.100.99")

    assert resolve_client_ip(request, "") == "203.0.113.10"


def test_resolve_client_ip_uses_xff_only_from_trusted_proxy():
    request = _request("10.0.0.5", "198.51.100.99")

    assert resolve_client_ip(request, "10.0.0.0/8") == "198.51.100.99"


def test_resolve_client_ip_walks_xff_chain_from_the_right():
    request = _request("10.0.0.5", "198.51.100.99, 203.0.113.8, 10.0.0.7")

    assert resolve_client_ip(request, "10.0.0.0/8") == "203.0.113.8"


def test_resolve_client_ip_combines_multiple_xff_headers():
    request = _request(
        "10.0.0.5",
        forwarded_for_headers=["198.51.100.99", "203.0.113.8, 10.0.0.7"],
    )

    assert resolve_client_ip(request, "10.0.0.0/8") == "203.0.113.8"


def test_resolve_client_ip_falls_back_to_direct_peer_for_invalid_rightmost_xff_token():
    request = _request("10.0.0.5", "198.51.100.99, not-an-ip")

    assert resolve_client_ip(request, "10.0.0.0/8") == "10.0.0.5"


def test_resolve_client_ip_uses_valid_rightmost_untrusted_token_before_invalid_left_token():
    request = _request("10.0.0.5", "not-an-ip, 198.51.100.99")

    assert resolve_client_ip(request, "10.0.0.0/8") == "198.51.100.99"


def test_resolve_client_ip_falls_back_to_direct_peer_for_invalid_token_after_trusted_hop():
    request = _request("10.0.0.5", "198.51.100.99, not-an-ip, 10.0.0.7")

    assert resolve_client_ip(request, "10.0.0.0/8") == "10.0.0.5"


def test_resolve_client_ip_falls_back_to_direct_peer_for_trailing_empty_xff_token():
    request = _request("10.0.0.5", "198.51.100.99,")

    assert resolve_client_ip(request, "10.0.0.0/8") == "10.0.0.5"


def test_resolve_client_ip_falls_back_to_direct_peer_when_all_xff_tokens_are_invalid():
    request = _request("10.0.0.5", "not-an-ip, also-invalid")

    assert resolve_client_ip(request, "10.0.0.0/8") == "10.0.0.5"


def test_resolve_client_ip_supports_ipv6_and_cidr():
    request = _request("2001:db8::10", "2001:db8:ffff::1")

    assert resolve_client_ip(request, "2001:db8::/64") == "2001:db8:ffff::1"


def test_resolve_client_ip_supports_ipv4_mapped_proxy_addresses():
    request = _request("::ffff:10.0.0.5", "198.51.100.99")

    assert resolve_client_ip(request, "10.0.0.0/8") == "198.51.100.99"


def test_resolve_client_ip_accepts_ipv4_with_port_in_xff():
    request = _request("10.0.0.5", "198.51.100.99:12345")

    assert resolve_client_ip(request, "10.0.0.0/8") == "198.51.100.99"


def test_resolve_client_ip_accepts_bracketed_ipv6_with_port_in_xff():
    request = _request("2001:db8::10", "[2001:db8:ffff::1]:12345")

    assert resolve_client_ip(request, "2001:db8::/64") == "2001:db8:ffff::1"


def test_resolve_client_ip_returns_none_without_client():
    assert resolve_client_ip(_request(None), "10.0.0.0/8") is None


def test_resolve_client_ip_returns_none_for_invalid_direct_peer():
    assert resolve_client_ip(_request("not-an-ip"), "10.0.0.0/8") is None


def test_parse_trusted_proxy_networks_is_cached():
    parse_trusted_proxy_networks.cache_clear()

    first = parse_trusted_proxy_networks("127.0.0.1,10.0.0.0/8")
    second = parse_trusted_proxy_networks("127.0.0.1,10.0.0.0/8")

    assert first is second
    assert parse_trusted_proxy_networks.cache_info().hits == 1
