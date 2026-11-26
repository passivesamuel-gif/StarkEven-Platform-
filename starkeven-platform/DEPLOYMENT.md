# StarkEven Production Deployment Guide

This guide covers deploying the full StarkEven B2B Lead & Data Intelligence platform using Docker Compose (`postgres`, `redis`, `api`, `worker`, `frontend`, `caddy`).

---

## 1. Prerequisites

- Linux server (Ubuntu 22.04/24.04 or Debian 12 recommended) with Docker Engine and Docker Compose v2 (`docker compose`).
- A domain name (e.g. `app.yourdomain.com`) with `A` / `AAAA` DNS records pointing to your server IP and TCP ports `80` and `443` open.
- Outbound TCP port `25` access if you want live SMTP mailbox verification (`POST /api/v1/verify/email`). If your VPS blocks port 25, SMTP probes gracefully return `smtp_deliverable: "unverifiable_network"` without charging credits.

---

## 2. Configure Environment & Secrets

Run the integrity and secret-generation script from the repository root (`/starkeven-platform`):

```bash
./finalize_prod.sh
```

This creates `.env` (permissions `600`) from `.env.example` and fills strong random hex values for:
- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `ADMIN_API_KEY`
- `WEBHOOK_SECRET`

Next, edit `.env` to configure your production domain, CORS, and SMTP identity:

```dotenv
ENVIRONMENT=production
SITE_ADDRESS=app.yourdomain.com
PUBLIC_BASE_URL=https://app.yourdomain.com
ALLOWED_ORIGINS=https://app.yourdomain.com
SMTP_HELO_DOMAIN=verify.yourdomain.com
```

> **Note:** Setting `SITE_ADDRESS` to your domain causes Caddy (`Caddyfile`) to automatically provision and renew Let's Encrypt TLS certificates. Keep `ENVIRONMENT=production` — the API refuses to start in production if placeholder secrets are present.

### Checkout Link Configuration (Frontend Build Args / Env)

The dashboard Billing tab (`Starter $79/mo`, `Growth $199/mo`, `Agency $499/mo`) links directly to your Lemon Squeezy or Stripe hosted checkout URLs and automatically appends `?checkout[custom][org_id]=<org_id>`.

Because `NEXT_PUBLIC_*` variables are inlined at Next.js build time (`frontend/Dockerfile`), export them in your shell or pass them via `frontend/.env.production` before building the frontend image:

```dotenv
NEXT_PUBLIC_CHECKOUT_STARTER_URL=https://yourstore.lemonsqueezy.com/buy/starter-variant
NEXT_PUBLIC_CHECKOUT_GROWTH_URL=https://yourstore.lemonsqueezy.com/buy/growth-variant
NEXT_PUBLIC_CHECKOUT_AGENCY_URL=https://yourstore.lemonsqueezy.com/buy/agency-variant
```

If you expose these via `docker compose build`, add matching `ARG NEXT_PUBLIC_CHECKOUT_*` / `ENV NEXT_PUBLIC_CHECKOUT_*` directives in `frontend/Dockerfile` or place them in `frontend/.env.production` prior to `docker compose build`.

---

## 3. Database Migrations & Deploy

Run the automated deployment script:

```bash
./scripts/deploy_prod.sh
```

This script performs the full production pipeline safely in order:
1. Validates `.env` contains no placeholder secrets.
2. Builds all Docker images (`api`, `worker`, `frontend`).
3. Starts `postgres` (PostgreSQL 16) and `redis` (Redis 7 with AOF persistence).
4. Runs Alembic migrations (`alembic upgrade head`, applying `0001_initial.py` and `0002_autopilot.py`).
5. Executes the full `pytest` suite against `starkeven_test` + Redis DB `15` and aborts before exposing traffic if any test fails.
6. Starts all services (`api`, `worker`, `frontend`, `caddy`) and waits for `/health` to report `healthy`.

### Manual Migration / Test Commands

```bash
# Run migrations manually
docker compose run --rm api alembic upgrade head

# Run backend test suite
docker compose run --rm api pytest -v
```

---

## 4. Billing Webhook Configuration (Stripe & Lemon Squeezy)

Credits are granted exclusively via signed billing webhooks at:

```
POST https://app.yourdomain.com/api/v1/webhooks/billing
```

- **Authentication (Required):** Requests without a valid `Stripe-Signature` (HMAC-SHA256 with 5-minute replay tolerance) or Lemon Squeezy `X-Signature` (HMAC-SHA256 hex digest using `WEBHOOK_SECRET`) are rejected with `HTTP 401`.
- **Idempotency:** Events are deduplicated atomically in Redis (`starkeven:webhook:{provider}:{event_id}`, 7-day TTL) and durably via a `UNIQUE(event_id)` constraint in PostgreSQL (`billing_events`). Duplicate deliveries safely return `200 {"ok": true, "duplicate": true, "status": "duplicate"}`.
- **Required Metadata:** Configure your checkout product / session metadata with:
  - `org_id`: StarkEven numeric organization ID (passed automatically via `?checkout[custom][org_id]=...`)
  - `credits`: Integer credit pack amount (e.g. `1000`, `4000`, `15000`)
  - `plan_tier` (optional): `starter`, `pro`, or `enterprise`

### Manual Admin Credit Grant (Break-Glass)

To manually credit an organization from an operator terminal:

```bash
curl -X POST https://app.yourdomain.com/api/v1/admin/orgs/1/credits \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"credits": 500, "reason": "Manual invoice"}'
```

---

## 5. Background Workers & Lead Autopilot

The `worker` container runs `arq app.worker.WorkerSettings`, handling:
- **Bulk CSV Enrichment Jobs** (`POST /api/v1/enrich/bulk`) with concurrency control and optional HMAC-signed completion webhooks.
- **Lead Autopilot Discovery & Verification** (`POST /api/v1/autopilot/campaigns/{id}/run-now` plus an automatic cron run every 6 hours at `00:00`, `06:00`, `12:00`, `18:00` UTC).

Monitor worker logs with:

```bash
docker compose logs -f worker
```

---

## 6. Post-Deploy Verification & Hardening

1. **Health Check:**
   ```bash
   curl -fsS https://app.yourdomain.com/health
   # {"status":"ok","service":"starkeven-api"}
   ```
2. **Billing Webhook Security Smoke Check:**
   ```bash
   # Unsigned webhook must return 401
   curl -i -X POST https://app.yourdomain.com/api/v1/webhooks/billing \
     -H "Content-Type: application/json" -d '{}'
   ```
3. **Egress / SSRF Defense-in-Depth:**
   Application-level DNS resolution (`app/netguard.py`) blocks `localhost`, `.local`, `.internal`, Docker service hostnames, and private/reserved/loopback/link-local IPv4 & IPv6 CIDRs (`HTTP 422`). For defense-in-depth against DNS rebinding, restrict outbound container egress to RFC1918 / link-local ranges on the Docker host firewall.
4. **Database & Redis Backups:**
   Back up the `pgdata` volume regularly (`pg_dump` via the `postgres` container) and keep `.env` outside version control.
