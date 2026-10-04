"""Bounded public-web fetches. Pin each connection to a validated public IP."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 5 * 1024 * 1024


def public_target(url: str) -> tuple[httpx.URL, str]:
    parts = urlsplit(url)
    if (
        parts.scheme not in ("https", "http")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 80, 443)
    ):
        raise ValueError("Use a public HTTP(S) URL on a standard web port.")
    hostname = parts.hostname.encode("idna").decode()
    addresses = socket.getaddrinfo(
        hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
    )
    ips = list(dict.fromkeys(info[4][0] for info in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Private, local, and reserved network addresses are not supported.")
    return httpx.URL(url).copy_with(host=ips[0]), hostname


def fetch_public(url: str, max_bytes: int = MAX_BYTES) -> tuple[bytes, str, str]:
    with httpx.Client(timeout=12, trust_env=False) as client:
        for _ in range(5):
            target, hostname = public_target(url)
            with client.stream(
                "GET",
                target,
                headers={
                    "Host": hostname,
                    "User-Agent": "Trace/0.1 (image usage review prototype)",
                },
                extensions={"sni_hostname": hostname},
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("The source returned an empty redirect.")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError(f"Source exceeds the {max_bytes // (1024 * 1024)} MB fetch limit.")
                return bytes(content), response.headers.get("content-type", ""), url
    raise ValueError("Too many redirects.")
