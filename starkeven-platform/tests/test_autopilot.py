import json
import uuid

import httpx
from sqlalchemy import select

from app import db as dbmod
from app import redis_client
from app.engine import crm, discovery
from app.models import UsageLog
from app.worker import WorkerSettings, execute_single_campaign, run_all_active_autopilot_campaigns
from tests.conftest import PUBLIC_IP, make_key


async def test_autopilot_campaign_crud_and_cross_org_isolation(client, signup):
    acct = await signup("lead-owner@example.com")
    other = await signup("other-org@example.com")
    api_key = (await make_key(client, acct, name="autopilot-key"))["api_key"]

    r1 = await client.post(
        "/api/v1/autopilot/campaigns",
        headers={"X-API-Key": api_key},
        json={
            "name": "First SaaS",
            "target_keywords": ["b2b saas", "devtools"],
            "required_tech_stack": ["Stripe", "HubSpot"],
            "require_hiring": True,
            "daily_lead_quota": 15,
            "target_crm_provider": "none",
        },
    )
    assert r1.status_code == 201, r1.text
    c1 = r1.json()
    assert c1["status"] == "active" and c1["daily_lead_quota"] == 15

    r2 = await client.post(
        "/api/v1/autopilot/campaigns",
        headers=acct["jwt"],
        json={"name": "Second SaaS", "target_keywords": ["shopify agency"]},
    )
    assert r2.status_code == 201
    c2 = r2.json()

    listed = await client.get("/api/v1/autopilot/campaigns", headers={"X-API-Key": api_key})
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [c2["id"], c1["id"]]

    # Malformed UUID -> 422; cross-org access -> 404
    assert (await client.patch("/api/v1/autopilot/campaigns/not-a-uuid", headers=acct["jwt"], json={"status": "paused"})).status_code == 422
    assert (await client.patch(f"/api/v1/autopilot/campaigns/{c1['id']}", headers=other["jwt"], json={"status": "paused"})).status_code == 404
    assert (await client.delete(f"/api/v1/autopilot/campaigns/{c1['id']}", headers=other["jwt"])).status_code == 404
    assert (await client.post(f"/api/v1/autopilot/campaigns/{c1['id']}/run-now", headers=other["jwt"])).status_code == 404
    assert (await client.get(f"/api/v1/autopilot/campaigns/{c1['id']}/leads", headers=other["jwt"])).status_code == 404

    patched = await client.patch(
        f"/api/v1/autopilot/campaigns/{c1['id']}",
        headers=acct["jwt"],
        json={"status": "paused", "daily_lead_quota": 50, "require_hiring": False},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "paused" and patched.json()["daily_lead_quota"] == 50

    deleted = await client.delete(f"/api/v1/autopilot/campaigns/{c2['id']}", headers=acct["jwt"])
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True


async def test_discover_candidate_domains_extracts_and_filters_noise(monkeypatch):
    seen_urls: list[str] = []
    ddg_html = """
    <html><body>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.AcmeSaaS.io%2Fpricing">Acme</a>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Facme">LinkedIn</a>
      <a class="result__a" href="https://employinc.com/wrestling">Employ</a>
      <a class="result__a" href="https://jazzhr.com/platform">JazzHR</a>
      <a class="result__a" href="https://workable.com/features">Workable</a>
      <a class="result__a" href="https://en.wikipedia.org/wiki/Software">Wiki</a>
      <a class="result__a" href="https://g2.com/products/foo">G2</a>
      <a class="result__a" href="https://github.com/acme">GitHub</a>
    </body></html>
    """
    gh_html = """
    <html><body>
      <a href="https://betaops.com/careers">BetaOps</a>
      <a href="https://boards.greenhouse.io/acme">GH</a>
      <a href="https://crunchbase.com/organization/betaops">CB</a>
    </body></html>
    """
    lever_html = """<html><body><a href="https://gammaflow.ai">GammaFlow</a><a href="https://jobs.lever.co/foo">Lever</a></body></html>"""
    ashby_html = """<html><body><a href="https://acme-saas.io/jobs">Ignore</a><a href="https://jobs.ashbyhq.com/bar">Ashby</a><a href="https://twitter.com/x">X</a></body></html>"""

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        h = request.url.host
        if h == "html.duckduckgo.com":
            return httpx.Response(200, text=ddg_html)
        if h == "boards.greenhouse.io":
            return httpx.Response(200, text=gh_html)
        if h == "jobs.lever.co":
            return httpx.Response(200, text=lever_html)
        if h == "jobs.ashbyhq.com":
            return httpx.Response(200, text=ashby_html)
        return httpx.Response(404)

    monkeypatch.setattr(discovery, "_transport", httpx.MockTransport(handler))
    domains = await discovery.discover_candidate_domains(["b2b saas"], limit=10)
    assert domains == ["acmesaas.io", "betaops.com", "gammaflow.ai", "acme-saas.io"]
    assert seen_urls[0].startswith("https://html.duckduckgo.com/html/?q=")
    assert "company+OR+official+site" in seen_urls[0] and "-site%3Alinkedin.com" in seen_urls[0]


async def test_autopilot_icp_dedup_credits_crm_push_and_csv_export(client, signup, dns, monkeypatch):
    acct = await signup("autopilot@example.com")
    dns[("api.hubapi.com", "A")] = [PUBLIC_IP]

    # Candidate behavior:
    # 1. alpha.io -> matches Stripe + hiring + valid & catch_all emails -> DELIVERED (1 credit)
    # 2. bravo.io -> lacks required tech (no Stripe) -> FILTERED OUT
    # 3. charlie.io -> has Stripe, NOT hiring -> FILTERED OUT
    # 4. delta.io -> has Stripe + hiring + unverifiable_network with valid MX -> DELIVERED (1 credit)
    # 5. echo.io -> has Stripe + hiring, all emails invalid -> FILTERED OUT
    async def fake_discover(keywords, limit=30):
        return ["alpha.io", "bravo.io", "charlie.io", "delta.io", "echo.io"]

    enriched_map = {
        "alpha.io": {
            "domain": "alpha.io",
            "company": {"name": "Alpha Inc", "description": "Alpha B2B", "website": "https://alpha.io"},
            "tech_stack": [{"name": "Stripe", "category": "Payments"}, {"name": "React", "category": "Frontend"}],
            "email": {"provider": "Google Workspace", "mx_hosts": ["aspmx.l.google.com"], "spf": True},
            "hiring": {"has_careers_page": True, "careers_url": "https://alpha.io/careers", "ats": ["Greenhouse"]},
        },
        "bravo.io": {
            "domain": "bravo.io",
            "company": {"name": "Bravo LLC"},
            "tech_stack": [{"name": "Shopify", "category": "E-commerce"}],
            "email": {"provider": "Microsoft 365"},
            "hiring": {"has_careers_page": True, "ats": ["Lever"]},
        },
        "charlie.io": {
            "domain": "charlie.io",
            "company": {"name": "Charlie Co"},
            "tech_stack": [{"name": "Stripe", "category": "Payments"}],
            "email": {"provider": "Google Workspace"},
            "hiring": {"has_careers_page": False, "ats": []},
        },
        "delta.io": {
            "domain": "delta.io",
            "company": {"name": "Delta Labs", "description": "Delta Infra", "website": "https://delta.io"},
            "tech_stack": [{"name": "Stripe", "category": "Payments"}, {"name": "HubSpot", "category": "CRM"}],
            "email": {"provider": "Microsoft 365", "mx_hosts": ["delta-io.mail.protection.outlook.com"], "spf": True},
            "hiring": {"has_careers_page": True, "ats": ["Ashby"]},
        },
        "echo.io": {
            "domain": "echo.io",
            "company": {"name": "Echo Tech"},
            "tech_stack": [{"name": "Stripe", "category": "Payments"}],
            "email": {"provider": "Google Workspace"},
            "hiring": {"has_careers_page": True, "ats": ["Lever"]},
        },
    }

    async def fake_enrich(domain):
        return enriched_map[domain]

    async def fake_verify(email):
        local, dom = email.split("@", 1)
        if dom == "alpha.io":
            status = "valid" if local == "founders" else ("catch_all" if local == "sales" else "invalid")
            return {"email": email, "format_valid": True, "mx_valid": True, "smtp_deliverable": status, "provider": "Google Workspace"}
        if dom == "delta.io":
            return {"email": email, "format_valid": True, "mx_valid": True, "smtp_deliverable": "unverifiable_network", "provider": "Microsoft 365"}
        return {"email": email, "format_valid": True, "mx_valid": True, "smtp_deliverable": "invalid", "provider": "Google Workspace"}

    crm_pushes = []

    def crm_handler(request: httpx.Request) -> httpx.Response:
        crm_pushes.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "hs-1"})

    monkeypatch.setattr(discovery, "discover_candidate_domains", fake_discover)
    monkeypatch.setattr(discovery, "enrich_domain", fake_enrich)
    monkeypatch.setattr(discovery, "verify_email", fake_verify)
    monkeypatch.setattr("app.worker.discover_candidate_domains", fake_discover)
    monkeypatch.setattr(crm, "_transport", httpx.MockTransport(crm_handler))

    c1_resp = await client.post(
        "/api/v1/autopilot/campaigns",
        headers=acct["jwt"],
        json={
            "name": "Stripe Hiring",
            "target_keywords": ["b2b saas"],
            "required_tech_stack": ["stripe"],  # case-insensitive match
            "require_hiring": True,
            "daily_lead_quota": 10,
            "target_crm_provider": "hubspot",
            "target_crm_url_or_token": "pat-secret-123",
        },
    )
    assert c1_resp.status_code == 201
    c1_id = c1_resp.json()["id"]

    # Run via POST /run-now (falls back cleanly to BackgroundTasks when no ARQ worker is active)
    run_resp = await client.post(f"/api/v1/autopilot/campaigns/{c1_id}/run-now", headers=acct["jwt"])
    assert run_resp.status_code == 202

    # Check credits deducted: 50 - 2 = 48 (alpha.io + delta.io)
    me = (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()
    assert me["credit_balance"] == 48
    assert await redis_client.get_redis().get(f"org:credits:{acct['org_id']}") == "48"

    # Check CRM pushed both delivered leads
    assert {p["properties"]["domain"] for p in crm_pushes} == {"alpha.io", "delta.io"}

    # Check paginated JSON leads
    leads_resp = await client.get(f"/api/v1/autopilot/campaigns/{c1_id}/leads?limit=1&offset=0", headers=acct["jwt"])
    assert leads_resp.status_code == 200
    lj = leads_resp.json()
    assert lj["total"] == 2 and len(lj["items"]) == 1

    all_leads = (await client.get(f"/api/v1/autopilot/campaigns/{c1_id}/leads", headers=acct["jwt"])).json()["items"]
    by_dom = {item["domain"]: item for item in all_leads}
    assert set(by_dom) == {"alpha.io", "delta.io"}
    assert by_dom["alpha.io"]["verified_emails"] == ["founders@alpha.io", "sales@alpha.io"]
    assert by_dom["delta.io"]["verified_emails"] == ["founders@delta.io", "sales@delta.io", "hello@delta.io"]

    # Check CSV export
    csv_resp = await client.get(f"/api/v1/autopilot/campaigns/{c1_id}/leads?format=csv", headers=acct["jwt"])
    assert csv_resp.status_code == 200 and csv_resp.headers["content-type"].startswith("text/csv")
    csv_lines = csv_resp.text.strip().splitlines()
    assert csv_lines[0] == "domain,company_name,email_provider,verified_emails,tech_stack,hiring_ats,delivered_at"
    assert len(csv_lines) == 3

    # Check UsageLog recorded
    async with dbmod.SessionLocal() as s:
        logs = (
            await s.execute(select(UsageLog).where(UsageLog.org_id == acct["org_id"], UsageLog.endpoint == f"AUTOPILOT {c1_id}"))
        ).scalars().all()
    assert len(logs) == 1 and logs[0].credits_used == 2

    # Second campaign in SAME org discovers same alpha.io & delta.io -> MUST deduplicate and charge 0 credits
    c2_id = (
        await client.post(
            "/api/v1/autopilot/campaigns",
            headers=acct["jwt"],
            json={"name": "Overlap Campaign", "target_keywords": ["b2b saas"], "required_tech_stack": ["Stripe"]},
        )
    ).json()["id"]
    delivered_c2 = await execute_single_campaign(None, c2_id)
    assert delivered_c2 == 0
    assert (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"] == 48

    # Paused campaign is skipped by both execute_single_campaign and run_all_active_autopilot_campaigns
    await client.patch(f"/api/v1/autopilot/campaigns/{c1_id}", headers=acct["jwt"], json={"status": "paused"})
    await client.patch(f"/api/v1/autopilot/campaigns/{c2_id}", headers=acct["jwt"], json={"status": "paused"})
    assert await execute_single_campaign(None, c1_id) == 0
    assert await run_all_active_autopilot_campaigns(None) == 0
    assert any(fn is execute_single_campaign for fn in WorkerSettings.functions)
    assert len(WorkerSettings.cron_jobs) == 1
