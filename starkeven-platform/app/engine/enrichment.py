"""Deterministic B2B domain enrichment: company profile, tech stack, email infrastructure,
hiring signals. No AI/LLM involved."""
import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from ..config import settings
from ..errors import DomainNotFound
from ..netguard import Unresolvable, UnsafeTarget, request_guard
from . import dnsutil
from .mailproviders import classify_email_provider
from .techdetect import detect_tech

_transport = None  # tests inject httpx.MockTransport
MAX_BYTES = 1_500_000
USER_AGENT = "Mozilla/5.0 (compatible; StarkEvenBot/1.0; +https://starkeven.com/bot)"

ATS_HOSTS = {
    "greenhouse.io": "Greenhouse", "lever.co": "Lever", "ashbyhq.com": "Ashby",
    "myworkdayjobs.com": "Workday", "smartrecruiters.com": "SmartRecruiters",
    "workable.com": "Workable", "bamboohr.com": "BambooHR", "recruitee.com": "Recruitee",
    "jobvite.com": "Jobvite", "icims.com": "iCIMS", "teamtailor.com": "Teamtailor",
}
_CAREERS_PATH = re.compile(r"^/(careers?|jobs|join-us|work-with-us|open-positions)(/|$)", re.I)
_TWITTER_PATH = re.compile(r"^/[A-Za-z0-9_]{1,15}/?$")
_TWITTER_RESERVED = {"share", "intent", "home", "search", "login", "i", "hashtag"}
_GITHUB_PATH = re.compile(r"^/[A-Za-z0-9-]{1,39}/?$")
_DOCKER_HOSTNAMES = frozenset({"postgres", "redis", "api", "worker", "frontend", "caddy"})
_BOT_CHALLENGE_MARKERS = (
    "just a moment...",
    "attention required! | cloudflare",
    "enable javascript and cookies to continue",
)


def _is_blocked_ip(ip_str: str) -> bool:
    clean = ip_str.split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(clean)
    except ValueError:
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or not addr.is_global
    )


async def _assert_safe_target(domain: str) -> None:
    host = (domain or "").strip().lower().rstrip(".")
    if not host:
        raise UnsafeTarget("empty target")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or host in _DOCKER_HOSTNAMES
    ):
        raise UnsafeTarget(f"Internal hostname refused: {domain}")
    bare = host.strip("[]")
    try:
        ipaddress.ip_address(bare.split("%", 1)[0])
    except ValueError:
        pass
    else:
        if _is_blocked_ip(bare):
            raise UnsafeTarget(f"Non-public IP address refused: {domain}")
        return
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except OSError:
        infos = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and _is_blocked_ip(sockaddr[0]):
            raise UnsafeTarget(f"{domain} resolves to non-public address {sockaddr[0]}")


def _is_bot_challenge(status_code: int | None, title: str | None, html: str) -> bool:
    if status_code in (403, 503):
        return True
    haystack = f"{title or ''}\n{html or ''}".lower()
    return any(marker in haystack for marker in _BOT_CHALLENGE_MARKERS)


# ---------------------------------------------------------------- HTML parsing
def _social_kind(href: str) -> str | None:
    u = urlparse(href)
    host = (u.hostname or "").lower().removeprefix("www.")
    if host == "linkedin.com" and u.path.startswith(("/company/", "/school/")):
        return "linkedin"
    if host in ("twitter.com", "x.com") and _TWITTER_PATH.match(u.path) \
            and u.path.strip("/").lower() not in _TWITTER_RESERVED:
        return "twitter"
    if host == "github.com" and _GITHUB_PATH.match(u.path):
        return "github"
    return None


def _ats_for(host: str) -> str | None:
    for suffix, name in ATS_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return None


