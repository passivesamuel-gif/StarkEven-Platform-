from sqlalchemy import update

from app import db as dbmod
from app import redis_client
from app.engine import notifications, otp_mailer
from app.models import Organization
from tests.conftest import make_key


async def test_notification_settings_crud_and_jwt_protection(client, signup):
    acct = await signup(email="prefs@example.com")
    api_key = (await make_key(client, acct, name="prefs-key"))["api_key"]

    # /orgs/me includes defaults (True, True)
    me = await client.get("/api/v1/orgs/me", headers=acct["jwt"])
    assert me.status_code == 200
    assert me.json()["notify_low_credits"] is True
    assert me.json()["notify_campaign_reports"] is True

    # API keys cannot read or mutate account notification settings
    assert (await client.get("/api/v1/orgs/me/notifications", headers={"X-API-Key": api_key})).status_code == 403
    assert (
        await client.patch(
            "/api/v1/orgs/me/notifications",
            json={"notify_low_credits": False},
            headers={"X-API-Key": api_key},
        )
    ).status_code == 403

    # Empty patch returns 422
    assert (await client.patch("/api/v1/orgs/me/notifications", json={}, headers=acct["jwt"])).status_code == 422

    # Toggle low-credit warnings off while keeping campaign reports on
    p1 = await client.patch(
        "/api/v1/orgs/me/notifications",
        json={"notify_low_credits": False},
        headers=acct["jwt"],
    )
    assert p1.status_code == 200
    assert p1.json() == {
        "notify_low_credits": False,
        "notify_campaign_reports": True,
        "recipient_email": "prefs@example.com",
    }

    # Toggle campaign reports off as well and verify persistence via GET
    p2 = await client.patch(
        "/api/v1/orgs/me/notifications",
        json={"notify_campaign_reports": False},
        headers=acct["jwt"],
    )
    assert p2.status_code == 200
    fetched = await client.get("/api/v1/orgs/me/notifications", headers=acct["jwt"])
    assert fetched.status_code == 200
    assert fetched.json() == {
        "notify_low_credits": False,
        "notify_campaign_reports": False,
        "recipient_email": "prefs@example.com",
    }


async def test_low_credit_warning_and_campaign_report_respect_toggles_and_cooldown(client, signup, monkeypatch):
    acct = await signup(email="alerts@example.com")
    sent: list[dict] = []

    async def fake_send(to_email: str, subject: str, html_body: str, text_body: str):
        sent.append({"to": to_email, "subject": subject, "html": html_body, "text": text_body})
        return {"delivery_mode": "dev_console"}

    monkeypatch.setattr(otp_mailer, "send_email_message", fake_send)

    # Above threshold (50 >= 5): no low-credit email sent
    assert await notifications.send_low_credit_warning_if_needed(acct["org_id"], 50) is False
    assert len(sent) == 0

    # Below 10% threshold (4 < 5): sends once, then suppressed by 24h Redis cooldown
    assert await notifications.send_low_credit_warning_if_needed(acct["org_id"], 4) is True
    assert len(sent) == 1
    assert "Low credit warning" in sent[0]["subject"]
    assert await notifications.send_low_credit_warning_if_needed(acct["org_id"], 3) is False
    assert len(sent) == 1

    # Campaign report sends and escapes HTML safely
    assert (
        await notifications.send_campaign_completion_report(
            acct["org_id"],
            campaign_name="Acme <script>alert(1)</script>",
            delivered_count=7,
            total_delivered=21,
            credits_remaining=4,
        )
        is True
    )
    assert len(sent) == 2
    assert "<script>" not in sent[1]["html"]
    assert "&lt;script&gt;" in sent[1]["html"]

    # Disable both toggles -> neither alert dispatches even after cooldown cleared
    await redis_client.get_redis().delete(f"starkeven:alert:low_credit:{acct['org_id']}")
    async with dbmod.SessionLocal() as s:
        await s.execute(
            update(Organization)
            .where(Organization.id == acct["org_id"])
            .values(notify_low_credits=False, notify_campaign_reports=False)
        )
        await s.commit()

    assert await notifications.send_low_credit_warning_if_needed(acct["org_id"], 2) is False
    assert (
        await notifications.send_campaign_completion_report(
            acct["org_id"],
            campaign_name="Paused Alerts",
            delivered_count=1,
            total_delivered=22,
            credits_remaining=2,
        )
        is False
    )
    assert len(sent) == 2
