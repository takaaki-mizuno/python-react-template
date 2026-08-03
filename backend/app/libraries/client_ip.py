from functools import lru_cache
from ipaddress import _BaseAddress, _BaseNetwork, ip_address, ip_network

from starlette.requests import Request


@lru_cache(maxsize=128)
def parse_trusted_proxy_networks(trusted_proxy_ips: str) -> tuple[_BaseNetwork, ...]:
    networks: list[_BaseNetwork] = []
    for raw_value in trusted_proxy_ips.split(","):
        value = raw_value.strip()
        if not value:
            continue
        networks.append(ip_network(value, strict=False))
    return tuple(networks)


def resolve_client_ip(request: Request, trusted_proxy_ips: str) -> str | None:
    direct_ip = _parse_direct_client_ip(request)
    if direct_ip is None:
        return None

    trusted_networks = parse_trusted_proxy_networks(trusted_proxy_ips)
    if not trusted_networks or not _is_trusted(direct_ip, trusted_networks):
        return str(direct_ip)

    forwarded_for = ",".join(request.headers.getlist("x-forwarded-for"))
    if not forwarded_for:
        return str(direct_ip)

    return str(_resolve_forwarded_for_client_ip(
        forwarded_for,
        trusted_networks,
        direct_ip,
    ))


def get_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:512] if user_agent else None


def _parse_direct_client_ip(request: Request) -> _BaseAddress | None:
    if not request.client:
        return None
    try:
        return _normalize_ip_address(ip_address(request.client.host))
    except ValueError:
        return None


def _parse_forwarded_for_ip(value: str) -> _BaseAddress:
    try:
        return _normalize_ip_address(ip_address(value))
    except ValueError:
        pass

    if value.startswith("[") and "]" in value:
        host = value[1:value.index("]")]
        return _normalize_ip_address(ip_address(host))

    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return _normalize_ip_address(ip_address(host))

    raise ValueError(f"Invalid X-Forwarded-For IP address: {value}")


def _resolve_forwarded_for_client_ip(
    forwarded_for: str,
    trusted_networks: tuple[_BaseNetwork, ...],
    direct_ip: _BaseAddress,
) -> _BaseAddress:
    leftmost_candidate = direct_ip
    for raw_value in reversed(forwarded_for.split(",")):
        value = raw_value.strip()
        if not value:
            return direct_ip
        try:
            candidate = _parse_forwarded_for_ip(value)
        except ValueError:
            return direct_ip
        leftmost_candidate = candidate
        if not _is_trusted(candidate, trusted_networks):
            return candidate
    return leftmost_candidate


def _normalize_ip_address(candidate: _BaseAddress) -> _BaseAddress:
    ipv4_mapped = getattr(candidate, "ipv4_mapped", None)
    return ipv4_mapped or candidate


def _is_trusted(candidate: _BaseAddress, trusted_networks: tuple[_BaseNetwork, ...]) -> bool:
    return any(candidate in network for network in trusted_networks)
