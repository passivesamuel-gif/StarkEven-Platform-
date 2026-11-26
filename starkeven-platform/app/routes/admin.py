import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import PLAN_LIMITS, settings
from ..db import get_db
from ..models import Organization

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(403, "Admin key required")


class Grant(BaseModel):
    credits: int = Field(ge=0, le=1_000_000)
    plan_tier: str | None = None


@router.post("/orgs/{org_id}/credits", dependencies=[Depends(require_admin)])
async def grant_credits(org_id: int, payload: Grant, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, org_id, with_for_update=True)
    if org is None:
        raise HTTPException(404, "Organization not found")
    org.credit_balance = Organization.credit_balance + payload.credits
    if payload.plan_tier:
        if payload.plan_tier not in PLAN_LIMITS:
            raise HTTPException(422, f"plan_tier must be one of {list(PLAN_LIMITS)}")
        org.plan_tier = payload.plan_tier
        org.rate_limit_per_min = PLAN_LIMITS[payload.plan_tier]
    await db.commit()
    await db.refresh(org)
    return {"organization_id": org.id, "credit_balance": org.credit_balance, "plan_tier": org.plan_tier}
