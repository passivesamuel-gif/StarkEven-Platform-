import re

from sqlalchemy import select

from app import db as dbmod
from app import redis_client
from app.config import settings
from app.engine import otp_mailer
from app.models import Organization, User
from tests.conftest import PUBLIC_IP, make_key


def _extract_code(text_body: str) -> str:
    m = re.search(r"Verification code:\s*(\d{6})", text_body)
    assert m, f"OTP code not found in email body: {text_body}"
    return m.group(1)


async def test_otp_hashing_ttl_cooldown_and_single_use_via_api_key(client, signup, monkeypatch):
    acct = await signup()
    api_key = (await make_key(client, acct, name="otp-sdk"))["api_key"]
    sent_messages: list[dict] = []

    async def fake_send(to_email: str, subject: str, html_body: str, text_body: str):
        sent_messages.append({
            "to": to_email,
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "code": _extract_code(text_body),
        })
        return {"delivery_mode": "smtp_relay"}

    monkeypatch.setattr(otp_mailer, "send_email_message", fake_send)

    # Unauthenticated requests are rejected
    assert (await client.post("/api/v1/email/send-otp", json={"email": "user@example.com"})).status_code == 401

    # Send OTP with X-API-Key and custom brand_name (including HTML chars to verify escaping)
    r = await client.post(
        "/api/v1/email/send-otp",
        json={"email": "Target@Example.com", "purpose": "login", "brand_name": "Acme <Scripts>"},
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"
    assert r.json()["expires_in"] == 600
    assert len(sent_messages) == 1

    code = sent_messages[0]["code"]
    assert re.fullmatch(r"\d{6}", code)
    assert "<Scripts>" not in sent_messages[0]["html"]
    assert "&lt;Scripts&gt;" in sent_messages[0]["html"]

    # Raw OTP must NEVER be stored in Redis; only its salted SHA-256 hash + attempts counter
    redis = redis_client.get_redis()
    otp_key = "starkeven:otp:login:target@example.com"
    stored = await redis.get(otp_key)
    assert stored is not None
    assert code not in stored
    assert stored == f"{otp_mailer.hash_otp('target@example.com', 'login', code)}:0"
    ttl = await redis.ttl(otp_key)
    assert 500 <= ttl <= 600

    # 1 credit deducted for sending OTP (50 -> 49)
    me = (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()
    assert me["credit_balance"] == 49

    # Cooldown: immediate resend within 60s returns 429 and does NOT deduct a credit
    cd = await client.post(
        "/api/v1/email/send-otp",
        json={"email": "target@example.com", "purpose": "login"},
        headers={"X-API-Key": api_key},
    )
    assert cd.status_code == 429
    assert int(cd.headers["Retry-After"]) >= 1
    assert await redis.ttl("starkeven:otp:cooldown:target@example.com") > 0
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 49

    # Verify OTP succeeds once and deletes the Redis key (single-use)
    v1 = await client.post(
        "/api/v1/email/verify-otp",
        json={"email": "target@example.com", "purpose": "login", "code": code},
        headers={"X-API-Key": api_key},
    )
    assert v1.status_code == 200 and v1.json() == {"verified": True}
    assert await redis.get(otp_key) is None

    # Replay of same OTP fails
    v2 = await client.post(
        "/api/v1/email/verify-otp",
        json={"email": "target@example.com", "purpose": "login", "code": code},
        headers={"X-API-Key": api_key},
    )
    assert v2.status_code == 400


async def test_otp_brute_force_5_attempt_lockout(client, signup, monkeypatch):
    acct = await signup()
    captured: list[str] = []

    async def fake_send(to_email: str, subject: str, html_body: str, text_body: str):
        captured.append(_extract_code(text_body))
        return {"delivery_mode": "dev_console"}

    monkeypatch.setattr(otp_mailer, "send_email_message", fake_send)

    r = await client.post(
        "/api/v1/email/send-otp",
        json={"email": "lock@example.com", "purpose": "login"},
        headers=acct["jwt"],
    )
    assert r.status_code == 200
    real_code = captured[0]
    wrong_code = "000000" if real_code != "000000" else "999999"

    # 5 wrong guesses fail cleanly
    for _ in range(5):
        bad = await client.post(
            "/api/v1/email/verify-otp",
            json={"email": "lock@example.com", "purpose": "login", "code": wrong_code},
            headers=acct["jwt"],
        )
        assert bad.status_code == 400

    # 6th attempt is locked (429) even with the valid OTP code
    locked = await client.post(
        "/api/v1/email/verify-otp",
        json={"email": "lock@example.com", "purpose": "login", "code": real_code},
        headers=acct["jwt"],
    )
    assert locked.status_code == 429


async def test_send_otp_requires_credits(client, signup):
    acct = await signup()
    async with dbmod.SessionLocal() as s:
        org = await s.get(Organization, acct["org_id"])
        org.credit_balance = 0
        await s.commit()

    r = await client.post(
        "/api/v1/email/send-otp",
        json={"email": "nocredit@example.com", "purpose": "login"},
        headers=acct["jwt"],
    )
    assert r.status_code == 402


async def test_signup_requires_otp_confirmation_to_unlock_trial_credits(client, monkeypatch):
    captured: list[str] = []

    async def fake_send(to_email: str, subject: str, html_body: str, text_body: str):
        captured.append(_extract_code(text_body))
        return {"delivery_mode": "dev_console"}

    monkeypatch.setattr(otp_mailer, "send_email_message", fake_send)

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "newfounder@example.com", "password": "secure-password-123", "organization_name": "Founder Co"},
    )
    assert reg.status_code == 201, reg.text
    reg_body = reg.json()
    assert reg_body["is_verified"] is False
    assert reg_body["credits"] == 0
    assert "access_token" not in reg_body
    assert len(captured) == 1

    # Database confirms user starts unverified with 0 org credits
    async with dbmod.SessionLocal() as s:
        user = (await s.execute(select(User).where(User.email == "newfounder@example.com"))).scalar_one()
        org = await s.get(Organization, user.org_id)
        assert user.is_verified is False
        assert org.credit_balance == 0

    # Login is blocked until signup OTP is confirmed
    blocked_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "newfounder@example.com", "password": "secure-password-123"},
    )
    assert blocked_login.status_code == 403

    # Confirming with wrong OTP fails and does not unlock credits
    bad_confirm = await client.post(
        "/api/v1/auth/confirm-signup",
        json={"email": "newfounder@example.com", "code": "000000" if captured[0] != "000000" else "999999"},
    )
    assert bad_confirm.status_code == 400

    # Immediate resend respects 60s cooldown (429 + Retry-After)
    resend_cd = await client.post(
        "/api/v1/auth/resend-signup-otp",
        json={"email": "newfounder@example.com"},
    )
    assert resend_cd.status_code == 429
    assert int(resend_cd.headers["Retry-After"]) >= 1

    # Clearing cooldown allows resending a fresh OTP
    await redis_client.get_redis().delete("starkeven:otp:cooldown:newfounder@example.com")
    resend_ok = await client.post(
        "/api/v1/auth/resend-signup-otp",
        json={"email": "newfounder@example.com"},
    )
    assert resend_ok.status_code == 200
    assert len(captured) == 2

    # Confirming with valid OTP marks verified, grants 50 trial credits, and returns JWT
    ok = await client.post(
        "/api/v1/auth/confirm-signup",
        json={"email": "newfounder@example.com", "code": captured[-1]},
    )
    assert ok.status_code == 200, ok.text
    ok_body = ok.json()
    assert ok_body["is_verified"] is True
    assert ok_body["credits"] == 50
    assert ok_body["access_token"]

    me = (await client.get("/api/v1/orgs/me", headers={"Authorization": f"Bearer {ok_body['access_token']}"})).json()
    assert me["credit_balance"] == 50

    login_ok = await client.post(
        "/api/v1/auth/login",
        json={"email": "newfounder@example.com", "password": "secure-password-123"},
    )
    assert login_ok.status_code == 200 and login_ok.json()["access_token"]