def parse_html(html: str, base_url: str, site_domain: str) -> dict:
    out = {
        "name": None, "title": None, "description": None,
        "linkedin": None, "twitter": None, "github": None,
        "careers_url": None, "ats": [],
    }
    if not html:
        return out
    tree = HTMLParser(html)

    def meta(selector: str) -> str | None:
        node = tree.css_first(selector)
        val = node.attributes.get("content") if node else None
        return val.strip() if val and val.strip() else None

    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else None
    if _is_bot_challenge(None, title, html):
        out["bot_protection_detected"] = True
        return out
    out["title"] = title[:200] if title else None
    name = meta('meta[property="og:site_name"]')
    if not name and title:
        name = re.split(r"\s[|\-–—:·•]\s", title)[0].strip()
    out["name"] = name[:100] if name else None
    desc = meta('meta[name="description"]') or meta('meta[property="og:description"]')
    out["description"] = desc[:500] if desc else None

    ats: list[str] = []
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        u = urlparse(absolute)
        if u.scheme not in ("http", "https"):
            continue
        host = (u.hostname or "").lower()
        kind = _social_kind(absolute)
        if kind and not out[kind]:
            out[kind] = absolute.split("?")[0]
        ats_name = _ats_for(host)
        if ats_name and ats_name not in ats:
            ats.append(ats_name)
            if not out["careers_url"]:
                out["careers_url"] = absolute
        on_site = host == site_domain or host.endswith("." + site_domain)
        if on_site and not out["careers_url"] and (
            _CAREERS_PATH.match(u.path or "") or host.startswith(("careers.", "jobs."))
        ):
            out["careers_url"] = absolute
    out["ats"] = ats
    return out


# ---------------------------------------------------------------- network fetchers
@dataclass
class SiteResult:
    reachable: bool = False
    html: str = ""
    headers: str = ""
    final_url: str | None = None
    unsafe: str | None = None
    error: str | None = None
    status_code: int | None = None


async def fetch_site(domain: str) -> SiteResult:
    await _assert_safe_target(domain)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(6.0, connect=4.0), follow_redirects=True, max_redirects=5,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
        event_hooks={"request": [request_guard]}, transport=_transport, trust_env=False,
    ) as client:
        last_error = None
        for scheme in ("https", "http"):
            try:
                async with client.stream("GET", f"{scheme}://{domain}") as r:
                    raw = bytearray()
                    async for chunk in r.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            break
                    ctype = r.headers.get("content-type", "")
                    html = bytes(raw).decode(r.encoding or "utf-8", "replace") if ("html" in ctype or not ctype) else ""
                    headers = "\n".join(f"{k}: {v}" for k, v in r.headers.items()).lower()
                    return SiteResult(True, html, headers, str(r.url), status_code=r.status_code)
            except UnsafeTarget as e:
                return SiteResult(unsafe=str(e))
            except Unresolvable:
                return SiteResult(error="unresolvable")
            except httpx.HTTPError as e:
                last_error = type(e).__name__
        return SiteResult(error=last_error)


@dataclass
class DnsInfo:
    ips: list = field(default_factory=list)
    mx_hosts: list = field(default_factory=list)
    txt: list = field(default_factory=list)
    cname: list = field(default_factory=list)


async def dns_bundle(domain: str) -> DnsInfo:
    a, aaaa, mx, txt, cname = await asyncio.gather(
        dnsutil.query(domain, "A"), dnsutil.query(domain, "AAAA"), dnsutil.query(domain, "MX"),
        dnsutil.query(domain, "TXT"), dnsutil.query("www." + domain, "CNAME"),
    )
    return DnsInfo(ips=a + aaaa, mx_hosts=dnsutil.parse_mx(mx), txt=txt, cname=cname)


