from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..engine.webhooks import callback_signing_secret
from ..models import Organization, UsageLog
from ..security import AuthContext, require

router = APIRouter(prefix="/api/v1/orgs", tags=["organization"])


class NotificationSettingsPatch(BaseModel):
    notify_low_credits: bool | None = None
    notify_campaign_reports: bool | None = None


@router.get("/me")
async def me(ctx: AuthContext = Depends(require()), db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, ctx.org.id)  # fresh balance
    out = {
        "id": org.id, "name": org.name, "plan_tier": org.plan_tier,
        "credit_balance": org.credit_balance, "rate_limit_per_min": org.rate_limit_per_min,
        "notify_low_credits": bool(org.notify_low_credits),
        "notify_campaign_reports": bool(org.notify_campaign_reports),
        "auth_method": ctx.via,
    }
    if ctx.user is not None:
        out["email"] = ctx.user.email
        out["role"] = ctx.user.role
        out["callback_signing_secret"] = callback_signing_secret(org.id)
    return out


@router.get("/me/notifications")
async def get_notification_settings(
    ctx: AuthContext = Depends(require(jwt_only=True)),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, ctx.org.id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return {
        "notify_low_credits": bool(org.notify_low_credits),
        "notify_campaign_reports": bool(org.notify_campaign_reports),
        "recipient_email": ctx.user.email if ctx.user else None,
    }


@router.patch("/me/notifications")
async def update_notification_settings(
    payload: NotificationSettingsPatch,
    ctx: AuthContext = Depends(require(jwt_only=True)),
    db: AsyncSession = Depends(get_db),
):
    if payload.notify_low_credits is None and payload.notify_campaign_reports is None:
        raise HTTPException(422, "Provide at least one notification setting to update")
    org = await db.get(Organization, ctx.org.id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    if payload.notify_low_credits is not None:
        org.notify_low_credits = payload.notify_low_credits
    if payload.notify_campaign_reports is not None:
        org.notify_campaign_reports = payload.notify_campaign_reports
    await db.commit()
    await db.refresh(org)
    return {
        "notify_low_credits": bool(org.notify_low_credits),
        "notify_campaign_reports": bool(org.notify_campaign_reports),
        "recipient_email": ctx.user.email if ctx.user else None,
    }


@router.get("/me/usage")
async def usage(
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(require()), db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(UsageLog).where(UsageLog.org_id == ctx.org.id).order_by(UsageLog.id.desc()).limit(limit)
    )).scalars().all()
    return [
        {
            "id": r.id, "endpoint": r.endpoint, "status_code": r.status_code,
            "credits_used": r.credits_used, "latency_ms": r.latency_ms, "created_at": r.created_at,
            "api_key_id": r.api_key_id,
        }
        for r in rows
    ]


@router.get("/me/usage/daily")
async def daily_usage(
    days: int = Query(30, ge=1, le=90),
    ctx: AuthContext = Depends(require()), db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    cutoff = datetime(start_day.year, start_day.month, start_day.day, tzinfo=timezone.utc)
    rows = (await db.execute(
        select(UsageLog.created_at, UsageLog.credits_used)
        .where(UsageLog.org_id == ctx.org.id, UsageLog.created_at >= cutoff)
    )).all()

    buckets = {
        (start_day + timedelta(days=i)).isoformat(): {"credits_used": 0, "requests": 0}
        for i in range(days)
    }
    total_credits = 0
    total_requests = 0
    for created_at, credits_used in rows:
        dt = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
        key = dt.date().isoformat()
        if key in buckets:
            c = int(credits_used or 0)
            buckets[key]["credits_used"] += c
            buckets[key]["requests"] += 1
            total_credits += c
            total_requests += 1

    return {
        "days": days,
        "total_credits": total_credits,
        "total_requests": total_requests,
        "daily": [{"date": d, **vals} for d, vals in buckets.items()],
    }