async def test_forgot_password_non_enumeration_and_reset_password(client, signup, monkeypatch):
    await signup(email="resetme@example.com", password="initial-password-1")
    await redis_client.get_redis().delete("starkeven:otp:cooldown:resetme@example.com")

    sent: list[str] = []

    async def fake_send(to_email: str, subject: str, html_body: str, text_body: str):
        sent.append(_extract_code(text_body))
        return {"delivery_mode": "dev_console"}

    monkeypatch.setattr(otp_mailer, "send_email_message", fake_send)

    # Non-existent email still returns 200 without leaking account status
    ghost = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert ghost.status_code == 200
    assert len(sent) == 0

    # Existing email sends reset code and returns 200 (even when called again inside cooldown)
    fp1 = await client.post("/api/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    fp2 = await client.post("/api/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    assert fp1.status_code == 200 and fp2.status_code == 200
    assert len(sent) == 1

    # Reset password updates password hash and returns a fresh JWT
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"email": "resetme@example.com", "code": sent[0], "new_password": "brand-new-password-2"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["access_token"]

    # Old password fails, new password works
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "initial-password-1"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@example.com", "password": "brand-new-password-2"},
    )
    assert new_login.status_code == 200 and new_login.json()["access_token"]


async def test_mailer_hybrid_relay_direct_mx_and_dev_console_fallback(dns, monkeypatch, capsys):
    calls: list[dict] = []

    async def fake_smtp_send(msg, **kwargs):
        calls.append({"to": msg["To"], "kwargs": kwargs})
        if kwargs.get("port") == 25 and kwargs.get("hostname") == "blocked-mx.example.com":
            raise OSError("port 25 blocked")
        return ({}, "250 OK")

    monkeypatch.setattr(otp_mailer.aiosmtplib, "send", fake_smtp_send)

    # Mode A: SMTP relay configured
    monkeypatch.setattr(settings, "smtp_host", "smtp-relay.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "apikey")
    monkeypatch.setattr(settings, "smtp_pass", "secret")
    res_a = await otp_mailer.send_email_message("alice@acme.com", "Subj", "<p>Hi</p>", "Hi")
    assert res_a == {"delivery_mode": "smtp_relay", "host": "smtp-relay.example.com"}
    assert calls[-1]["kwargs"]["hostname"] == "smtp-relay.example.com"
    assert calls[-1]["kwargs"]["port"] == 587

    # Mode B: Direct MX delivery when SMTP_HOST is empty
    monkeypatch.setattr(settings, "smtp_host", "")
    dns[("acme.com", "MX")] = ["10 mx1.acme.com"]
    dns[("mx1.acme.com", "A")] = [PUBLIC_IP]
    res_b = await otp_mailer.send_email_message("bob@acme.com", "Subj", "<p>Hi</p>", "Hi")
    assert res_b == {"delivery_mode": "direct_mx", "host": "mx1.acme.com"}
    assert calls[-1]["kwargs"]["port"] == 25
    assert calls[-1]["kwargs"]["timeout"] == 5.0

    # Dev console fallback when port 25 is blocked in non-production
    dns[("blocked.io", "MX")] = ["10 blocked-mx.example.com"]
    dns[("blocked-mx.example.com", "A")] = [PUBLIC_IP]
    redis = redis_client.get_redis()
    res_c = await otp_mailer.send_otp(redis, "dev@blocked.io", purpose="login")
    assert res_c["delivery_mode"] == "dev_console"
    out = capsys.readouterr().out
    assert "[StarkEven OTP Dev Console]" in out and "dev@blocked.io" in out