# ---------------------------------------------------------------- orchestration
async def enrich_domain(domain: str) -> dict:
    """Live enrichment (DNS validated before website fetch). `domain` must already be normalized."""
    await _assert_safe_target(domain)
    dns = await dns_bundle(domain)
    for ip in dns.ips:
        if _is_blocked_ip(ip):
            raise UnsafeTarget(f"{domain} resolves to non-public address {ip}")
    if not dns.ips and not dns.mx_hosts:
        raise DomainNotFound(domain)

    site = await fetch_site(domain)
    if site.unsafe:
        raise UnsafeTarget(site.unsafe)

    parsed = parse_html(site.html, site.final_url or f"https://{domain}", domain)
    bot_protected = _is_bot_challenge(site.status_code, parsed.get("title"), site.html) or bool(
        parsed.get("bot_protection_detected")
    )
    dns_blob = " ".join(dns.mx_hosts + dns.txt + dns.cname)
    tech = detect_tech(site.html, site.headers, dns_blob)
    label = domain.split(".")[0].replace("-", " ").title()
    return {
        "domain": domain,
        "company": {
            "name": label if bot_protected else (parsed["name"] or label),
            "title": None if bot_protected else parsed["title"],
            "description": None if bot_protected else parsed["description"],
            "website": f"https://{domain}",
            "linkedin": None if bot_protected else parsed["linkedin"],
            "twitter": None if bot_protected else parsed["twitter"],
            "github": None if bot_protected else parsed["github"],
        },
        "tech_stack": tech,
        "email": {
            "provider": classify_email_provider(dns.mx_hosts),
            "mx_hosts": dns.mx_hosts[:5],
            "spf": any(t.lower().startswith("v=spf1") for t in dns.txt),
        },
        "hiring": {
            "has_careers_page": False if bot_protected else bool(parsed["careers_url"]),
            "careers_url": None if bot_protected else parsed["careers_url"],
            "ats": [] if bot_protected else parsed["ats"],
        },
        "site_reachable": site.reachable,
        "bot_protection_detected": bot_protected,
        "enriched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def cache_key(domain: str) -> str:
    return f"enrich:v2:{domain}"


async def enrich_cached(domain: str, redis, *, force_refresh: bool = False, charge=None) -> tuple[dict, bool]:
    """Returns (data, served_from_cache). `charge` (async callable) is awaited once, only for a
    live result and BEFORE it is cached, so a failed payment never leaks a free cache entry."""
    if not force_refresh:
        raw = await redis.get(cache_key(domain))
        if raw:
            return json.loads(raw), True
    data = await enrich_domain(domain)
    if charge is not None:
        await charge()
    await redis.setex(cache_key(domain), settings.enrich_cache_ttl, json.dumps(data))
    return data, False


def sandbox_enrichment(domain: str) -> dict:
    label = domain.split(".")[0].replace("-", " ").title()
    return {
        "domain": domain,
        "company": {
            "name": label, "title": f"{label} (sandbox sample)",
            "description": "Deterministic sample data returned for sk_test_ keys.",
            "website": f"https://{domain}", "linkedin": None, "twitter": None, "github": None,
        },
        "tech_stack": [{"name": "Cloudflare", "category": "CDN / Security"}],
        "email": {"provider": "Google Workspace", "mx_hosts": ["aspmx.l.google.com"], "spf": True},
        "hiring": {"has_careers_page": False, "careers_url": None, "ats": []},
        "site_reachable": True,
        "enriched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sandbox": True,
    }


CSV_FIELDS = [
    "domain", "status", "cached", "error", "company_name", "description", "website",
    "linkedin", "twitter", "github", "email_provider", "spf", "tech_stack",
    "has_careers_page", "careers_url", "ats",
]


def flatten(data: dict, cached: bool) -> dict:
    c = data.get("company") or {}
    e = data.get("email") or {}
    h = data.get("hiring") or {}
    return {
        "domain": data.get("domain"), "status": "ok", "cached": cached, "error": "",
        "company_name": c.get("name"), "description": c.get("description"), "website": c.get("website"),
        "linkedin": c.get("linkedin"), "twitter": c.get("twitter"), "github": c.get("github"),
        "email_provider": e.get("provider"), "spf": e.get("spf"),
        "tech_stack": "; ".join(t["name"] for t in data.get("tech_stack", [])),
        "has_careers_page": h.get("has_careers_page"), "careers_url": h.get("careers_url"),
        "ats": "; ".join(h.get("ats", [])),
    }
