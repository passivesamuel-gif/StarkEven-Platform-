"""Hybrid Direct-MX + Free SMTP Relay transactional OTP mailer."""
import hashlib
import hmac
import html
import logging
import secrets
from email.message import EmailMessage

import aiosmtplib
from redis.asyncio import Redis

from ..config import settings
from ..netguard import UnsafeTarget, Unresolvable, assert_public_host
from . import dnsutil

logger = logging.getLogger("starkeven.otp_mailer")

OTP_TTL_SECONDS = 600
OTP_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
VALID_PURPOSES = ("signup", "password_reset", "login")

_CLAIM_VALID_OTP_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""

_INCREMENT_ATTEMPTS_LUA = """
local v = redis.call('GET', KEYS[1])
if not v then return -1 end
local h, a = string.match(v, '^([^:]+):(%d+)$')
if not h then return -1 end
local n = tonumber(a)
if n >= tonumber(ARGV[1]) then return n + 1 end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return -1 end
redis.call('SET', KEYS[1], h .. ':' .. tostring(n + 1), 'PX', ttl)
return n + 1
"""


class OtpCooldownError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, int(retry_after))
        super().__init__(f"Please wait {self.retry_after}s before requesting another verification code.")


class OtpLockedError(Exception):
    pass


class OtpInvalidError(Exception):
    pass


class OtpDeliveryError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def otp_redis_key(purpose: str, email: str) -> str:
    return f"starkeven:otp:{purpose}:{normalize_email(email)}"


def cooldown_redis_key(email: str) -> str:
    return f"starkeven:otp:cooldown:{normalize_email(email)}"


def generate_otp_code() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def hash_otp(email: str, purpose: str, code: str) -> str:
    material = f"{settings.jwt_secret_key}:{purpose}:{normalize_email(email)}:{code}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def render_otp_email(
    code: str,
    purpose: str,
    brand_name: str = "StarkEven",
    expires_minutes: int = 10,
) -> tuple[str, str, str]:
    safe_brand = html.escape((brand_name or "StarkEven").strip())
    plain_brand = (brand_name or "StarkEven").strip()
    safe_code = html.escape(code)

    if purpose == "signup":
        subject = f"Verify your {plain_brand} account"
        headline = "Confirm your email address"
        intro = f"Enter this verification code to activate your {safe_brand} account and unlock your starter credits."
        plain_intro = f"Enter this verification code to activate your {plain_brand} account."
    elif purpose == "password_reset":
        subject = f"Reset your {plain_brand} password"
        headline = "Reset your password"
        intro = f"Use the verification code below to reset your {safe_brand} password."
        plain_intro = f"Use this verification code to reset your {plain_brand} password."
    else:
        subject = f"Your {plain_brand} verification code"
        headline = "Your one-time verification code"
        intro = f"Enter the verification code below to continue signing in to {safe_brand}."
        plain_intro = f"Enter this one-time verification code to continue signing in to {plain_brand}."

    spaced_code = " ".join(safe_code)
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#F5F5F7;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1D1D1F;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#F5F5F7;padding:40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:480px;background-color:#FFFFFF;border-radius:20px;border:1px solid rgba(0,0,0,0.08);padding:36px 32px;box-shadow:0 2px 12px rgba(0,0,0,0.04);">
          <tr>
            <td style="padding-bottom:20px;">
              <span style="display:inline-block;font-size:15px;font-weight:600;letter-spacing:-0.02em;color:#1D1D1F;">{safe_brand}</span>
            </td>
          </tr>
          <tr>
            <td style="padding-bottom:10px;">
              <h1 style="margin:0;font-size:24px;line-height:1.25;font-weight:600;letter-spacing:-0.025em;color:#1D1D1F;">{headline}</h1>
            </td>
          </tr>
          <tr>
            <td style="padding-bottom:24px;">
              <p style="margin:0;font-size:15px;line-height:1.55;color:#6E6E73;">{intro}</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:20px 16px;background-color:#F5F5F7;border-radius:14px;border:1px solid rgba(0,0,0,0.06);">
              <span style="font-family:'SF Mono',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:32px;font-weight:700;letter-spacing:0.22em;color:#0071E3;font-variant-numeric:tabular-nums;">{spaced_code}</span>
            </td>
          </tr>
          <tr>
            <td style="padding-top:22px;">
              <p style="margin:0;font-size:13px;line-height:1.5;color:#6E6E73;">
                This code expires in <strong style="color:#1D1D1F;">{expires_minutes} minutes</strong> and can only be used once. If you did not request this code, you can safely ignore this message.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    text_body = (
        f"{plain_brand} - {headline}\n\n"
        f"{plain_intro}\n\n"
        f"Verification code: {code}\n\n"
        f"This code expires in {expires_minutes} minutes and can only be used once.\n"
        f"If you did not request this code, you can safely ignore this message.\n"
    )
    return subject, html_body, text_body


