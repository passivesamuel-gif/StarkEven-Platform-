from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import APIKey, utcnow
from ..redis_client import redis_dep
from ..security import ALLOWED_SCOPES, AuthContext, charge, hash_key, key_cache_name, new_key, require

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])
ping_router = APIRouter(prefix="/api/v1/protected", tags=["keys"])
MAX_ACTIVE_KEYS = 25


class KeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=120)
    environment: Literal["live", "test"] = "live"
    scopes: list[str] | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


def _row(k: APIKey) -> dict:
    return {
        "id": k.id, "name": k.name, "key_prefix": k.key_prefix, "scopes": k.scopes,
        "is_active": k.is_active, "expires_at": k.expires_at, "last_used_at": k.last_used_at,
        "created_at": k.created_at,
    }


def _issue(org_id: int, name: str, env: str, scopes: list[str], expires_at) -> tuple[str, APIKey]:
    raw = new_key(env)
    row = APIKey(
        org_id=org_id, name=name, key_prefix=raw[:12] + "...",  # e.g. "sk_live_a8f9..."
        key_hash=hash_key(raw), scopes=scopes, expires_at=expires_at,
    )
    return raw, row


@router.post("", status_code=201)
async def create_key(
    payload: KeyCreate | None = None,
    ctx: AuthContext = Depends(require(jwt_only=True)),
    db: AsyncSession = Depends(get_db),
):
    payload = payload or KeyCreate()
    scopes = payload.scopes if payload.scopes is not None else list(ALLOWED_SCOPES)
    if not scopes or any(s not in ALLOWED_SCOPES for s in scopes):
        raise HTTPException(422, f"scopes must be a non-empty subset of {list(ALLOWED_SCOPES)}")
    active = await db.scalar(
        select(func.count()).select_from(APIKey).where(APIKey.org_id == ctx.org.id, APIKey.is_active.is_(True))
    )
    if (active or 0) >= MAX_ACTIVE_KEYS:
        raise HTTPException(400, f"Active key limit ({MAX_ACTIVE_KEYS}) reached; revoke a key first")
    expires = utcnow() + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    raw, row = _issue(ctx.org.id, payload.name.strip(), payload.environment, scopes, expires)
    db.add(row)
    await db.commit()
    return {
        "api_key": raw, "id": row.id, "key_prefix": row.key_prefix, "scopes": scopes,
        "warning": "Store this key now; it will not be shown again.",
    }


@router.get("")
async def list_keys(ctx: AuthContext = Depends(require(jwt_only=True)), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(APIKey).where(APIKey.org_id == ctx.org.id).order_by(APIKey.id.desc())
    )).scalars().all()
    return [_row(k) for k in rows]  # never includes the key itself, only key_prefix


async def _owned_key(db: AsyncSession, org_id: int, key_id: int, *, for_update: bool = False) -> APIKey:
    stmt = select(APIKey).where(APIKey.id == key_id, APIKey.org_id == org_id)
    if for_update:
        stmt = stmt.with_for_update()
    key = (await db.execute(stmt)).scalar_one_or_none()
    if key is None:
        raise HTTPException(404, "API key not found")
    return key


@router.post("/{key_id}/rotate", status_code=201)
async def rotate_key(
    key_id: int, ctx: AuthContext = Depends(require(jwt_only=True)),
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    old = await _owned_key(db, ctx.org.id, key_id, for_update=True)
    if not old.is_active:
        raise HTTPException(409, "Key is already revoked")
    env = "test" if old.key_prefix.startswith("sk_test_") else "live"
    scopes = list(old.scopes or [])
    old.is_active = False
    raw, new = _issue(ctx.org.id, old.name, env, scopes, old.expires_at)
    db.add(new)
    await db.commit()  # revoke + replace in one transaction
    await redis.delete(key_cache_name(old.key_hash))
    return {
        "api_key": raw, "id": new.id, "key_prefix": new.key_prefix, "scopes": scopes,
        "replaced_key_id": old.id, "warning": "Store this key now; it will not be shown again.",
    }


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int, ctx: AuthContext = Depends(require(jwt_only=True)),
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    key = await _owned_key(db, ctx.org.id, key_id)
    key.is_active = False
    await db.commit()
    await redis.delete(key_cache_name(key.key_hash))  # takes effect immediately
    return {"revoked": True, "id": key.id}


@ping_router.get("/ping")
async def ping(
    request: Request,
    ctx: AuthContext = Depends(require("enrich:read", billable=True)),
    db: AsyncSession = Depends(get_db),
):
    remaining = await charge(db, ctx, request, 1)
    return {"pong": True, "via": ctx.via, "organization_id": ctx.org.id, "credits_remaining": remaining}
