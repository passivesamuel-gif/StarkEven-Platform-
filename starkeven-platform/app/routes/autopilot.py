import csv
import io
import uuid
from typing import Literal

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..models import AutopilotCampaign, DeliveredLead
from ..netguard import UnsafeTarget, assert_public_url
from ..security import AuthContext, get_current_org
from ..worker import execute_single_campaign
from .bulk import safe_cell

router = APIRouter(prefix="/api/v1/autopilot", tags=["autopilot"])
_arq_pool = None

LEAD_CSV_FIELDS = [
    "domain",
    "company_name",
    "email_provider",
    "verified_emails",
    "tech_stack",
    "hiring_ats",
    "delivered_at",
]


async def enqueue_campaign(campaign_id: str) -> bool:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    if not await _arq_pool.exists("arq:queue:health-check"):
        return False
    await _arq_pool.enqueue_job("execute_single_campaign", campaign_id)
    return True


async def close_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: Literal["active", "paused"] = "active"
    target_keywords: list[str] = Field(min_length=1, max_length=25)
    required_tech_stack: list[str] = Field(default_factory=list, max_length=50)
    require_hiring: bool = False
    daily_lead_quota: int = Field(default=25, ge=1, le=500)
    target_crm_provider: Literal["none", "hubspot", "salesforce", "webhook"] = "none"
    target_crm_url_or_token: str | None = Field(default=None, max_length=512)

    @field_validator("target_keywords")
    @classmethod
    def _clean_keywords(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        if not cleaned:
            raise ValueError("Provide at least one non-empty keyword")
        return cleaned

    @field_validator("required_tech_stack")
    @classmethod
    def _clean_tech(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["active", "paused"] | None = None
    target_keywords: list[str] | None = Field(default=None, min_length=1, max_length=25)
    required_tech_stack: list[str] | None = Field(default=None, max_length=50)
    require_hiring: bool | None = None
    daily_lead_quota: int | None = Field(default=None, ge=1, le=500)
    target_crm_provider: Literal["none", "hubspot", "salesforce", "webhook"] | None = None
    target_crm_url_or_token: str | None = Field(default=None, max_length=512)

    @field_validator("target_keywords")
    @classmethod
    def _clean_keywords(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        if not cleaned:
            raise ValueError("Provide at least one non-empty keyword")
        return cleaned

    @field_validator("required_tech_stack")
    @classmethod
    def _clean_tech(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]


def _campaign_out(c: AutopilotCampaign) -> dict:
    return {
        "id": str(c.id),
        "org_id": c.org_id,
        "name": c.name,
        "status": c.status,
        "target_keywords": c.target_keywords,
        "required_tech_stack": c.required_tech_stack,
        "require_hiring": c.require_hiring,
        "daily_lead_quota": c.daily_lead_quota,
        "target_crm_provider": c.target_crm_provider,
        "target_crm_url_or_token": c.target_crm_url_or_token,
        "total_leads_delivered": c.total_leads_delivered,
        "last_run_at": c.last_run_at,
        "created_at": c.created_at,
    }


def _lead_out(lead: DeliveredLead) -> dict:
    return {
        "id": str(lead.id),
        "campaign_id": str(lead.campaign_id),
        "org_id": lead.org_id,
        "domain": lead.domain,
        "company_name": lead.company_name,
        "tech_stack": lead.tech_stack,
        "email_provider": lead.email_provider,
        "verified_emails": lead.verified_emails,
        "hiring_ats": lead.hiring_ats,
        "delivered_at": lead.delivered_at,
    }


async def _owned_campaign(db: AsyncSession, campaign_id: uuid.UUID, org_id: int) -> AutopilotCampaign:
    c = (
        await db.execute(
            select(AutopilotCampaign).where(AutopilotCampaign.id == campaign_id, AutopilotCampaign.org_id == org_id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    return c


async def _validate_crm(provider: str, target: str | None) -> str | None:
    cleaned = (target or "").strip() or None
    if provider == "webhook" and cleaned:
        try:
            await assert_public_url(cleaned)
        except ValueError as e:
            raise HTTPException(422, f"target_crm_url_or_token: {e}")
        except UnsafeTarget:
            raise HTTPException(422, "Webhook target resolves to a non-public address")
    return cleaned


@router.post("/campaigns", status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    crm_target = await _validate_crm(payload.target_crm_provider, payload.target_crm_url_or_token)
    c = AutopilotCampaign(
        org_id=ctx.org.id,
        name=payload.name.strip(),
        status=payload.status,
        target_keywords=payload.target_keywords,
        required_tech_stack=payload.required_tech_stack,
        require_hiring=payload.require_hiring,
        daily_lead_quota=payload.daily_lead_quota,
        target_crm_provider=payload.target_crm_provider,
        target_crm_url_or_token=crm_target,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _campaign_out(c)


@router.get("/campaigns")
async def list_campaigns(
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(AutopilotCampaign)
            .where(AutopilotCampaign.org_id == ctx.org.id)
            .order_by(AutopilotCampaign.created_at.desc())
        )
    ).scalars().all()
    return [_campaign_out(c) for c in rows]


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignPatch,
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    c = await _owned_campaign(db, campaign_id, ctx.org.id)
    data = payload.model_dump(exclude_unset=True)
    provider = data.get("target_crm_provider", c.target_crm_provider)
    target = data.get("target_crm_url_or_token", c.target_crm_url_or_token)
    if "target_crm_provider" in data or "target_crm_url_or_token" in data:
        data["target_crm_url_or_token"] = await _validate_crm(provider, target)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for k, v in data.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return _campaign_out(c)


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: uuid.UUID,
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    c = await _owned_campaign(db, campaign_id, ctx.org.id)
    await db.delete(c)
    await db.commit()
    return {"deleted": True, "id": str(campaign_id)}


@router.post("/campaigns/{campaign_id}/run-now", status_code=202)
async def run_campaign_now(
    campaign_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    c = await _owned_campaign(db, campaign_id, ctx.org.id)
    try:
        enqueued = await enqueue_campaign(str(c.id))
    except Exception:
        enqueued = False
    if enqueued is False:
        background_tasks.add_task(execute_single_campaign, None, str(c.id))
    return {"campaign_id": str(c.id), "status": "queued"}


@router.get("/campaigns/{campaign_id}/leads")
async def list_campaign_leads(
    campaign_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    format: Literal["json", "csv"] = Query("json"),
    ctx: AuthContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    c = await _owned_campaign(db, campaign_id, ctx.org.id)
    if format == "csv":
        rows = (
            await db.execute(
                select(DeliveredLead)
                .where(DeliveredLead.campaign_id == c.id, DeliveredLead.org_id == ctx.org.id)
                .order_by(DeliveredLead.delivered_at.desc())
            )
        ).scalars().all()

        def generate():
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(LEAD_CSV_FIELDS)
            yield buf.getvalue()
            for r in rows:
                buf.seek(0)
                buf.truncate(0)
                writer.writerow([
                    safe_cell(r.domain),
                    safe_cell(r.company_name),
                    safe_cell(r.email_provider),
                    safe_cell("; ".join(r.verified_emails or [])),
                    safe_cell("; ".join(r.tech_stack or [])),
                    safe_cell("; ".join(r.hiring_ats or [])),
                    safe_cell(r.delivered_at.isoformat() if r.delivered_at else ""),
                ])
                yield buf.getvalue()

        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="autopilot-{c.id}.csv"'},
        )

    total = await db.scalar(
        select(func.count())
        .select_from(DeliveredLead)
        .where(DeliveredLead.campaign_id == c.id, DeliveredLead.org_id == ctx.org.id)
    )
    rows = (
        await db.execute(
            select(DeliveredLead)
            .where(DeliveredLead.campaign_id == c.id, DeliveredLead.org_id == ctx.org.id)
            .order_by(DeliveredLead.delivered_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return {
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "items": [_lead_out(r) for r in rows],
    }
