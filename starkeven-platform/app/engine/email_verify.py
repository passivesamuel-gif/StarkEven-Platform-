import re

from ..config import settings
from ..netguard import Unresolvable, UnsafeTarget, assert_public_host
from . import dnsutil
from .mailproviders import classify_email_provider
from .smtp import ProbeResult, smtp_probe

SMTP_PORT = 25  # overridable in tests
SMTP_TIMEOUT = 3.0  # seconds per MX host
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")


def _result(email, fmt, mx_ok, status, provider, reason=None) -> dict:
    out = {
        "email": email, "format_valid": fmt, "mx_valid": mx_ok,
        "smtp_deliverable": status, "provider": provider,
    }
    if reason:
        out["reason"] = reason
    return out


async def verify_email(email: str) -> dict:
    email = (email or "").strip()
    if len(email) > 254 or not EMAIL_RE.match(email) or ".." in email:
        return _result(email, False, False, "unknown", None, "invalid_format")
    domain = email.rsplit("@", 1)[1].lower()
    mx_hosts = dnsutil.parse_mx(await dnsutil.query(domain, "MX"))
    if not mx_hosts:
        return _result(email, True, False, "unknown", None, "no_mx_records")
    provider = classify_email_provider(mx_hosts)

    last = ProbeResult("unknown", "no_public_mx")
    saw_smtp_reply = False
    for host in mx_hosts[:2]:
        try:
            await assert_public_host(host)  # never connect to private/internal MX targets
        except (UnsafeTarget, Unresolvable):
            continue
        try:
            last = await smtp_probe(
                host, email, port=SMTP_PORT, helo=settings.smtp_helo_domain, timeout=SMTP_TIMEOUT
            )
        except (OSError, TimeoutError, ConnectionRefusedError):
            last = ProbeResult("unknown", "connection_failed")
        if last.reason not in ("connection_failed", "smtp_error", "no_public_mx"):
            saw_smtp_reply = True
        if last.status != "unknown":
            break
    status = (
        "unverifiable_network"
        if last.status == "unknown" and not saw_smtp_reply and last.reason in ("connection_failed", "smtp_error")
        else last.status
    )
    return _result(email, True, True, status, provider, last.reason)
