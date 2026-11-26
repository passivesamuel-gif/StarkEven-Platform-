import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..config import PLAN_LIMITS, TRIAL_CREDITS
from ..db import get_db
from ..engine.otp_mailer import (
    OtpCooldownError,
    OtpDeliveryError,
    OtpInvalidError,
    OtpLockedError,
    cooldown_redis_key,
    send_otp,
    verify_otp,
)
from ..models import Organization, User
from ..ratelimit import fixed_window
from ..redis_client import redis_dep
from ..security import create_token, pwd
from ..utils import client_ip

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_DUMMY_HASH = pwd.hash("starkeven-dummy-password")  # constant-time-ish login for unknown emails
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_S = 900


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL.match(v):
        raise ValueError("Enter a valid email address")
    return v


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(default="My Organization", min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class ConfirmSignupIn(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class ForgotPasswordIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class ResetPasswordIn(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


@router.post("/register", status_code=201)
async def register(
    payload: RegisterIn, request: Request,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    allowed, retry = await fixed_window(redis, f"register:{client_ip(request)}", 10, 3600)
    if not allowed:
        raise HTTPException(429, "Too many sign-ups from this address", headers={"Retry-After": str(retry)})
    if (await db.execute(select(User.id).where(User.email == payload.email))).first():
        raise HTTPException(409, "Email already registered")
    hashed = await run_in_threadpool(pwd.hash, payload.password)
    org = Organization(
        name=payload.organization_name.strip(), plan_tier="starter",
        credit_balance=0, rate_limit_per_min=PLAN_LIMITS["starter"],
    )
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email=payload.email, hashed_password=hashed, role="owner", is_verified=False)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already registered")

    try:
        otp_res = await send_otp(redis, payload.email, purpose="signup", brand_name="StarkEven")
    except OtpCooldownError as exc:
        await db.rollback()
        raise HTTPException(429, str(exc), headers={"Retry-After": str(exc.retry_after)})
    except OtpDeliveryError as exc:
        await db.rollback()
        raise HTTPException(503, str(exc))

    try:
        await db.commit()  # org + user in one transaction
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already registered")

    return {
        "status": "verification_required",
        "message": "Verification code sent to your email.",
        "organization_id": org.id,
        "credits": org.credit_balance,
        "is_verified": False,
        "expires_in": otp_res["expires_in"],
    }


@router.post("/confirm-signup")
async def confirm_signup(
    payload: ConfirmSignupIn,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    try:
        await verify_otp(redis, payload.email, "signup", payload.code)
    except OtpLockedError as exc:
        raise HTTPException(429, str(exc))
    except OtpInvalidError as exc:
        raise HTTPException(400, str(exc))

    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(400, "Invalid or expired verification code")

    flipped = (
        await db.execute(
            update(User)
            .where(User.id == user.id, User.is_verified.is_(False))
            .values(is_verified=True)
            .returning(User.id)
        )
    ).scalar_one_or_none()
    if flipped is not None:
        await db.execute(
            update(Organization)
            .where(Organization.id == user.org_id)
            .values(credit_balance=Organization.credit_balance + TRIAL_CREDITS)
        )
    await db.commit()
    await redis.delete(cooldown_redis_key(payload.email))
    org = await db.get(Organization, user.org_id)
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "organization_id": user.org_id,
        "credits": org.credit_balance if org else TRIAL_CREDITS,
        "is_verified": True,
    }


@router.post("/resend-signup-otp")
async def resend_signup_otp(
    payload: ForgotPasswordIn,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is not None and user.is_active and not user.is_verified:
        try:
            await send_otp(redis, payload.email, purpose="signup", brand_name="StarkEven")
        except OtpCooldownError as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": str(exc.retry_after)})
        except OtpDeliveryError as exc:
            raise HTTPException(503, str(exc))
    return {"status": "ok", "message": "If an account is awaiting verification, a new code has been sent."}


@router.post("/login")
async def login(
    payload: LoginIn, request: Request,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    fail_key = f"loginfail:{client_ip(request)}:{payload.email}"
    if int(await redis.get(fail_key) or 0) >= LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many failed attempts. Try again later.",
                            headers={"Retry-After": str(LOGIN_WINDOW_S)})
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    hashed = user.hashed_password if user else _DUMMY_HASH
    ok = await run_in_threadpool(pwd.verify, payload.password, hashed)
    if not (user and ok and user.is_active):
        await fixed_window(redis, fail_key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S)
        raise HTTPException(401, "Invalid email or password")
    if not user.is_verified:
        raise HTTPException(403, "Account email is not verified. Please confirm your signup verification code.")
    await redis.delete(fail_key)
    return {"access_token": create_token(user), "token_type": "bearer", "organization_id": user.org_id}


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordIn,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is not None and user.is_active and user.is_verified:
        try:
            await send_otp(redis, payload.email, purpose="password_reset", brand_name="StarkEven")
        except (OtpCooldownError, OtpDeliveryError):
            pass
    return {"status": "ok", "message": "If an account exists for that email, a reset code has been sent."}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordIn,
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(redis_dep),
):
    try:
        await verify_otp(redis, payload.email, "password_reset", payload.code)
    except OtpLockedError as exc:
        raise HTTPException(429, str(exc))
    except OtpInvalidError as exc:
        raise HTTPException(400, str(exc))

    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not user.is_active or not user.is_verified:
        raise HTTPException(400, "Invalid or expired verification code")

    user.hashed_password = await run_in_threadpool(pwd.hash, payload.new_password)
    await db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "organization_id": user.org_id}
