import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from app import db as dbmod
from app.engine import crm, email_verify, webhooks
from app.engine.smtp import smtp_probe
from app.models import BulkJob
from app.routes import bulk as bulk_routes
from app.worker import run_bulk_job
from tests.conftest import PUBLIC_IP, make_key


# ------------------------------------------------------------------ bulk
@pytest.fixture
def queued(monkeypatch):
    jobs = []

    async def fake_enqueue(job_id):
        jobs.append(job_id)

    monkeypatch.setattr(bulk_routes, "enqueue_bulk", fake_enqueue)
    return jobs


async def test_bulk_job_end_to_end_with_cache_ownership_and_csv(client, signup, acme, site, queued):
    acct = await signup()
    # warm the cache for acme.com (costs 1 credit)
    await client.post("/api/v1/enrich/domain", json={"domain": "acme.com"}, headers=acct["jwt"])

    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"],
                          json={"domains": ["acme.com", "ACME.com", "beta.io", "nothing.example", "bad host"]})
    assert r.status_code == 202, r.text
    batch = r.json()["batch_id"]
    assert r.json()["total_domains"] == 4 and queued == [batch]

    await run_bulk_job(batch)
    status = (await client.get(f"/api/v1/enrich/bulk/{batch}", headers=acct["jwt"])).json()
    assert status["status"] == "completed" and status["progress"] == 1.0
    rows = {x["domain"]: x for x in status["results"]}
    assert rows["acme.com"]["cached"] is True and rows["beta.io"]["cached"] is False
    assert rows["nothing.example"]["error"] == "domain_not_found"
    assert rows["bad host"]["error"] == "invalid_domain"
    assert status["credits_used"] == 1  # only beta.io was a live lookup
    me = (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()
    assert me["credit_balance"] == 50 - 1 - 1

    csv_resp = await client.get(f"/api/v1/enrich/bulk/{batch}/download", headers=acct["jwt"])
    assert csv_resp.status_code == 200 and csv_resp.headers["content-type"].startswith("text/csv")
    lines = csv_resp.text.strip().splitlines()
    assert lines[0].startswith("domain,status,cached,error,company_name")
    assert any(l.startswith("beta.io,ok") for l in lines)

    other = await signup("someone-else@example.com")
    assert (await client.get(f"/api/v1/enrich/bulk/{batch}", headers=other["jwt"])).status_code == 404
    assert (await client.get(f"/api/v1/enrich/bulk/{batch}/download", headers=other["jwt"])).status_code == 404

    # a second run of the same job must never re-process or re-charge
    await run_bulk_job(batch)
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 48


async def test_bulk_csv_upload_and_precheck(client, signup, queued):
    acct = await signup()
    csv_bytes = "Domain,Name\r\nacme.com,Acme\r\nbeta.io,Beta\r\n".encode()
    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"],
                          files={"file": ("d.csv", csv_bytes, "text/csv")})
    assert r.status_code == 202 and r.json()["total_domains"] == 2
    many = {"domains": [f"d{i}.example.com" for i in range(51)]}
    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"], json=many)
    assert r.status_code == 402
    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"], files={"file": ("d.csv", b"name\nx\n", "text/csv")})
    assert r.status_code == 400


