#!/usr/bin/env bash
# Stage 3 check: frontend, Caddy and compose wiring.
source "$(dirname "$0")/scripts/lib.sh"
check_stage "Stage 3 - frontend & proxy" \
  frontend/package.json frontend/Dockerfile frontend/tsconfig.json frontend/next.config.mjs \
  frontend/tailwind.config.ts frontend/postcss.config.mjs \
  frontend/src/app/layout.tsx frontend/src/app/globals.css frontend/src/app/page.tsx \
  frontend/src/app/login/page.tsx frontend/src/app/dashboard/page.tsx \
  frontend/src/lib/api.ts frontend/src/components/LiveDemo.tsx Caddyfile
