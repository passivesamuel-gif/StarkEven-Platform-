#!/usr/bin/env bash
# Stage 2b check: enrichment engine and billing webhooks.
source "$(dirname "$0")/scripts/lib.sh"
check_stage "Stage 2b - enrichment & billing" \
  app/netguard.py app/engine/dnsutil.py app/engine/enrichment.py app/engine/techdetect.py \
  app/engine/mailproviders.py app/billing_sig.py app/routes/enrich.py app/routes/billing.py \
  tests/test_enrichment.py tests/test_billing.py
