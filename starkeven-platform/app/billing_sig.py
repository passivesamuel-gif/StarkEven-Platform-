"""Webhook signature verification and event parsing for Stripe and Lemon Squeezy."""
import hashlib
import hmac
import time
from dataclasses import dataclass

MAX_CREDITS_PER_EVENT = 1_000_000
STRIPE_TOLERANCE_S = 300


@dataclass
class CreditEvent:
    event_id: str
    org_id: int
    credits: int
    plan_tier: str | None


def verify_signature(headers, body: bytes, secret: str, now: float | None = None) -> bool:
    """Lemon Squeezy: X-Signature = hex HMAC-SHA256(body).
    Stripe: Stripe-Signature = t=<ts>,v1=<hex HMAC-SHA256("<ts>.<body>")>.
    A request with neither header is always rejected."""
    if not secret:
        return False
    ls = headers.get("x-signature")
    if ls:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(ls.strip().lower(), expected)
    st = headers.get("stripe-signature")
    if st:
        parts = [p.split("=", 1) for p in st.split(",") if "=" in p]
        ts = next((v for k, v in parts if k.strip() == "t"), None)
        sigs = [v.strip() for k, v in parts if k.strip() == "v1"]
        if not ts or not sigs:
            return False
        try:
            if abs((now if now is not None else time.time()) - int(ts)) > STRIPE_TOLERANCE_S:
                return False
        except ValueError:
            return False
        expected = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(s, expected) for s in sigs)
    return False


def parse_event(payload: dict) -> CreditEvent | None:
    """Returns a CreditEvent for a paid checkout / order, None for events we ignore.
    Raises ValueError for a recognised event with unusable metadata."""
    meta: dict = {}
    event_id = None
    if payload.get("type") == "checkout.session.completed":  # Stripe
        obj = (payload.get("data") or {}).get("object") or {}
        if obj.get("payment_status") not in ("paid", "no_payment_required"):
            return None
        event_id = str(payload.get("id") or "")
        meta = obj.get("metadata") or {}
    elif (payload.get("meta") or {}).get("event_name") == "order_created":  # Lemon Squeezy
        data = payload.get("data") or {}
        if (data.get("attributes") or {}).get("status") not in (None, "paid"):
            return None
        event_id = "ls_" + str(data.get("id") or "")
        meta = (payload.get("meta") or {}).get("custom_data") or {}
    else:
        return None
    if not event_id or event_id in ("ls_",):
        raise ValueError("missing event id")
    try:
        org_id = int(meta["org_id"])
        credits = int(meta.get("credits", 0))
    except (KeyError, TypeError, ValueError):
        raise ValueError("metadata must include integer org_id and credits")
    if not 0 <= credits <= MAX_CREDITS_PER_EVENT:
        raise ValueError("credits out of range")
    return CreditEvent(event_id, org_id, credits, meta.get("plan_tier"))
