#!/usr/bin/env bash
# Stage 1 check: core platform, API keys, rate limiting, credits.
source "$(dirname "$0")/scripts/lib.sh"
check_stage "Stage 1 - core platform" \
  requirements.txt Dockerfile .env.example docker-compose.yml \
  app/config.py app/db.py app/models.py app/redis_client.py app/security.py \
  app/ratelimit.py app/credits.py app/usage.py app/errors.py app/main.py \
  app/routes/keys.py app/routes/orgs.py
