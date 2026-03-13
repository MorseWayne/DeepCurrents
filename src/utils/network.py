from __future__ import annotations

import ipaddress
from typing import Optional
from urllib.parse import urlsplit


LOCAL_HOSTNAMES = {"localhost", "host.docker.internal"}


def is_local_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False

    normalized = hostname.strip().strip("[]").lower()
    if not normalized:
        return False
    if normalized in LOCAL_HOSTNAMES:
        return True
    if "." not in normalized:
        # Docker Compose service names are typically single-label hosts like "rsshub".
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
    )


def should_bypass_proxy(url: str) -> bool:
    hostname = urlsplit(url).hostname
    return is_local_hostname(hostname)


def resolve_request_proxy(url: str, proxy: Optional[str]) -> Optional[str]:
    if not proxy:
        return None
    if should_bypass_proxy(url):
        return None
    return proxy
