import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .credits import spend_credits
from .db import get_db
from .errors import InsufficientCredits
from .models import APIKey, Organization, User
from .ratelimit import sliding_window
from .redis_client import redis_dep

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALLOWED_SCOPES = ("enrich:read", "bulk:write")
KEY_CACHE_TTL = 300


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_key(env: str = "live") -> str:
    # token_urlsafe(24) -> 32 URL-safe chars
    return f"sk_{env}_{secrets.token_urlsafe(24)}"


def key_cache_name(key_hash: str) -> str:
    return f"apikey:{key_hash}"


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret_key,
        algorithm="HS256",
    )


@dataclass
class AuthContext:
    org: Organization
    via: str  # "jwt" | "api_key"
    scopes: set = field(default_factory=set)
    user: User | None = None
    api_key_id: int | None = None
    sandbox: bool = False

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes


def _unauthorized(msg: str = "Invalid or missing authentication") -> HTTPException:
    return HTTPException(401, msg)


def _is_expired(expires_at: datetime | str | None) -> bool:
    if not expires_at:
        return False
    dt = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= datetime.now(timezone.utc)


async def _auth_api_key(raw: str, db: AsyncSession, redis: Redis) -> AuthContext:
    h = hash_key(raw)
    cached = await redis.get(key_cache_name(h))
    if cached:
        rec = json.loads(cached)
        if _is_expired(rec.get("expires_at")):
            await redis.delete(key_cache_name(h))
            raise _unauthorized("API key expired")
    else:
        key = (await db.execute(select(APIKey).where(APIKey.key_hash == h))).scalar_one_or_none()
        if key is None or not key.is_active:
            raise _unauthorized("Invalid API key")
        if _is_expired(key.expires_at):
            raise _unauthorized("API key expired")
        rec = {
            "id": key.id, "org_id": key.org_id, "scopes": key.scopes or [],
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        }
        await redis.setex(key_cache_name(h), KEY_CACHE_TTL, json.dumps(rec))
    org = await db.get(Organization, rec["org_id"])
    if org is None:
        raise _unauthorized("Invalid API key")
    return AuthContext(
        org=org, via="api_key", scopes=set(rec["scopes"]), api_key_id=rec["id"],
        sandbox=raw.startswith("sk_test_"),
    )


async def _auth_jwt(token: str, db: AsyncSession) -> AuthContext:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user = await db.get(User, int(payload["sub"]))
    except (JWTError, KeyError, ValueError, TypeError):
        raise _unauthorized("Invalid or expired token")
    if user is None or not user.is_active:
        raise _unauthorized("Invalid or expired token")
    org = await db.get(Organization, user.org_id)
    if org is None:
        raise _unauthorized()
    return AuthContext(org=org, via="jwt", scopes={"*"}, user=user)


def require(scope: str | None = None, *, billable: bool = False, jwt_only: bool = False):
    """Dual-auth dependency: dashboard JWT (Authorization: Bearer <jwt>) OR API key
    (X-API-Key / Authorization: Bearer sk_...). Applies scope check, per-org sliding-window
    rate limit and (for billable endpoints) a positive-credit check."""

    async def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
        db: AsyncSession = Depends(get_db),
        redis: Redis = Depends(redis_dep),
    ) -> AuthContext:
        bearer = authorization[7:].strip() if authorization and authorization[:7].lower() == "bearer " else None
        raw_key = x_api_key or (bearer if bearer and bearer.startswith("sk_") else None)
        if raw_key:
            ctx = await _auth_api_key(raw_key, db, redis)
        elif bearer:
            ctx = await _auth_jwt(bearer, db)
        else:
            raise _unauthorized()

        # From here on the request is attributable to an org: record it for usage logging.
        request.scope["starkeven_usage"] = {
            "org_id": ctx.org.id, "api_key_id": ctx.api_key_id, "credits": 0,
        }
        if jwt_only and ctx.via != "jwt":
            raise HTTPException(403, "This endpoint requires a dashboard login (JWT)")
        if scope and not ctx.has_scope(scope):
            raise HTTPException(403, f"API key is missing required scope '{scope}'")
        allowed, retry = await sliding_window(redis, f"rl:{ctx.org.id}", max(ctx.org.rate_limit_per_min, 1))
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(retry)})
        if billable and not ctx.sandbox and ctx.org.credit_balance <= 0:
            raise InsufficientCredits()
        return ctx

    return dependency


async def charge(db: AsyncSession, ctx: AuthContext, request: Request, amount: int = 1) -> int:
    """Deduct credits for this request (no-op for sandbox keys). Returns the new balance."""
    if ctx.sandbox or amount <= 0:
        return ctx.org.credit_balance
    balance = await spend_credits(db, ctx.org.id, amount)
    usage = request.scope.get("starkeven_usage")
    if usage is not None:
        usage["credits"] += amount
    return balance


get_current_org = require()
