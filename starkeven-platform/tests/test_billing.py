import hashlib
import hmac
import json
import time

from sqlalchemy import func, select

from app import db as dbmod
from app.config import settings
from app.models import BillingEvent


def _lemon(event_id="1001", org_id=1, credits=100, plan="pro"):
    return json.dumps({
        "meta": {"event_name": "order_created", "custom_data": {"org_id": org_id, "credits": credits, "plan_tier": plan}},
        "data": {"id": event_id, "attributes": {"status": "paid"}},
    }).encode()


def _sig(body: bytes) -> dict:
    return {"X-Signature": hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()}


async def _me(client, acct):
    return (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()


async def test_unsigned_or_badly_signed_webhooks_are_rejected(client, signup):
    acct = await signup()
    body = _lemon(org_id=acct["org_id"])
    assert (await client.post("/api/v1/webhooks/billing", content=body)).status_code == 401
    assert (await client.post("/api/v1/webhooks/billing", content=body, headers={"X-Signature": "0" * 64})).status_code == 401
    assert (await _me(client, acct))["credit_balance"] == 50


async def test_webhook_is_idempotent_and_upgrades_plan(client, signup):
    acct = await signup()
    body = _lemon(org_id=acct["org_id"])
    r1 = await client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body))
    r2 = await client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body))
    assert r1.json()["credits_added"] == 100 and r2.json()["duplicate"] is True
    me = await _me(client, acct)
    assert me["credit_balance"] == 150 and me["plan_tier"] == "pro" and me["rate_limit_per_min"] == 600


async def test_duplicate_is_still_caught_by_database_when_redis_is_flushed(client, signup):
    from app import redis_client

    acct = await signup()
    body = _lemon(org_id=acct["org_id"])
    await client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body))
    await redis_client.get_redis().flushdb()
    r = await client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body))
    assert r.json()["duplicate"] is True
    assert (await _me(client, acct))["credit_balance"] == 150
    async with dbmod.SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(BillingEvent)) == 1


async def test_stripe_style_signature_and_replay_window(client, signup):
    acct = await signup()
    body = json.dumps({
        "id": "evt_abc", "type": "checkout.session.completed",
        "data": {"object": {"payment_status": "paid", "metadata": {"org_id": str(acct["org_id"]), "credits": "25"}}},
    }).encode()

    def header(ts):
        mac = hmac.new(settings.webhook_secret.encode(), str(ts).encode() + b"." + body, hashlib.sha256).hexdigest()
        return {"Stripe-Signature": f"t={ts},v1={mac}"}

    assert (await client.post("/api/v1/webhooks/billing", content=body, headers=header(int(time.time()) - 3600))).status_code == 401
    ok = await client.post("/api/v1/webhooks/billing", content=body, headers=header(int(time.time())))
    assert ok.status_code == 200 and ok.json()["credits_added"] == 25


async def test_unknown_org_and_ignored_events(client, signup):
    await signup()
    body = _lemon(org_id=999999)
    assert (await client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body))).status_code == 404
    other = json.dumps({"type": "customer.created"}).encode()
    r = await client.post("/api/v1/webhooks/billing", content=other, headers=_sig(other))
    assert r.status_code == 200 and r.json()["ignored"] is True
    # a failed attempt must not burn the idempotency key: retry after the org exists should be processed
    from app import redis_client
    assert await redis_client.get_redis().get("billing:evt:ls_1001") is None
    assert await redis_client.get_redis().get("starkeven:webhook:lemonsqueezy:ls_1001") is None


async def test_webhook_redis_key_status_duplicate_and_concurrent_delivery(client, signup):
    import asyncio
    from app import redis_client

    acct = await signup()
    body = _lemon(event_id="9001", org_id=acct["org_id"], credits=40)
    r_empty = await client.post("/api/v1/webhooks/billing", content=body, headers={"X-Signature": ""})
    assert r_empty.status_code == 401

    r1, r2 = await asyncio.gather(
        client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body)),
        client.post("/api/v1/webhooks/billing", content=body, headers=_sig(body)),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    statuses = sorted([r1.json().get("status", "processed"), r2.json().get("status", "processed")])
    assert statuses == ["duplicate", "processed"]
    assert await redis_client.get_redis().get("starkeven:webhook:lemonsqueezy:ls_9001") == "1"
    assert (await _me(client, acct))["credit_balance"] == 90
