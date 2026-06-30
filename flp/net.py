"""
Flower of Life Protocol v1.0 — Endpoint validation / SSRF guard (PROTOCOL.md §7.5)

Because an `endpoint` arrives inside an untrusted card, fetching it naively is a
confused-deputy / SSRF vector (§1.1): an attacker points your agent at internal
services (cloud metadata, localhost, RFC1918). v0.1's probe/bootstrap fetched
arbitrary URLs with none of these checks. v1.0 forbids that.

These are normative MUSTs:
  1. https only (reject http/file/gopher/...).
  2. Reject private, loopback, link-local, and reserved IP ranges.
  3. Re-check after DNS resolution (defeat hostname pointing at an internal IP).
  4. Caller enforces timeout + response-size cap (see client).

`allow_private=True` is a DEVELOPMENT-ONLY escape hatch for loopback testing.
Production agents MUST NOT enable it.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from .identity import FLPVerifyError


def _ip_is_blocked(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
        # 169.254.169.254 (cloud metadata) is link-local, already covered.
    )


def validate_endpoint(url: str, *, allow_private: bool = False,
                      _resolver=None) -> str:
    """Return the URL if safe to fetch, else raise FLPVerifyError('ssrf_blocked').

    _resolver is injectable for testing (maps host -> list[ip]).
    """
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    allowed_schemes = {"https"} | ({"http"} if allow_private else set())
    if scheme not in allowed_schemes:
        raise FLPVerifyError("ssrf_blocked", f"scheme {scheme!r} not permitted")

    host = parsed.hostname
    if not host:
        raise FLPVerifyError("ssrf_blocked", "missing host")

    # Resolve and check EVERY resolved address (§7.5 step 3).
    resolve = _resolver or _default_resolver
    try:
        ips = resolve(host)
    except Exception as e:  # noqa: BLE001
        raise FLPVerifyError("ssrf_blocked", f"cannot resolve host: {e}") from e
    if not ips:
        raise FLPVerifyError("ssrf_blocked", "host resolves to nothing")

    if not allow_private:
        for ip in ips:
            if _ip_is_blocked(ip):
                raise FLPVerifyError(
                    "ssrf_blocked", f"host resolves to blocked address {ip}")

    return url


def _default_resolver(host: str) -> list[str]:
    """Resolve a hostname to all its IP addresses (v4 + v6)."""
    # If host is already a literal IP, getaddrinfo returns it unchanged.
    infos = socket.getaddrinfo(host, None)
    return list({info[4][0] for info in infos})


def assert_no_cross_host_redirect(original: str, location: str,
                                  *, allow_private: bool = False) -> str:
    """Re-validate a redirect target; reject cross-host redirect to internal IPs.

    Defeats redirect-to-internal: a public host 302s to 169.254.169.254.
    """
    return validate_endpoint(location, allow_private=allow_private)
