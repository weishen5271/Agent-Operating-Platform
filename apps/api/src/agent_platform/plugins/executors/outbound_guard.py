from __future__ import annotations

import fnmatch
import ipaddress
from typing import Callable
from urllib.parse import urlparse

from agent_platform.bootstrap.settings import settings

_LOCALHOST_NAMES = {"localhost", "localhost.localdomain"}


def validate_http_endpoint(
    url: str,
    *,
    executor_label: str,
    error_factory: Callable[[str, int | None, str], Exception],
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise error_factory(
            "ENDPOINT_NOT_ALLOWED",
            None,
            f"{executor_label} executor only allows absolute http(s) URLs.",
        )

    host = parsed.hostname.strip().lower().rstrip(".")
    allowlist = [str(item).strip().lower() for item in settings.http_executor_allowlist if str(item).strip()]
    if allowlist and not _host_matches_allowlist(host, allowlist):
        raise error_factory(
            "ENDPOINT_NOT_ALLOWED",
            None,
            f"{executor_label} executor endpoint host is not allowlisted: {host}",
        )
    if _is_blocked_host(host) and not _host_matches_allowlist(host, allowlist):
        raise error_factory(
            "ENDPOINT_NOT_ALLOWED",
            None,
            f"{executor_label} executor endpoint host is blocked by SSRF protection: {host}",
        )


def _is_blocked_host(host: str) -> bool:
    if host in _LOCALHOST_NAMES or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _host_matches_allowlist(host: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return False
    host_ip = _parse_ip(host)
    for raw_entry in allowlist:
        entry = raw_entry.strip().lower()
        if not entry:
            continue
        if "/" in entry:
            if host_ip is None:
                continue
            try:
                if host_ip in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        entry_ip = _parse_ip(entry)
        if entry_ip is not None and host_ip is not None and host_ip == entry_ip:
            return True
        if fnmatch.fnmatchcase(host, entry):
            return True
    return False


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None