async def send_email_message(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> dict[str, str]:
    target_email = normalize_email(to_email)
    sender = (settings.smtp_from or settings.smtp_user or f"noreply@{settings.smtp_helo_domain}").strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = target_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    smtp_host = (settings.smtp_host or "").strip()
    if smtp_host:
        port = int(settings.smtp_port or 587)
        use_tls = port == 465
        start_tls = port != 465 and not (port == 25 and not (settings.smtp_user or "").strip())
        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=port,
                username=(settings.smtp_user or "").strip() or None,
                password=(settings.smtp_pass or "").strip() or None,
                use_tls=use_tls,
                start_tls=start_tls,
                timeout=10.0,
            )
            return {"delivery_mode": "smtp_relay", "host": smtp_host}
        except (OSError, TimeoutError, aiosmtplib.SMTPException) as exc:
            if settings.environment == "production":
                raise OtpDeliveryError(f"SMTP relay delivery failed: {exc}") from exc
            logger.info("SMTP relay unavailable in %s (%s); falling back to dev_console", settings.environment, exc)
            return {"delivery_mode": "dev_console"}

    # Mode B: Direct MX delivery over port 25
    domain = target_email.rsplit("@", 1)[-1]
    mx_records = await dnsutil.query(domain, "MX")
    mx_hosts = dnsutil.parse_mx(mx_records)

    last_err: Exception | None = None
    for mx_host in mx_hosts[:3]:
        try:
            await assert_public_host(mx_host)
            await aiosmtplib.send(
                msg,
                hostname=mx_host,
                port=25,
                timeout=5.0,
                local_hostname=settings.smtp_helo_domain,
            )
            return {"delivery_mode": "direct_mx", "host": mx_host}
        except (UnsafeTarget, Unresolvable, OSError, TimeoutError, aiosmtplib.SMTPException) as exc:
            last_err = exc
            continue

    if settings.environment != "production":
        logger.info("Direct MX delivery skipped/unavailable in %s (%s); using dev_console", settings.environment, last_err)
        return {"delivery_mode": "dev_console"}

    raise OtpDeliveryError("Unable to deliver email to recipient MX server")


async def send_otp(
    redis: Redis,
    email: str,
    purpose: str = "login",
    brand_name: str = "StarkEven",
) -> dict[str, object]:
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"Unsupported OTP purpose: {purpose}")
    norm_email = normalize_email(email)

    cooldown_key = cooldown_redis_key(norm_email)
    if not await redis.set(cooldown_key, "1", nx=True, ex=OTP_COOLDOWN_SECONDS):
        ttl = await redis.ttl(cooldown_key)
        raise OtpCooldownError(ttl if ttl and ttl > 0 else OTP_COOLDOWN_SECONDS)

    code = generate_otp_code()
    otp_hash = hash_otp(norm_email, purpose, code)
    key = otp_redis_key(purpose, norm_email)
    await redis.set(key, f"{otp_hash}:0", ex=OTP_TTL_SECONDS)

    subject, html_body, text_body = render_otp_email(code, purpose, brand_name=brand_name)
    try:
        delivery = await send_email_message(norm_email, subject, html_body, text_body)
    except OtpDeliveryError:
        await redis.delete(key, cooldown_key)
        raise

    mode = delivery.get("delivery_mode", "unknown")
    if mode == "dev_console" and settings.environment != "production":
        print(f"[StarkEven OTP Dev Console] purpose={purpose} to={norm_email} code={code}", flush=True)

    return {
        "status": "sent",
        "expires_in": OTP_TTL_SECONDS,
        "delivery_mode": mode,
    }


async def verify_otp(redis: Redis, email: str, purpose: str, code: str) -> bool:
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"Unsupported OTP purpose: {purpose}")
    norm_email = normalize_email(email)
    key = otp_redis_key(purpose, norm_email)

    raw = await redis.get(key)
    if not raw or ":" not in raw:
        raise OtpInvalidError("Invalid or expired verification code")

    stored_hash, _, attempts_str = raw.rpartition(":")
    try:
        attempts = int(attempts_str)
    except ValueError:
        raise OtpInvalidError("Invalid or expired verification code")

    if attempts >= OTP_MAX_ATTEMPTS:
        raise OtpLockedError("Too many failed verification attempts. Please request a new code.")

    expected_hash = hash_otp(norm_email, purpose, code.strip())
    if hmac.compare_digest(stored_hash, expected_hash):
        claimed = await redis.eval(_CLAIM_VALID_OTP_LUA, 1, key, raw)
        if not claimed:
            raise OtpInvalidError("Invalid or expired verification code")
        return True

    new_attempts = int(await redis.eval(_INCREMENT_ATTEMPTS_LUA, 1, key, OTP_MAX_ATTEMPTS))
    if new_attempts < 0:
        raise OtpInvalidError("Invalid or expired verification code")
    if new_attempts > OTP_MAX_ATTEMPTS:
        raise OtpLockedError("Too many failed verification attempts. Please request a new code.")
    raise OtpInvalidError("Invalid or expired verification code")
