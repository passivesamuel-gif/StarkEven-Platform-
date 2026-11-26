"""Test configuration. Tests run against the isolated `starkeven_test` Postgres database and
Redis logical DB 15, never the production database. Outbound HTTP and DNS are always mocked."""
import os
import urllib.parse

# --- must run before `app` is imported -----------------------------------------------------
os.environ["ENVIRONMENT"] = "test"
from sqlalchemy.engine import URL  # noqa: E402

_url = os.environ.get("TEST_DATABASE_URL") or URL.create(
    "postgresql+asyncpg",
    username=os.environ.get("POSTGRES_USER", "starkeven"),
    password=os.environ.get("POSTGRES_PASSWORD", "starkeven"),
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    database="starkeven_test",
).render_as_string(hide_password=False)
assert _url.split("?")[0].rsplit("/", 1)[-1] == "starkeven_test", "refusing to run tests on a non-test database"
os.environ["DATABASE_URL"] = _url
_r = urllib.parse.urlparse(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
os.environ["REDIS_URL"] = _r._replace(path="/15").geturl()
# -------------------------------------------------------------------------------------------

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

PUBLIC_IP = "93.184.216.34"
ACME_HTML = """<html><head><title>Acme | Rockets for everyone</title>
<meta name="description" content="Acme builds rockets.">
<script src="https://js.hs-scripts.com/123.js"></script><script src="https://js.stripe.com/v3/"></script></head>
<body><a href="https://www.linkedin.com/company/acme">LinkedIn</a><a href="https://twitter.com/acme">X</a>
<a href="https://github.com/acme">GitHub</a><a href="https://boards.greenhouse.io/acme">Jobs</a>
<a href="/careers">Careers</a></body></html>"""


@pytest_asyncio.fixture(autouse=True)
async def _clean_state():
    from app import db as dbmod
    from app import redis_client, usage
    from app.models import Base

    async with dbmod.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    redis_client.reset()
    await redis_client.get_redis().flushdb()
    yield
    await usage.drain()
    await redis_client.close()


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def dns(monkeypatch):
    """Dict-backed DNS: dns[("acme.com", "A")] = ["93.184.216.34"]. Unknown names return []."""
    from app.engine import dnsutil

    records: dict = {}

    async def fake_query(name, rdtype, **kw):
        return list(records.get((name.lower(), rdtype), []))

    monkeypatch.setattr(dnsutil, "query", fake_query)
    return records


@pytest.fixture
def acme(dns):
    for d in ("acme.com", "beta.io"):
        dns[(d, "A")] = [PUBLIC_IP]
        dns[(d, "MX")] = ["10 aspmx.l.google.com"]
        dns[(d, "TXT")] = ["v=spf1 include:_spf.google.com ~all"]
    dns[("aspmx.l.google.com", "A")] = ["142.250.1.1"]
    return dns


@pytest.fixture
def site(monkeypatch):
    """Mocked website responses for enrichment; state['calls'] counts live fetches."""
    from app.engine import enrichment

    state = {"calls": 0, "html": ACME_HTML}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(200, text=state["html"], headers={"content-type": "text/html", "server": "cloudflare"})

    monkeypatch.setattr(enrichment, "_transport", httpx.MockTransport(handler))
    return state


@pytest_asyncio.fixture
async def signup(client):
    import re
    from app.engine import otp_mailer

    async def _signup(email="owner@example.com", password="correct-horse-battery"):
        captured: list[str] = []
        orig_send = otp_mailer.send_email_message

        async def _capture(to_email: str, subject: str, html_body: str, text_body: str):
            m = re.search(r"Verification code:\s*(\d{6})", text_body)
            if m:
                captured.append(m.group(1))
            return {"delivery_mode": "dev_console"}

        otp_mailer.send_email_message = _capture
        try:
            r = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
            assert r.status_code == 201, r.text
        finally:
            otp_mailer.send_email_message = orig_send

        assert len(captured) == 1, "signup OTP was not dispatched"
        c = await client.post("/api/v1/auth/confirm-signup", json={"email": email, "code": captured[0]})
        assert c.status_code == 200, c.text
        body = c.json()
        return {
            "token": body["access_token"], "org_id": body["organization_id"],
            "jwt": {"Authorization": f"Bearer {body['access_token']}"},
        }

    return _signup


async def make_key(client, account, **payload):
    r = await client.post("/api/v1/keys", json=payload, headers=account["jwt"])
    assert r.status_code == 201, r.text
    return r.json()
