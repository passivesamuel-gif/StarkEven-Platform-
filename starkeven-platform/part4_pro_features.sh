#!/usr/bin/env bash
# Stage 4 check: bulk jobs, SMTP verification, CRM exports.
source "$(dirname "$0")/scripts/lib.sh"
check_stage "Stage 4 - pro features" \
  app/routes/bulk.py app/worker.py app/engine/smtp.py app/engine/email_verify.py \
  app/engine/crm.py app/engine/webhooks.py app/routes/verify.py app/routes/integrations.py \
  app/routes/admin.py tests/test_bulk_smtp_crm.py \
  frontend/src/components/BulkPanel.tsx frontend/src/components/VerifyPanel.tsx
