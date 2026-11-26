"""SSRF protection: only public hostnames / IPs may be fetched or connected to."""
import asyncio
import ipaddress
import re
from urllib.parse import urlparse

from .engine import dnsutil


class UnsafeTarget(Exception):
    """Host resolves to a loopback / private / link-local / otherwise non-public address."""


class Unresolvable(Exception):
    """Host has no A/AAAA records."""


_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_BLOCKED_SUFFIXES = (
    ".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".arpa", ".test", ".invalid",
)


def normalize_domain(value: str) -> str:
    """Normalize user input ("https://www.Stripe.com/x?y" -> "stripe.com"). Raises ValueError."""
    v = (value or "").strip().lower()
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)
    v = re.split(r"[/?#]", v, maxsplit=1)[0]
    if "@" in v:
        raise ValueError("Domain must not contain credentials")
    v = re.sub(r":\d+$", "", v).rstrip(".")
    if v.startswith("www."):
        v = v[4:]
    if not v:
        raise ValueError("Domain is required")
    try:
        v = v.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("Invalid domain name")
    if len(v) > 253 or "." not in v:
        raise ValueError("Enter a fully-qualified domain such as example.com")
    labels = v.split(".")
    if not all(_LABEL.match(lbl) for lbl in labels):
        raise ValueError("Invalid domain name")
    if labels[-1].isdigit():
        raise ValueError("IP addresses are not accepted; provide a domain name")
    if v == "localhost" or v.endswith(_BLOCKED_SUFFIXES):
        raise ValueError("Internal hostnames are not accepted")
    return v


async def resolve_ips(host: str) -> list[str]:
    a, aaaa = await asyncio.gather(dnsutil.query(host, "A"), dnsutil.query(host, "AAAA"))
    return a + aaaa


def _is_public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def assert_public_host(host: str) -> list[str]:
    ips = await resolve_ips(host)
    if not ips:
        raise Unresolvable(host)
    for ip in ips:
        if not _is_public(ip):
            raise UnsafeTarget(f"{host} resolves to non-public address {ip}")
    return ips


async def request_guard(request) -> None:
    """httpx 'request' event hook: runs for the first request and every redirect hop."""
    host = request.url.host
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not _is_public(host):
            raise UnsafeTarget(f"non-public address {host}")
        return
    await assert_public_host(host.lower())


async def assert_public_url(url: str) -> str:
    """Validate a customer-supplied callback URL. Raises ValueError (bad shape) or UnsafeTarget."""
    u = url.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("URL must start with http:// or https://")
    if p.username or p.password:
        raise ValueError("URL must not contain credentials")
    host = normalize_domain(p.hostname)  # rejects IP literals & internal names
    try:
        await assert_public_host(host)
    except Unresolvable:
        raise ValueError("URL host does not resolve")
    return u
