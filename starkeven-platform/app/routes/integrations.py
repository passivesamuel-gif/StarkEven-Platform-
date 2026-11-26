from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..engine.crm import push_to_crm
from ..netguard import UnsafeTarget
from ..security import AuthContext, require

router = APIRouter(prefix="/api/v1/export", tags=["exports"])


class CRMExport(BaseModel):
    provider: Literal["hubspot", "salesforce", "webhook"]
    target_url_or_token: str = Field(min_length=1, max_length=4096)  # webhook URL, or HubSpot/Salesforce token
    enriched_record: dict
    instance_url: str | None = None  # Salesforce only, e.g. https://acme.my.salesforce.com
    salesforce_object: Literal["Account", "Lead"] = "Account"


@router.post("/crm")
async def export_crm(payload: CRMExport, ctx: AuthContext = Depends(require("enrich:read"))):
    if not isinstance(payload.enriched_record.get("domain"), str):
        raise HTTPException(422, "enriched_record.domain is required")
    try:
        return await push_to_crm(
            payload.provider, payload.target_url_or_token, payload.enriched_record,
            instance_url=payload.instance_url, sobject=payload.salesforce_object,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except UnsafeTarget:
        raise HTTPException(422, "Target URL resolves to a non-public address and was refused")


async def push_lead_to_crm(provider: str, target_url_or_token: str, lead_record: dict) -> dict:
    instance_url = None
    token_or_url = target_url_or_token
    if provider == "salesforce" and "|" in target_url_or_token:
        instance_url, token_or_url = target_url_or_token.split("|", 1)
    return await push_to_crm(provider, token_or_url, lead_record, instance_url=instance_url)
