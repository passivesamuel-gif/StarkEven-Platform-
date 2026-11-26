from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..engine.email_verify import EMAIL_RE, verify_email
from ..security import AuthContext, charge, require

router = APIRouter(prefix="/api/v1/verify", tags=["verification"])


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


@router.post("/email")
async def verify(
    payload: EmailIn, request: Request,
    ctx: AuthContext = Depends(require("enrich:read", billable=True)),
    db: AsyncSession = Depends(get_db),
):
    if ctx.sandbox:
        ok = bool(EMAIL_RE.match(payload.email.strip()))
        return {
            "email": payload.email.strip(), "format_valid": ok, "mx_valid": ok,
            "smtp_deliverable": "valid" if ok else "unknown", "provider": "Google Workspace" if ok else None,
            "sandbox": True,
        }
    result = await verify_email(payload.email)
    if result["format_valid"] and result["smtp_deliverable"] != "unverifiable_network":
        await charge(db, ctx, request, 1)
    return result