async def test_bulk_completion_webhook_is_signed(client, signup, acme, site, queued, dns, monkeypatch):
    acct = await signup()
    dns[("hooks.acme.com", "A")] = [PUBLIC_IP]
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["headers"] = request.content, request.headers
        return httpx.Response(200)

    monkeypatch.setattr(webhooks, "_transport", httpx.MockTransport(handler))
    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"],
                          json={"domains": ["acme.com"], "webhook_url": "https://hooks.acme.com/cb"})
    assert r.status_code == 202
    await run_bulk_job(r.json()["batch_id"])
    secret = (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["callback_signing_secret"]
    ts = seen["headers"]["x-starkeven-timestamp"]
    expected = "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + seen["body"], hashlib.sha256).hexdigest()
    assert seen["headers"]["x-starkeven-signature"] == expected
    assert json.loads(seen["body"])["status"] == "completed"


async def test_bulk_rejects_private_webhook_url(client, signup, queued):
    acct = await signup()
    r = await client.post("/api/v1/enrich/bulk", headers=acct["jwt"],
                          json={"domains": ["acme.com"], "webhook_url": "http://169.254.169.254/latest"})
    assert r.status_code == 422 and queued == []


def test_csv_formula_injection_is_neutralised():
    assert bulk_routes.safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert bulk_routes.safe_cell("+1") == "'+1" and bulk_routes.safe_cell("hello") == "hello"
    assert bulk_routes.safe_cell(None) == ""


async def test_bulk_uuid_validation_and_background_tasks_fallback(client, signup, acme, site):
    import uuid

    acct = await signup()
    other = await signup("other-bulk@example.com")

    for bad_id in ("not-a-uuid", "12345"):
        assert (await client.get(f"/api/v1/enrich/bulk/{bad_id}", headers=acct["jwt"])).status_code == 422
        assert (await client.get(f"/api/v1/enrich/bulk/{bad_id}/download", headers=acct["jwt"])).status_code == 422

    missing_id = uuid.uuid4().hex
    assert (await client.get(f"/api/v1/enrich/bulk/{missing_id}", headers=acct["jwt"])).status_code == 404

    csv_bytes = "domain,note\r\nacme.com,first\r\nbeta.io,second\r\n".encode()
    r = await client.post(
        "/api/v1/enrich/bulk",
        headers=acct["jwt"],
        files={"file": ("domains.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 202, r.text
    batch_id = r.json()["batch_id"]

    # BackgroundTasks executed inside ASGITransport request lifecycle when ARQ worker is offline
    st = await client.get(f"/api/v1/enrich/bulk/{batch_id}", headers=acct["jwt"])
    assert st.status_code == 200 and st.json()["status"] == "completed"
    assert st.json()["credits_used"] == 2
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 48

    # Cross-org access denied with 404 (including hyphenated UUID form)
    hyphenated = str(uuid.UUID(batch_id))
    assert (await client.get(f"/api/v1/enrich/bulk/{hyphenated}", headers=other["jwt"])).status_code == 404
    assert (await client.get(f"/api/v1/enrich/bulk/{hyphenated}/download", headers=other["jwt"])).status_code == 404

    dl = await client.get(f"/api/v1/enrich/bulk/{batch_id}/download", headers=acct["jwt"])
    assert dl.status_code == 200 and dl.headers["content-type"].startswith("text/csv")
    lines = dl.text.strip().splitlines()
    assert len(lines) == 3
    assert any(line.startswith("acme.com,ok,False,,Acme") for line in lines)


# ------------------------------------------------------------------ SMTP
def _fake_smtp(rcpt):
    async def handle(reader, writer):
        writer.write(b"220 fake ESMTP\r\n")
        await writer.drain()
        while True:
            line = await reader.readline()
            if not line:
                break
            cmd = line.decode().strip()
            up = cmd.upper()
            if up.startswith("EHLO"):
                writer.write(b"250-fake\r\n250 SIZE 100\r\n")
            elif up.startswith("RCPT"):
                writer.write(rcpt(cmd[len("RCPT TO:<"):-1]) + b"\r\n")
            elif up.startswith("QUIT"):
                writer.write(b"221 bye\r\n")
                await writer.drain()
                break
            else:
                writer.write(b"250 ok\r\n")
            await writer.drain()
        writer.close()

    return handle


async def _serve(rcpt):
    server = await asyncio.start_server(_fake_smtp(rcpt), "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.parametrize("rcpt,status,reason", [
    (lambda a: b"250 ok" if a == "jane@acme.com" else b"550 5.1.1 no such user", "valid", None),
    (lambda a: b"550 5.1.1 User unknown", "invalid", "mailbox_rejected"),
    (lambda a: b"250 ok", "catch_all", "domain_accepts_all"),
    (lambda a: b"451 4.7.1 greylisted, try later", "unknown", "temporary_failure"),
    (lambda a: b"550 5.7.1 blocked by spamhaus", "unknown", "policy_rejection"),
])
async def test_smtp_probe_outcomes(rcpt, status, reason):
    server, port = await _serve(rcpt)
    try:
        res = await smtp_probe("127.0.0.1", "jane@acme.com", port=port, timeout=3)
    finally:
        server.close()
        await server.wait_closed()
    assert res.status == status and res.reason == reason


async def test_smtp_probe_unreachable_port_is_unknown_not_an_error():
    res = await smtp_probe("127.0.0.1", "jane@acme.com", port=1, timeout=2)
    assert res.status == "unknown" and res.reason == "connection_failed"


async def test_verify_email_endpoint(client, signup, dns, monkeypatch):
    acct = await signup()
    server, port = await _serve(lambda a: b"250 ok" if a == "jane@acme.com" else b"550 5.1.1 nope")
    dns[("acme.com", "MX")] = ["10 127.0.0.1"]

    async def allow(host):
        return [host]

    monkeypatch.setattr(email_verify, "assert_public_host", allow)
    monkeypatch.setattr(email_verify, "SMTP_PORT", port)
    try:
        r = await client.post("/api/v1/verify/email", json={"email": "jane@acme.com"}, headers=acct["jwt"])
        bad = await client.post("/api/v1/verify/email", json={"email": "not-an-email"}, headers=acct["jwt"])
    finally:
        server.close()
        await server.wait_closed()
    body = r.json()
    assert r.status_code == 200 and body["format_valid"] and body["mx_valid"] and body["smtp_deliverable"] == "valid"
    assert bad.json()["format_valid"] is False
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 49  # bad format is free


async def test_verify_email_network_timeout_returns_unverifiable_and_refunds_credit(client, signup, dns, monkeypatch):
    acct = await signup()
    dns[("acme.com", "MX")] = ["10 aspmx.l.google.com"]
    dns[("aspmx.l.google.com", "A")] = ["142.250.1.1"]

    seen_timeouts = []

    async def fake_probe_timeout(host, email, *, port=25, helo="verify.starkeven.local", timeout=3.0, catch_all_probe=True):
        seen_timeouts.append(timeout)
        raise TimeoutError("port 25 blocked")

    monkeypatch.setattr(email_verify, "smtp_probe", fake_probe_timeout)
    r = await client.post("/api/v1/verify/email", json={"email": "jane@acme.com"}, headers=acct["jwt"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen_timeouts == [3.0]
    assert body["format_valid"] is True
    assert body["mx_valid"] is True
    assert body["provider"] == "Google Workspace"
    assert body["smtp_deliverable"] == "unverifiable_network"
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 50

    # Also verify real smtp_probe connection_failed (unreachable port) refunds credit
    monkeypatch.setattr(email_verify, "smtp_probe", smtp_probe)
    monkeypatch.setattr(email_verify, "SMTP_PORT", 1)

    async def allow_local(host):
        return [host]

    dns[("acme.com", "MX")] = ["10 aspmx.l.google.com"]
    monkeypatch.setattr(email_verify, "assert_public_host", allow_local)

    # Mock open_connection to simulate ConnectionRefusedError immediately with google MX host
    async def fake_open_connection(host, port):
        raise ConnectionRefusedError("port 25 refused")

    from app.engine import smtp as smtp_mod
    monkeypatch.setattr(smtp_mod.asyncio, "open_connection", fake_open_connection)
    r2 = await client.post("/api/v1/verify/email", json={"email": "jane@acme.com"}, headers=acct["jwt"])
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["mx_valid"] is True and body2["provider"] == "Google Workspace"
    assert body2["smtp_deliverable"] == "unverifiable_network"
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 50


# ------------------------------------------------------------------ CRM export
RECORD = {"domain": "acme.com", "company": {"name": "Acme", "description": "Rockets", "linkedin": "https://www.linkedin.com/company/acme"}}


def test_crm_payload_formats():
    assert crm.format_hubspot(RECORD) == {"properties": {
        "name": "Acme", "domain": "acme.com", "description": "Rockets",
        "linkedin_company_page": "https://www.linkedin.com/company/acme"}}
    assert crm.format_salesforce(RECORD)["Name"] == "Acme"
    lead = crm.format_salesforce(RECORD, "Lead")
    assert lead["Company"] == "Acme" and lead["LastName"] == "[not provided]"
    assert crm.format_webhook(RECORD)["record"] == RECORD


async def test_crm_export_pushes_and_validates(client, signup, dns, monkeypatch):
    acct = await signup()
    dns[("api.hubapi.com", "A")] = [PUBLIC_IP]
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["json"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        return httpx.Response(201, json={"id": "42"})

    monkeypatch.setattr(crm, "_transport", httpx.MockTransport(handler))
    r = await client.post("/api/v1/export/crm", headers=acct["jwt"], json={
        "provider": "hubspot", "target_url_or_token": "pat-123", "enriched_record": RECORD})
    assert r.status_code == 200 and r.json()["delivered"] is True
    assert seen["url"] == crm.HUBSPOT_URL and seen["auth"] == "Bearer pat-123"
    assert seen["json"]["properties"]["name"] == "Acme"

    sf = await client.post("/api/v1/export/crm", headers=acct["jwt"], json={
        "provider": "salesforce", "target_url_or_token": "tok", "enriched_record": RECORD,
        "instance_url": "https://evil.example.com"})
    assert sf.status_code == 422
    hook = await client.post("/api/v1/export/crm", headers=acct["jwt"], json={
        "provider": "webhook", "target_url_or_token": "http://10.0.0.5/x", "enriched_record": RECORD})
    assert hook.status_code == 422
