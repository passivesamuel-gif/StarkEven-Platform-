import hashlib

from sqlalchemy import select

from app import db as dbmod
from app.models import APIKey, Organization
from tests.conftest import make_key


async def _set_org(org_id, **values):
    async with dbmod.SessionLocal() as s:
        org = await s.get(Organization, org_id)
        for k, v in values.items():
            setattr(org, k, v)
        await s.commit()


async def test_register_creates_org_with_trial_credits_and_login_works(client, signup):
    acct = await signup("Owner@Example.com")
    me = (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()
    assert me["credit_balance"] == 50 and me["plan_tier"] == "starter" and me["email"] == "owner@example.com"

    dup = await client.post("/api/v1/auth/register", json={"email": "owner@example.com", "password": "another-password"})
    assert dup.status_code == 409

    ok = await client.post("/api/v1/auth/login", json={"email": "OWNER@example.com", "password": "correct-horse-battery"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = await client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong-password"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthorized"


async def test_key_shown_once_and_only_hash_stored(client, signup):
    acct = await signup()
    created = await make_key(client, acct, name="ci")
    raw = created["api_key"]
    assert raw.startswith("sk_live_") and len(raw) == len("sk_live_") + 32

    listing = (await client.get("/api/v1/keys", headers=acct["jwt"])).json()
    assert listing[0]["key_prefix"] == raw[:12] + "..."
    assert raw not in str(listing)

    async with dbmod.SessionLocal() as s:
        row = (await s.execute(select(APIKey))).scalar_one()
    assert row.key_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in (row.key_hash, row.key_prefix)


async def test_api_key_and_jwt_both_authenticate_and_charge_one_credit(client, signup):
    acct = await signup()
    raw = (await make_key(client, acct))["api_key"]
    r1 = await client.get("/api/v1/protected/ping", headers={"X-API-Key": raw})
    assert r1.status_code == 200 and r1.json()["credits_remaining"] == 49
    r2 = await client.get("/api/v1/protected/ping", headers={"Authorization": f"Bearer {raw}"})
    assert r2.status_code == 200 and r2.json()["credits_remaining"] == 48
    r3 = await client.get("/api/v1/protected/ping", headers=acct["jwt"])
    assert r3.status_code == 200 and r3.json()["via"] == "jwt" and r3.json()["credits_remaining"] == 47


async def test_scope_is_enforced(client, signup):
    acct = await signup()
    raw = (await make_key(client, acct, scopes=["bulk:write"]))["api_key"]
    r = await client.get("/api/v1/protected/ping", headers={"X-API-Key": raw})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_api_keys_cannot_manage_keys(client, signup):
    acct = await signup()
    raw = (await make_key(client, acct))["api_key"]
    r = await client.get("/api/v1/keys", headers={"X-API-Key": raw})
    assert r.status_code == 403


async def test_revoke_takes_effect_immediately_even_when_cached(client, signup):
    acct = await signup()
    created = await make_key(client, acct)
    h = {"X-API-Key": created["api_key"]}
    assert (await client.get("/api/v1/protected/ping", headers=h)).status_code == 200  # populates Redis cache
    assert (await client.delete(f"/api/v1/keys/{created['id']}", headers=acct["jwt"])).status_code == 200
    assert (await client.get("/api/v1/protected/ping", headers=h)).status_code == 401


async def test_rotate_replaces_key_atomically(client, signup):
    acct = await signup()
    old = await make_key(client, acct, name="prod")
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": old["api_key"]})).status_code == 200
    rot = await client.post(f"/api/v1/keys/{old['id']}/rotate", headers=acct["jwt"])
    assert rot.status_code == 201
    new_raw = rot.json()["api_key"]
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": old["api_key"]})).status_code == 401
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": new_raw})).status_code == 200


async def test_rate_limit_returns_429_with_retry_after(client, signup):
    acct = await signup()
    await _set_org(acct["org_id"], rate_limit_per_min=2)
    for _ in range(2):
        assert (await client.get("/api/v1/protected/ping", headers=acct["jwt"])).status_code == 200
    r = await client.get("/api/v1/protected/ping", headers=acct["jwt"])
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(r.headers["Retry-After"]) <= 60


async def test_zero_credits_returns_402(client, signup):
    acct = await signup()
    await _set_org(acct["org_id"], credit_balance=0)
    r = await client.get("/api/v1/protected/ping", headers=acct["jwt"])
    assert r.status_code == 402 and r.json()["error"]["code"] == "payment_required"


async def test_error_envelopes(client):
    r = await client.get("/api/v1/protected/ping")
    assert r.status_code == 401 and set(r.json()["error"]) >= {"code", "message"}
    r = await client.post("/api/v1/auth/register", json={"email": "nope", "password": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_usage_is_logged_in_background(client, signup):
    from app import usage

    acct = await signup()
    await client.get("/api/v1/protected/ping", headers=acct["jwt"])
    await usage.drain()
    rows = (await client.get("/api/v1/orgs/me/usage", headers=acct["jwt"])).json()
    ping = next(r for r in rows if r["endpoint"].endswith("/protected/ping"))
    assert ping["status_code"] == 200 and ping["credits_used"] == 1


async def test_rotate_preserves_scopes_and_expired_keys_return_401(client, signup):
    from datetime import datetime, timedelta, timezone
    from app import redis_client
    from app.security import hash_key, key_cache_name

    acct = await signup()
    created = await make_key(client, acct, name="scoped", scopes=["enrich:read"], expires_in_days=5)
    old_raw = created["api_key"]
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": old_raw})).status_code == 200

    rot = await client.post(f"/api/v1/keys/{created['id']}/rotate", headers=acct["jwt"])
    assert rot.status_code == 201
    rot_body = rot.json()
    assert rot_body["scopes"] == ["enrich:read"]
    assert await redis_client.get_redis().get(key_cache_name(hash_key(old_raw))) is None
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": old_raw})).status_code == 401

    new_raw = rot_body["api_key"]
    assert (await client.get("/api/v1/protected/ping", headers={"Authorization": f"Bearer {new_raw}"})).status_code == 200
    assert (await client.post("/api/v1/enrich/bulk", json={"domains": ["acme.com"]}, headers={"X-API-Key": new_raw})).status_code == 403

    # Force expires_at into the past in DB and test both cache-miss and cache-hit expiration rejection
    async with dbmod.SessionLocal() as s:
        row = await s.get(APIKey, rot_body["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        await s.commit()

    await redis_client.get_redis().delete(key_cache_name(hash_key(new_raw)))
    assert (await client.get("/api/v1/protected/ping", headers={"X-API-Key": new_raw})).status_code == 401
    assert await redis_client.get_redis().get(key_cache_name(hash_key(new_raw))) is None


async def test_daily_usage_endpoint_returns_30_days_isolated_per_org(client, signup):
    from datetime import datetime, timedelta, timezone
    from app.models import UsageLog

    acct = await signup("usage-a@example.com")
    other = await signup("usage-b@example.com")
    now = datetime.now(timezone.utc)
    async with dbmod.SessionLocal() as s:
        s.add_all([
            UsageLog(org_id=acct["org_id"], endpoint="POST /api/v1/enrich/domain", status_code=200, credits_used=3, latency_ms=12, created_at=now),
            UsageLog(org_id=acct["org_id"], endpoint="POST /api/v1/verify/email", status_code=200, credits_used=2, latency_ms=8, created_at=now - timedelta(days=4)),
            UsageLog(org_id=acct["org_id"], endpoint="GET /api/v1/protected/ping", status_code=200, credits_used=5, latency_ms=5, created_at=now - timedelta(days=45)),
            UsageLog(org_id=other["org_id"], endpoint="POST /api/v1/enrich/domain", status_code=200, credits_used=99, latency_ms=10, created_at=now),
        ])
        await s.commit()

    r = await client.get("/api/v1/orgs/me/usage/daily?days=30", headers=acct["jwt"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["days"] == 30
    assert body["total_credits"] == 5
    assert body["total_requests"] == 2
    assert len(body["daily"]) == 30
    by_date = {d["date"]: d for d in body["daily"]}
    assert by_date[now.date().isoformat()]["credits_used"] == 3
    assert by_date[(now - timedelta(days=4)).date().isoformat()]["credits_used"] == 2
