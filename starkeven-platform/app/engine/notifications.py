"""Transactional email alerts for low credit warnings and Lead Autopilot campaign reports."""
import asyncio
import html
import logging
import math

from sqlalchemy import select

from .. import db as dbmod
from .. import redis_client
from ..config import settings
from ..models import Organization, User
from . import otp_mailer

logger = logging.getLogger("starkeven.notifications")
LOW_CREDIT_ALERT_COOLDOWN_S = 86400  # 24h per org to avoid repeated alerts on consecutive requests
_tasks: set = set()


def plan_baseline_credits(plan_tier: str) -> int:
    tier = (plan_tier or "").strip().lower()
    if tier in ("pro", "growth"):
        return 4000
    if tier in ("enterprise", "agency"):
        return 15000
    return 50


def low_credit_threshold(plan_tier: str) -> int:
    return math.ceil(plan_baseline_credits(plan_tier) * 0.1)


async def _org_recipient_emails(db, org_id: int) -> list[str]:
    rows = (
        await db.execute(
            select(User.email)
            .where(User.org_id == org_id, User.is_active.is_(True), User.is_verified.is_(True))
            .order_by(User.id.asc())
        )
    ).scalars().all()
    return [str(e) for e in rows if e]


async def clear_low_credit_cooldown(org_id: int) -> None:
    try:
        await redis_client.get_redis().delete(f"starkeven:alert:low_credit:{org_id}")
    except Exception:
        pass


async def send_low_credit_warning_if_needed(org_id: int, new_balance: int) -> bool:
    """Send a low-credit warning email when balance drops below 10% of plan quota and alerts are enabled."""
    try:
        async with dbmod.SessionLocal() as s:
            org = await s.get(Organization, org_id)
            if org is None or not org.notify_low_credits:
                return False
            threshold = low_credit_threshold(org.plan_tier)
            if new_balance >= threshold:
                return False
            recipients = await _org_recipient_emails(s, org_id)
            org_name = org.name

        if not recipients:
            return False

        redis = redis_client.get_redis()
        cooldown_key = f"starkeven:alert:low_credit:{org_id}"
        if not await redis.set(cooldown_key, "1", nx=True, ex=LOW_CREDIT_ALERT_COOLDOWN_S):
            return False

        safe_org = html.escape(org_name)
        subject = f"StarkEven: Low credit warning for {org_name}"
        html_body = (
            f"<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1D1D1F;max-width:520px;margin:0 auto;padding:24px;\">"
            f"<h2 style=\"margin:0 0 12px;font-size:20px;\">Low credit balance alert</h2>"
            f"<p style=\"margin:0 0 12px;color:#6E6E73;line-height:1.5;\">"
            f"Your workspace <strong>{safe_org}</strong> currently has <strong>{new_balance:,}</strong> credits remaining "
            f"(below the 10% plan threshold of {threshold:,} credits)."
            f"</p>"
            f"<p style=\"margin:0;color:#6E6E73;line-height:1.5;\">"
            f"Upgrade or top up in your Billing dashboard to keep enrichment, verification, and Lead Autopilot runs active."
            f"</p></div>"
        )
        text_body = (
            f"Low credit balance alert for {org_name}\n\n"
            f"Remaining credits: {new_balance:,} (below 10% threshold of {threshold:,}).\n"
            f"Visit your Billing dashboard to add credits and avoid interruptions.\n"
        )

        sent = False
        for email in recipients:
            try:
                await otp_mailer.send_email_message(email, subject, html_body, text_body)
                sent = True
            except Exception:
                logger.exception("Failed sending low credit alert to %s", email)
        if not sent:
            await redis.delete(cooldown_key)
        return sent
    except Exception:
        logger.exception("Low credit alert check failed for org %s", org_id)
        return False


async def send_campaign_completion_report(
    org_id: int,
    campaign_name: str,
    delivered_count: int,
    total_delivered: int,
    credits_remaining: int,
) -> bool:
    """Send a Lead Autopilot campaign completion summary email if enabled for the organization."""
    try:
        async with dbmod.SessionLocal() as s:
            org = await s.get(Organization, org_id)
            if org is None or not org.notify_campaign_reports:
                return False
            recipients = await _org_recipient_emails(s, org_id)
            org_name = org.name

        if not recipients:
            return False

        safe_org = html.escape(org_name)
        safe_campaign = html.escape(campaign_name)
        subject = f"StarkEven Autopilot Report: {campaign_name}"
        html_body = (
            f"<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1D1D1F;max-width:520px;margin:0 auto;padding:24px;\">"
            f"<h2 style=\"margin:0 0 12px;font-size:20px;\">Campaign run completed</h2>"
            f"<p style=\"margin:0 0 16px;color:#6E6E73;line-height:1.5;\">"
            f"Lead Autopilot finished a run for <strong>{safe_campaign}</strong> ({safe_org})."
            f"</p>"
            f"<ul style=\"margin:0 0 16px;padding-left:18px;color:#1D1D1F;line-height:1.6;\">"
            f"<li>New qualified leads delivered: <strong>{delivered_count:,}</strong></li>"
            f"<li>Total campaign leads delivered: <strong>{total_delivered:,}</strong></li>"
            f"<li>Remaining workspace credits: <strong>{credits_remaining:,}</strong></li>"
            f"</ul></div>"
        )
        text_body = (
            f"Lead Autopilot Report: {campaign_name} ({org_name})\n\n"
            f"- New qualified leads delivered: {delivered_count:,}\n"
            f"- Total campaign leads delivered: {total_delivered:,}\n"
            f"- Remaining workspace credits: {credits_remaining:,}\n"
        )

        sent = False
        for email in recipients:
            try:
                await otp_mailer.send_email_message(email, subject, html_body, text_body)
                sent = True
            except Exception:
                logger.exception("Failed sending campaign report to %s", email)
        return sent
    except Exception:
        logger.exception("Campaign completion report failed for org %s", org_id)
        return False


def schedule_low_credit_check(org_id: int, new_balance: int) -> None:
    """Schedule non-blocking low-credit check outside unit tests."""
    if settings.environment == "test" or new_balance >= 1500:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(send_low_credit_warning_if_needed(org_id, new_balance))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
