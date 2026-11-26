import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..engine.otp_mailer import (
    OtpCooldownError,
    OtpDeliveryError,
    OtpInvalidError,
    OtpLockedError,
    send_otp,
    verify_otp,
)
from ..redis_client import redis_dep
from ..security import AuthContext, charge, get_current_org, require

router = APIRouter(prefix="/api/v1/email", tags=["email-otp"])
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL.match(v):
        raise ValueError("Enter a valid email address")
    return v


class SendOtpIn(BaseModel):
    email: str
    purpose: Literal["signup", "password_reset", "login"] = "login"
    brand_name: str = Field(default="StarkEven", min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class VerifyOtpIn(BaseModel):
    email: str
    purpose: Literal["signup", "password_reset", "login"] = "login"
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


@router.post("/send-otp")
async def send_otp_endpoint(
    payload: SendOtpIn,
    request: Request,
    ctx: AuthContext = Depends(require(billable=True)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(redis_dep),
):
    try:
        result = await send_otp(redis, payload.email, purpose=payload.purpose, brand_name=payload.brand_name)
    except OtpCooldownError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": str(exc.retry_after)})
    except OtpDeliveryError as exc:
        raise HTTPException(503, str(exc))

    await charge(db, ctx, request, 1)
    return result


@router.post("/verify-otp")
async def verify_otp_endpoint(
    payload: VerifyOtpIn,
    ctx: AuthContext = Depends(get_current_org),
    redis: Redis = Depends(redis_dep),
):
    try:
        await verify_otp(redis, payload.email, payload.purpose, payload.code)
    except OtpLockedError as exc:
        raise HTTPException(429, str(exc))
    except OtpInvalidError as exc:
        raise HTTPException(400, str(exc))
    return {"verified": True}
