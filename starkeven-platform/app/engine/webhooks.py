import asyncio
import hashlib
import hmac
import json
import time

import httpx

from ..config import settings
from ..netguard import request_guard

_transport = None  # tests inject httpx.MockTransport


def sign(timestamp: str, body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def callback_signing_secret(org_id: int) -> str:
    """Per-organization secret for verifying bulk-job callbacks. Derived one-way from
    WEBHOOK_SECRET, so handing it to a customer never lets them forge billing webhooks."""
    return hmac.new(settings.webhook_secret.encode(), f"bulk-callback:{org_id}".encode(), hashlib.sha256).hexdigest()


async def send_signed_webhook(url: str, payload: dict, secret: str, *, event: str, backoff=(1.0, 3.0)) -> bool:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    attempts = len(backoff) + 1
    async with httpx.AsyncClient(
        timeout=10.0, follow_redirects=False, trust_env=False,
        event_hooks={"request": [request_guard]}, transport=_transport,
    ) as client:
        for i in range(attempts):
            ts = str(int(time.time()))
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "StarkEven-Webhook/1.0",
                "X-StarkEven-Event": event,
                "X-StarkEven-Timestamp": ts,
                "X-StarkEven-Signature": sign(ts, body, secret),
            }
            try:
                r = await client.post(url, content=body, headers=headers)
                if 200 <= r.status_code < 300:
                    return True
            except Exception:
                pass
            if i < attempts - 1:
                await asyncio.sleep(backoff[i])
    return False
