import asyncio
import logging
import time
import uuid

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from . import db as dbmod
from . import redis_client
from .config import settings
from .credits import spend_org_credits
from .engine.discovery import discover_candidate_domains, qualify_and_verify_lead
from .engine.enrichment import enrich_cached, flatten
from .engine.notifications import send_campaign_completion_report, send_low_credit_warning_if_needed
from .engine.webhooks import callback_signing_secret, send_signed_webhook
from .errors import DomainNotFound, InsufficientCredits
from .models import AutopilotCampaign, BulkJob, DeliveredLead, Organization, UsageLog, utcnow
from .netguard import Unresolvable, UnsafeTarget, normalize_domain
from .routes.integrations import push_lead_to_crm

log = logging.getLogger("starkeven.worker")
CONCURRENCY = 10
AUTOPILOT_CONCURRENCY = 5
PERSIST_EVERY = 100


async def _process_domain(raw: str, org_id: int, redis, counters: dict) -> dict:
    try:
        domain = normalize_domain(raw)
    except ValueError:
        return {"domain": raw, "status": "error", "error": "invalid_domain"}

    async def pay():
        await spend_org_credits(org_id, 1)  # 1 credit per uncached domain
        counters["credits"] += 1

    try:
        data, cached = await enrich_cached(domain, redis, charge=pay)
        return flatten(data, cached)
    except InsufficientCredits:
        return {"domain": domain, "status": "error", "error": "insufficient_credits"}
    except DomainNotFound:
        return {"domain": domain, "status": "error", "error": "domain_not_found"}
    except (UnsafeTarget, Unresolvable):
        return {"domain": domain, "status": "error", "error": "unsafe_target"}
    except Exception:
        log.exception("enrichment failed for %s", domain)
        return {"domain": domain, "status": "error", "error": "enrichment_failed"}


async def _save(job_id: str, **values) -> None:
    async with dbmod.SessionLocal() as s:
        job = await s.get(BulkJob, job_id)
        for k, v in values.items():
            setattr(job, k, v)
        await s.commit()


async def run_bulk_job(job_id: str) -> None:
    redis = redis_client.get_redis()
    async with dbmod.SessionLocal() as s:
        res = await s.execute(
            update(BulkJob)
            .where(BulkJob.id == job_id, BulkJob.status == "queued")
            .values(status="processing")
            .returning(BulkJob.id)
        )
        if res.scalar_one_or_none() is None:
            return  # unknown, or already picked up: never process (and charge) twice
        await s.commit()
        job = await s.get(BulkJob, job_id)
        domains = [r["domain"] for r in job.results_json]
        org_id, webhook_url = job.org_id, job.webhook_url

    results: list = [None] * len(domains)
    counters = {"credits": 0, "done": 0}
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()

    async def one(i: int, d: str):
        async with sem:
            row = await _process_domain(d, org_id, redis, counters)
        async with lock:
            results[i] = row
            counters["done"] += 1
            partial = counters["done"] % PERSIST_EVERY == 0
            await _save(
                job_id, processed_domains=counters["done"], credits_used=counters["credits"],
                **({"results_json": [r or {"domain": domains[k], "status": "pending"} for k, r in enumerate(results)]}
                   if partial else {}),
            )

    status, error = "completed", None
    try:
        await asyncio.gather(*(one(i, d) for i, d in enumerate(domains)))
        await _save(
            job_id, status="completed", results_json=results, processed_domains=len(domains),
            credits_used=counters["credits"], completed_at=utcnow(),
        )
    except Exception as e:  # noqa: BLE001
        log.exception("bulk job %s failed", job_id)
        status, error = "failed", str(e)[:500]
        await _save(job_id, status="failed", error=error, completed_at=utcnow(),
                    credits_used=counters["credits"], processed_domains=counters["done"])

    if webhook_url:
        payload = {
            "event": "bulk.completed" if status == "completed" else "bulk.failed",
            "batch_id": job_id, "status": status, "total_domains": len(domains),
            "processed_domains": counters["done"], "credits_used": counters["credits"],
            "download_url": f"{settings.public_base_url.rstrip('/')}/api/v1/enrich/bulk/{job_id}/download",
        }
        await send_signed_webhook(webhook_url, payload, callback_signing_secret(org_id), event=payload["event"])


