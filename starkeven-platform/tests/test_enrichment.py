import json

from app import redis_client
from tests.conftest import make_key


async def _credits(client, acct):
    return (await client.get("/api/v1/orgs/me", headers=acct["jwt"])).json()["credit_balance"]


async def test_enrichment_parses_company_tech_email_and_hiring(client, signup, acme, site):
    acct = await signup()
    r = await client.post("/api/v1/enrich/domain", json={"domain": "https://www.Acme.com/pricing"}, headers=acct["jwt"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cached"] is False and body["credits_used"] == 1
    d = body["data"]
    assert d["domain"] == "acme.com"
    assert d["company"]["name"] == "Acme"
    assert d["company"]["description"] == "Acme builds rockets."
    assert d["company"]["linkedin"] == "https://www.linkedin.com/company/acme"
    assert d["company"]["twitter"] == "https://twitter.com/acme"
    assert d["company"]["github"] == "https://github.com/acme"
    names = {t["name"] for t in d["tech_stack"]}
    assert {"HubSpot", "Stripe", "Cloudflare", "Google Workspace"} <= names
    assert d["email"]["provider"] == "Google Workspace" and d["email"]["spf"] is True
    assert d["hiring"]["has_careers_page"] is True and d["hiring"]["ats"] == ["Greenhouse"]


async def test_results_are_cached_24h_and_cache_hits_are_free(client, signup, acme, site):
    acct = await signup()
    first = (await client.post("/api/v1/enrich/domain", json={"domain": "acme.com"}, headers=acct["jwt"])).json()
    ttl = await redis_client.get_redis().ttl("enrich:v2:acme.com")
    assert 86000 < ttl <= 86400
    second = (await client.post("/api/v1/enrich/domain", json={"domain": "acme.com"}, headers=acct["jwt"])).json()
    assert second["cached"] is True and second["credits_used"] == 0
    assert second["data"] == first["data"]
    assert site["calls"] == 1
    assert await _credits(client, acct) == 49

    forced = (await client.post("/api/v1/enrich/domain", json={"domain": "acme.com", "force_refresh": True},
                                headers=acct["jwt"])).json()
    assert forced["cached"] is False and site["calls"] == 2
    assert await _credits(client, acct) == 48


async def test_private_and_internal_targets_are_refused_without_charge(client, signup, dns, site):
    acct = await signup()
    dns[("intranet-host.example.com", "A")] = ["10.0.0.5"]
    dns[("rebind.example.com", "A")] = ["127.0.0.1"]
    for bad in ("localhost", "127.0.0.1", "redis", "db.internal", "http://10.0.0.5/x"):
        r = await client.post("/api/v1/enrich/domain", json={"domain": bad}, headers=acct["jwt"])
        assert r.status_code == 422, bad
    for bad in ("intranet-host.example.com", "rebind.example.com"):
        r = await client.post("/api/v1/enrich/domain", json={"domain": bad}, headers=acct["jwt"])
        assert r.status_code == 422 and r.json()["error"]["code"] == "unsafe_target"
    assert site["calls"] == 0
    assert await _credits(client, acct) == 50


async def test_domain_without_dns_is_not_charged(client, signup, dns, site):
    acct = await signup()
    r = await client.post("/api/v1/enrich/domain", json={"domain": "does-not-exist.example"}, headers=acct["jwt"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "domain_not_found"
    assert await _credits(client, acct) == 50


async def test_sandbox_key_returns_sample_data_for_free(client, signup, site):
    acct = await signup()
    raw = (await make_key(client, acct, environment="test"))["api_key"]
    assert raw.startswith("sk_test_")
    r = await client.post("/api/v1/enrich/domain", json={"domain": "acme.com"}, headers={"X-API-Key": raw})
    assert r.status_code == 200 and r.json()["sandbox"] is True and site["calls"] == 0
    assert await _credits(client, acct) == 50


async def test_public_demo_is_rate_limited_per_ip_and_hides_extras(client, acme, site, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_lookups_per_hour", 2)
    for _ in range(2):
        r = await client.post("/api/v1/demo/lookup", json={"domain": "acme.com"})
        assert r.status_code == 200
    assert "mx_hosts" not in json.dumps(r.json())
    r = await client.post("/api/v1/demo/lookup", json={"domain": "acme.com"})
    assert r.status_code == 429


async def test_bot_challenge_pages_do_not_pollute_company_metadata(client, signup, dns, monkeypatch):
    import httpx
    from app.engine import enrichment
    from tests.conftest import PUBLIC_IP

    acct = await signup()
    dns[("claude.ai", "A")] = [PUBLIC_IP]
    dns[("shield200.example.com", "A")] = [PUBLIC_IP]
    dns[("shield503.example.com", "A")] = [PUBLIC_IP]

    responses = {
        "claude.ai": httpx.Response(
            403,
            text="<html><head><title>Just a moment...</title></head><body>Enable JavaScript and cookies to continue</body></html>",
            headers={"content-type": "text/html", "server": "cloudflare"},
        ),
        "shield200.example.com": httpx.Response(
            200,
            text="<html><head><title>Attention Required! | Cloudflare</title></head><body>Blocked</body></html>",
            headers={"content-type": "text/html", "server": "cloudflare"},
        ),
        "shield503.example.com": httpx.Response(
            503,
            text="<html><head><title>Service Unavailable</title></head><body>Wait</body></html>",
            headers={"content-type": "text/html"},
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return responses[request.url.host]

    monkeypatch.setattr(enrichment, "_transport", httpx.MockTransport(handler))

    r = await client.post("/api/v1/enrich/domain", json={"domain": "claude.ai"}, headers=acct["jwt"])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["company"]["name"] == "Claude"
    assert d["company"]["title"] is None
    assert d["bot_protection_detected"] is True

    r2 = await client.post("/api/v1/enrich/domain", json={"domain": "shield200.example.com"}, headers=acct["jwt"])
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert d2["company"]["name"] == "Shield200"
    assert d2["company"]["title"] is None
    assert d2["bot_protection_detected"] is True

    r3 = await client.post("/api/v1/enrich/domain", json={"domain": "shield503.example.com"}, headers=acct["jwt"])
    assert r3.status_code == 200
    d3 = r3.json()["data"]
    assert d3["company"]["name"] == "Shield503"
    assert d3["company"]["title"] is None
    assert d3["bot_protection_detected"] is True


async def test_ssrf_blocks_loopback_docker_hosts_and_getaddrinfo_private_ips(client, signup, dns, site, monkeypatch):
    import socket
    import pytest
    from app.engine import enrichment
    from app.netguard import UnsafeTarget

    acct = await signup()
    for bad in ("127.0.0.1", "localhost", "app.local", "db.internal", "postgres", "redis", "api", "worker", "frontend", "caddy"):
        r = await client.post("/api/v1/enrich/domain", json={"domain": bad}, headers=acct["jwt"])
        assert r.status_code == 422, bad
        with pytest.raises(UnsafeTarget):
            await enrichment.enrich_domain(bad)

    real_getaddrinfo = socket.getaddrinfo
    for private_ip in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fc00::1"):
        target = "getaddr-rebind.example.com"

        def fake_getaddrinfo(host, port, *args, _ip=private_ip, _target=target, **kwargs):
            if host == _target:
                return [(socket.AF_INET6 if ":" in _ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (_ip, 0))]
            return real_getaddrinfo(host, port, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        r = await client.post("/api/v1/enrich/domain", json={"domain": target}, headers=acct["jwt"])
        assert r.status_code == 422 and r.json()["error"]["code"] == "unsafe_target"

    monkeypatch.setattr(socket, "getaddrinfo", real_getaddrinfo)

    assert site["calls"] == 0
    assert await _credits(client, acct) == 50
