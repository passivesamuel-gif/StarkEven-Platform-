import json

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing_sig import parse_event, verify_signature
from ..config import PLAN_LIMITS, settings
from ..db import get_db
from ..models import BillingEvent, Organization
from ..redis_client import redis_dep

router = APIRouter(prefix="/api/v1/webhooks", tags=["billing"])
IDEMPOTENCY_TTL_S = 604800


@router.post("/billing")
async def billing_webhook(request: Request, db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep)):
    stripe_sig = (request.headers.get("stripe-signature") or "").strip()
    lemon_sig = (request.headers.get("x-signature") or "").strip()
    if not stripe_sig and not lemon_sig:
        raise HTTPException(401, "Missing webhook signature")
    body = await request.body()
    if not verify_signature(request.headers, body, settings.webhook_secret):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        payload = json.loads(body)
        event = parse_event(payload) if isinstance(payload, dict) else None
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Unusable webhook payload: {e}")
    if event is None:
        return {"ok": True, "ignored": True}

    provider = "lemonsqueezy" if lemon_sig else "stripe"
    # Fast duplicate guard in Redis; the UNIQUE(event_id) row below is the durable guarantee.
    idem_key = f"starkeven:webhook:{provider}:{event.event_id}"
    if not await redis.set(idem_key, "1", nx=True, ex=IDEMPOTENCY_TTL_S):
        return {"ok": True, "duplicate": True, "status": "duplicate"}
    try:
        org = await db.get(Organization, event.org_id, with_for_update=True)
        if org is None:
            raise HTTPException(404, "Organization not found")
        db.add(BillingEvent(event_id=event.event_id, org_id=org.id, credits=event.credits))
        org.credit_balance = Organization.credit_balance + event.credits
        if event.plan_tier in PLAN_LIMITS:
            org.plan_tier = event.plan_tier
            org.rate_limit_per_min = PLAN_LIMITS[event.plan_tier]
        await db.commit()  # credits + event row commit together
        await redis.delete(f"starkeven:alert:low_credit:{org.id}")
    except IntegrityError:
        await db.rollback()
        return {"ok": True, "duplicate": True, "status": "duplicate"}
    except BaseException:
        await db.rollback()
        await redis.delete(idem_key)  # let the provider's retry succeed
        raise
    return {"ok": True, "credits_added": event.credits}
