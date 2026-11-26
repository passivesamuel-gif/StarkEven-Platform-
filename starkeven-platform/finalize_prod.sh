#!/usr/bin/env bash
# Final integrity check + production secret generation. Safe to re-run: it only fills
# placeholder values and NEVER overwrites a secret you (or an earlier run) already set.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/3 Integrity check =="
fail=0
required=(
  requirements.txt Dockerfile docker-compose.yml Caddyfile .env.example alembic.ini
  alembic/env.py alembic/versions/0001_initial.py
  app/main.py app/config.py app/db.py app/models.py app/security.py app/worker.py
  app/routes/auth.py app/routes/keys.py app/routes/enrich.py app/routes/bulk.py
  app/routes/billing.py app/routes/verify.py app/routes/integrations.py
  app/engine/enrichment.py app/engine/smtp.py app/engine/crm.py
  tests/conftest.py pytest.ini
  frontend/package.json frontend/Dockerfile frontend/src/app/page.tsx
  frontend/src/app/dashboard/page.tsx frontend/src/lib/api.ts
  scripts/deploy_prod.sh
)
for f in "${required[@]}"; do
  [ -s "$f" ] || { echo "  MISSING/EMPTY: $f"; fail=1; }
done
python3 - <<'PY' || fail=1
import compileall, json, sys
ok = compileall.compile_dir("app", quiet=1) and compileall.compile_dir("tests", quiet=1) and compileall.compile_dir("alembic", quiet=1)
json.load(open("frontend/package.json"))
sys.exit(0 if ok else 1)
PY
for s in *.sh scripts/*.sh; do bash -n "$s" || { echo "  bash syntax error: $s"; fail=1; }; done
if [ -x frontend/node_modules/.bin/tsc ]; then
  (cd frontend && node_modules/.bin/tsc --noEmit) || fail=1
else
  echo "  (frontend type-check runs during 'docker compose build frontend')"
fi
if command -v docker >/dev/null 2>&1 && [ -f .env ]; then
  docker compose config -q || fail=1
fi
[ "$fail" = 0 ] || { echo "Integrity check FAILED"; exit 1; }
echo "  OK"

echo "== 2/3 Secrets =="
[ -f .env ] || cp .env.example .env
rand_hex() { openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))'; }
for key in POSTGRES_PASSWORD JWT_SECRET_KEY ADMIN_API_KEY WEBHOOK_SECRET; do
  cur="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- || true)"
  if [ -z "$cur" ] || [[ "$cur" == replace-with* ]] || [[ "$cur" == change-me* ]]; then
    val="$(rand_hex)"
    if grep -qE "^${key}=" .env; then sed -i "s#^${key}=.*#${key}=${val}#" .env; else echo "${key}=${val}" >> .env; fi
    echo "  generated ${key}"
  else
    echo "  kept existing ${key}"
  fi
done
chmod 600 .env
echo "  .env ready (permissions 600). Set SITE_ADDRESS to your domain for automatic HTTPS."

echo "== 3/3 Summary =="
printf '%-10s %s\n' "SERVICE" "ROLE"
printf '%-10s %s\n' "caddy" "reverse proxy, HTTP(S) on :80/:443"
printf '%-10s %s\n' "frontend" "Next.js landing page + dashboard"
printf '%-10s %s\n' "api" "FastAPI (docs at /docs)"
printf '%-10s %s\n' "worker" "ARQ bulk-enrichment worker"
printf '%-10s %s\n' "postgres" "PostgreSQL 16 (internal only)"
printf '%-10s %s\n' "redis" "Redis 7: cache, rate limits, job queue (internal only)"
echo
printf '%-7s %-34s %s\n' "METHOD" "ENDPOINT" "AUTH"
while IFS='|' read -r m p a; do printf '%-7s %-34s %s\n' "$m" "$p" "$a"; done <<'EP'
POST|/api/v1/auth/register|public
POST|/api/v1/auth/login|public
POST|/api/v1/demo/lookup|public (per-IP limit)
GET|/api/v1/orgs/me|JWT or key
GET|/api/v1/orgs/me/usage|JWT or key
POST|/api/v1/keys|JWT
GET|/api/v1/keys|JWT
POST|/api/v1/keys/{id}/rotate|JWT
DELETE|/api/v1/keys/{id}|JWT
GET|/api/v1/protected/ping|key/JWT enrich:read (1 credit)
POST|/api/v1/enrich/domain|key/JWT enrich:read (1 credit)
POST|/api/v1/enrich/bulk|key/JWT bulk:write
GET|/api/v1/enrich/bulk/{id}|key/JWT bulk:write
GET|/api/v1/enrich/bulk/{id}/download|key/JWT bulk:write
POST|/api/v1/verify/email|key/JWT enrich:read (1 credit)
POST|/api/v1/export/crm|key/JWT enrich:read
POST|/api/v1/webhooks/billing|HMAC signature
POST|/api/v1/admin/orgs/{id}/credits|X-Admin-Key
GET|/health|public
EP
echo
echo "Next: ./scripts/deploy_prod.sh"
