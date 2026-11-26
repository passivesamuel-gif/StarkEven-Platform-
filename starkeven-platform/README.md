# StarkEven: B2B Lead & Data Intelligence API

FastAPI + PostgreSQL + Redis + ARQ worker, with a Next.js dashboard behind Caddy. No AI/LLM calls at runtime:
enrichment is deterministic (HTTP fetch, HTML parsing, DNS, pattern matching).

## Deploy

```bash
./finalize_prod.sh          # integrity check + generates .env secrets (never overwrites existing ones)
# edit .env: SITE_ADDRESS=api.yourdomain.com (automatic HTTPS), PUBLIC_BASE_URL, SMTP_HELO_DOMAIN
./scripts/deploy_prod.sh    # build -> migrate -> pytest -> go live (aborts before exposing anything if tests fail)
```

The app refuses to start with `ENVIRONMENT=production` and placeholder secrets.

## What is where

| Path | Purpose |
|---|---|
| `app/security.py` | dual auth (JWT or API key), scopes, per-org sliding-window rate limit, credit charging |
| `app/routes/*` | auth, keys, orgs, enrich (+ public demo), verify, bulk, export/crm, billing webhook, admin |
| `app/engine/*` | enrichment, tech fingerprinting (54 signatures), SMTP probe, CRM push, signed webhooks |
| `app/netguard.py` | SSRF protection for every outbound request |
| `app/worker.py` | ARQ bulk-enrichment worker |
| `alembic/versions/0001_initial.py` | schema |
| `tests/` | pytest suite (isolated `starkeven_test` DB, Redis db 15, DNS + HTTP mocked) |
| `*.sh` in the root | stage verification scripts (they check files and syntax; they do not generate code) |

## Behaviour worth knowing

- **Credits** are authoritative in Postgres and deducted atomically (`UPDATE ... WHERE balance >= n`). Usage logging is
  asynchronous (background task), so it never adds latency; the credit deduction itself is in the request path on purpose.
- **Caching**: enrichment results are cached in Redis for 24 h. A cached hit costs 0 credits. A live result is only
  cached after the charge succeeds. Domains with no DNS at all return 422 and are not charged.
- **Rate limit** is per organization (not per key), so creating more keys does not multiply the limit.
- **Sandbox keys** (`sk_test_...`) return deterministic sample data, cost nothing, and cannot run bulk jobs.
- **Public demo** (`POST /api/v1/demo/lookup`) powers the landing-page box: no account, trimmed fields, 5/hour per IP.
  Signed-in visitors use the real endpoint.
- **Billing webhook** (`POST /api/v1/webhooks/billing`) requires a valid signature (Lemon Squeezy `X-Signature`, or
  Stripe `Stripe-Signature` with a 5-minute window). Credits come from checkout metadata you set:
  `org_id`, `credits`, optional `plan_tier` (`starter|pro|enterprise`). Duplicate events are ignored (Redis + a unique DB row).
- **Bulk callbacks** are signed with a per-organization secret (shown in the dashboard's Bulk tab):
  `X-StarkEven-Signature: sha256=HMAC(secret, "<timestamp>.<raw body>")`.
- **Email verification** needs outbound TCP port 25, which many cloud providers block. When blocked, results come back as
  `smtp_deliverable: "unknown"` with `reason: "connection_failed"`. Many servers also refuse probes from IPs
  without matching reverse DNS; set `SMTP_HELO_DOMAIN` to a domain you control.
- **Admin**: `POST /api/v1/admin/orgs/{id}/credits` with header `X-Admin-Key: $ADMIN_API_KEY` grants credits manually.

## Known limitations

- SSRF protection validates DNS answers before connecting but cannot fully rule out DNS rebinding between check and
  connect. For defence in depth, block outbound traffic from the `api` and `worker` containers to private ranges at the host firewall.
- A bulk job whose worker crashes mid-run stays in `processing` (retries are disabled to avoid double charging).
- Dashboard login token lives in `localStorage`; move to httpOnly cookies if you add third-party scripts.
- Pricing figures on the landing page are placeholders: edit `PLANS` in `frontend/src/app/page.tsx`.

## Local development

```bash
docker compose up -d postgres redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest -q
API_ORIGIN=http://localhost:8000 npm --prefix frontend run dev
```
