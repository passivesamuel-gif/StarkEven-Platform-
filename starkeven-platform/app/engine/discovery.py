"""Deterministic B2B lead discovery and ICP qualification engine (no AI/LLM)."""
import asyncio
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from selectolax.parser import HTMLParser

from ..errors import DomainNotFound
from ..netguard import Unresolvable, UnsafeTarget, normalize_domain, request_guard
from .email_verify import verify_email
from .enrichment import USER_AGENT, enrich_domain

_transport = None  # tests inject httpx.MockTransport

NOISE_DOMAINS = frozenset({
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "youtube.com",
    "instagram.com",
    "wikipedia.org",
    "reddit.com",
    "medium.com",
    "github.com",
    "google.com",
    "amazon.com",
    "apple.com",
    "crunchbase.com",
    "g2.com",
    "capterra.com",
    "glassdoor.com",
    "indeed.com",
    "duckduckgo.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "employinc.com",
    "jazzhr.com",
    "workable.com",
    "breezy.hr",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "myworkdayjobs.com",
    "workday.com",
})

ROLE_PREFIXES = ("founders", "sales", "hello")


def _is_noise(domain: str) -> bool:
    return any(domain == n or domain.endswith("." + n) for n in NOISE_DOMAINS)


def _extract_candidate_domains_from_html(html: str) -> list[str]:
    if not html:
        return []
    tree = HTMLParser(html)
    out: list[str] = []
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        parsed = urlparse(href)
        target = href
        if "uddg" in parsed.query:
            qs = parse_qs(parsed.query)
            if qs.get("uddg"):
                target = unquote(qs["uddg"][0])
        elif not parsed.scheme and href.startswith("//"):
            target = "https:" + href
        u = urlparse(target)
        if u.scheme not in ("http", "https") or not u.hostname:
            continue
        try:
            domain = normalize_domain(u.hostname)
        except ValueError:
            continue
        if not _is_noise(domain):
            out.append(domain)
    return out


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url)
        if 200 <= r.status_code < 400:
            return r.text
    except (httpx.HTTPError, UnsafeTarget, Unresolvable):
        return ""
    return ""


async def discover_candidate_domains(keywords: list[str], limit: int = 30) -> list[str]:
    cleaned = [k.strip() for k in (keywords or []) if isinstance(k, str) and k.strip()]
    if not cleaned or limit <= 0:
        return []

    web_search_urls: list[str] = []
    secondary_urls: list[str] = []
    for kw in cleaned[:5]:
        web_q = quote_plus(
            f'"{kw}" company OR official site -site:linkedin.com -site:wikipedia.org -site:facebook.com -site:youtube.com'
        )
        web_search_urls.append(f"https://html.duckduckgo.com/html/?q={web_q}")
        q = quote_plus(kw)
        secondary_urls.extend([
            f"https://boards.greenhouse.io/?q={q}",
            f"https://jobs.lever.co/?q={q}",
            f"https://jobs.ashbyhq.com/?q={q}",
        ])

    hooks = {} if _transport is not None else {"request": [request_guard]}
    seen: set[str] = set()
    domains: list[str] = []

    def _collect(pages: list) -> None:
        for page in pages:
            if not isinstance(page, str) or not page:
                continue
            for dom in _extract_candidate_domains_from_html(page):
                if dom not in seen:
                    seen.add(dom)
                    domains.append(dom)
                    if len(domains) >= limit:
                        return

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0),
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
        event_hooks=hooks,
        transport=_transport,
        trust_env=False,
    ) as client:
        # Step 1: Query general web search FIRST for authentic niche company domains
        primary_pages = await asyncio.gather(*(_fetch_text(client, u) for u in web_search_urls), return_exceptions=True)
        _collect(primary_pages)

        # Step 2: Only supplement with secondary job board directories if quota remains
        if len(domains) < limit and secondary_urls:
            secondary_pages = await asyncio.gather(*(_fetch_text(client, u) for u in secondary_urls), return_exceptions=True)
            _collect(secondary_pages)

    return domains


async def qualify_and_verify_lead(
    domain: str,
    required_tech_stack: list[str],
    require_hiring: bool,
) -> dict | None:
    try:
        norm = normalize_domain(domain)
    except ValueError:
        return None

    try:
        enriched = await enrich_domain(norm)
    except (UnsafeTarget, Unresolvable, DomainNotFound, httpx.HTTPError):
        return None

    tech_items = enriched.get("tech_stack") or []
    tech_names = [t["name"] if isinstance(t, dict) else str(t) for t in tech_items]
    tech_lower = {name.strip().lower() for name in tech_names if name}
    req_lower = {r.strip().lower() for r in (required_tech_stack or []) if isinstance(r, str) and r.strip()}
    if req_lower and not (req_lower & tech_lower):
        return None

    hiring = enriched.get("hiring") or {}
    hiring_signals = enriched.get("hiring_signals") or {}
    is_hiring = bool(
        hiring.get("has_careers_page") or hiring.get("ats") or hiring_signals.get("is_hiring")
    )
    if require_hiring and not is_hiring:
        return None

    role_emails = [f"{prefix}@{norm}" for prefix in ROLE_PREFIXES]
    checks = await asyncio.gather(*(verify_email(addr) for addr in role_emails), return_exceptions=True)
    verified_emails: list[str] = []
    for addr, res in zip(role_emails, checks):
        if not isinstance(res, dict):
            continue
        status = res.get("smtp_deliverable")
        if status in ("valid", "catch_all") or (status == "unverifiable_network" and res.get("mx_valid") is True):
            verified_emails.append(addr)

    if not verified_emails:
        return None

    company = enriched.get("company") or {}
    email_info = enriched.get("email") or {}
    return {
        "domain": norm,
        "company_name": company.get("name") or enriched.get("company_name"),
        "tech_stack": tech_names,
        "email_provider": email_info.get("provider") or "Unknown",
        "verified_emails": verified_emails,
        "hiring_ats": list(hiring.get("ats") or []),
        "enriched": enriched,
    }
