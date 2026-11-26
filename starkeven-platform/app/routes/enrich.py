from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..engine.enrichment import enrich_cached, sandbox_enrichment
from ..netguard import normalize_domain
from ..ratelimit import fixed_window
from ..redis_client import redis_dep
from ..security import AuthContext, charge, require
from ..utils import client_ip

router = APIRouter(prefix="/api/v1/enrich", tags=["enrichment"])
demo_router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    force_refresh: bool = False


def _domain_or_422(raw: str) -> str:
    try:
        return normalize_domain(raw)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/domain")
async def enrich_domain_route(
    payload: DomainIn, request: Request,
    ctx: AuthContext = Depends(require("enrich:read", billable=True)),
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    domain = _domain_or_422(payload.domain)
    if ctx.sandbox:
        return {"cached": False, "credits_used": 0, "sandbox": True, "data": sandbox_enrichment(domain)}

    async def pay():
        await charge(db, ctx, request, 1)

    data, cached = await enrich_cached(domain, redis, force_refresh=payload.force_refresh, charge=pay)
    return {"cached": cached, "credits_used": 0 if cached else 1, "data": data}


@demo_router.post("/lookup")
async def demo_lookup(payload: DomainIn, request: Request, redis: Redis = Depends(redis_dep)):
    """Public landing-page demo: no account, no credits, limited fields, per-IP rate limit."""
    allowed, retry = await fixed_window(
        redis, f"demo:{client_ip(request)}", settings.demo_lookups_per_hour, 3600
    )
    if not allowed:
        raise HTTPException(
            429, "Demo limit reached. Create a free account for 50 trial credits.",
            headers={"Retry-After": str(retry)},
        )
    domain = _domain_or_422(payload.domain)
    data, cached = await enrich_cached(domain, redis)
    return {
        "cached": cached,
        "data": {
            "domain": data["domain"], "company": data["company"],
            "tech_stack": data["tech_stack"][:8], "email": {"provider": data["email"]["provider"]},
            "hiring": {"has_careers_page": data["hiring"]["has_careers_page"]},
        },
    }