async def execute_single_campaign(ctx, campaign_id: str) -> int:
    start = time.perf_counter()
    redis = redis_client.get_redis()
    try:
        cid = uuid.UUID(str(campaign_id))
    except (ValueError, TypeError):
        return 0

    async with dbmod.SessionLocal() as s:
        campaign = await s.get(AutopilotCampaign, cid)
        if campaign is None or campaign.status != "active":
            return 0
        org = await s.get(Organization, campaign.org_id)
        if org is None or org.credit_balance <= 0:
            return 0
        org_id = org.id
        budget = min(max(campaign.daily_lead_quota, 1), org.credit_balance)
        keywords = list(campaign.target_keywords or [])
        req_tech = list(campaign.required_tech_stack or [])
        require_hiring = bool(campaign.require_hiring)
        crm_provider = campaign.target_crm_provider
        crm_target = campaign.target_crm_url_or_token
        existing = set(
            (await s.execute(select(DeliveredLead.domain).where(DeliveredLead.org_id == org_id))).scalars().all()
        )

    candidates = await discover_candidate_domains(keywords, limit=max(budget * 3, 30))
    fresh_candidates = [d for d in candidates if d not in existing]
    if not fresh_candidates:
        async with dbmod.SessionLocal() as s:
            camp = await s.get(AutopilotCampaign, cid)
            if camp is not None:
                camp.last_run_at = utcnow()
                await s.commit()
        return 0

    sem = asyncio.Semaphore(AUTOPILOT_CONCURRENCY)

    async def _qualify(dom: str) -> dict | None:
        async with sem:
            return await qualify_and_verify_lead(dom, req_tech, require_hiring)

    qualified: list[dict] = []
    idx = 0
    while idx < len(fresh_candidates) and len(qualified) < budget:
        needed = budget - len(qualified)
        batch_size = min(len(fresh_candidates) - idx, max(needed, AUTOPILOT_CONCURRENCY))
        chunk = fresh_candidates[idx : idx + batch_size]
        idx += batch_size
        outcomes = await asyncio.gather(*(_qualify(d) for d in chunk), return_exceptions=True)
        for item in outcomes:
            if isinstance(item, dict):
                qualified.append(item)
                if len(qualified) >= budget:
                    break

    delivered: list[dict] = []
    latest_balance: int | None = None
    async with dbmod.SessionLocal() as s:
        camp = await s.get(AutopilotCampaign, cid)
        if camp is None or camp.status != "active":
            return 0
        for lead in qualified:
            try:
                async with s.begin_nested():
                    s.add(
                        DeliveredLead(
                            campaign_id=cid,
                            org_id=org_id,
                            domain=lead["domain"],
                            company_name=lead["company_name"],
                            tech_stack=lead["tech_stack"],
                            email_provider=lead["email_provider"],
                            verified_emails=lead["verified_emails"],
                            hiring_ats=lead["hiring_ats"],
                        )
                    )
                    await s.flush()
                    res = await s.execute(
                        update(Organization)
                        .where(Organization.id == org_id, Organization.credit_balance >= 1)
                        .values(credit_balance=Organization.credit_balance - 1)
                        .returning(Organization.credit_balance)
                        .execution_options(synchronize_session=False)
                    )
                    new_bal = res.scalar_one_or_none()
                    if new_bal is None:
                        raise InsufficientCredits()
                    latest_balance = int(new_bal)
                delivered.append(lead)
            except IntegrityError:
                continue
            except InsufficientCredits:
                break

        camp.total_leads_delivered = (camp.total_leads_delivered or 0) + len(delivered)
        camp.last_run_at = utcnow()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        s.add(
            UsageLog(
                org_id=org_id,
                api_key_id=None,
                endpoint=f"AUTOPILOT {cid}",
                status_code=200,
                credits_used=len(delivered),
                latency_ms=elapsed_ms,
            )
        )
        await s.commit()

    if latest_balance is not None:
        try:
            await redis.setex(f"org:credits:{org_id}", 300, str(latest_balance))
        except Exception:
            pass

    if delivered and crm_provider != "none" and crm_target:
        for lead in delivered:
            record = lead.get("enriched") or {
                "domain": lead["domain"],
                "company_name": lead["company_name"],
                "company": {"name": lead["company_name"]},
                "tech_stack": lead["tech_stack"],
                "verified_emails": lead["verified_emails"],
            }
            try:
                await push_lead_to_crm(crm_provider, crm_target, record)
            except Exception:
                log.exception("autopilot CRM push failed for %s (%s)", lead["domain"], crm_provider)

    if settings.environment != "test":
        async with dbmod.SessionLocal() as s:
            org_row = await s.get(Organization, org_id)
            camp_row = await s.get(AutopilotCampaign, cid)
            bal_now = int(org_row.credit_balance) if org_row else int(latest_balance or 0)
            camp_name = camp_row.name if camp_row else "Autopilot Campaign"
            total_now = int(camp_row.total_leads_delivered or 0) if camp_row else len(delivered)
        await send_campaign_completion_report(org_id, camp_name, len(delivered), total_now, bal_now)
        if latest_balance is not None:
            await send_low_credit_warning_if_needed(org_id, latest_balance)

    return len(delivered)


async def run_all_active_autopilot_campaigns(ctx) -> int:
    async with dbmod.SessionLocal() as s:
        ids = (
            await s.execute(select(AutopilotCampaign.id).where(AutopilotCampaign.status == "active"))
        ).scalars().all()
    for cid in ids:
        try:
            await execute_single_campaign(ctx, str(cid))
        except Exception:
            log.exception("autopilot campaign %s failed in scheduled run", cid)
    return len(ids)


async def process_bulk(ctx, job_id: str):
    await run_bulk_job(job_id)
    return job_id


async def shutdown(ctx):
    try:
        await redis_client.get_redis().delete("arq:queue:health-check")
    except Exception:
        pass
    await redis_client.close()


class WorkerSettings:
    functions = [process_bulk, execute_single_campaign]
    cron_jobs = [cron(run_all_active_autopilot_campaigns, hour={0, 6, 12, 18}, minute=0)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 7200
    health_check_interval = 30
    max_tries = 1  # a retry would re-run (and re-charge) a half-finished job
    keep_result = 3600
