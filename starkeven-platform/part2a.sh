#!/usr/bin/env bash
# Stage 2a check: auth, schema migrations, error handling.
source "$(dirname "$0")/scripts/lib.sh"
check_stage "Stage 2a - auth & migrations" \
  app/routes/auth.py alembic.ini alembic/env.py alembic/script.py.mako alembic/versions/0001_initial.py \
  tests/conftest.py tests/test_auth_and_keys.py
