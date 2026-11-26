import asyncio
import logging

from sqlalchemy import or_, update

from . import db as dbmod
from .models import APIKey, UsageLog, utcnow
from datetime import timedelta

log = logging.getLogger("starkeven.usage")
_tasks: set = set()


async def _write(org_id, api_key_id, endpoint, status, credits, latency_ms):
    try:
        async with dbmod.SessionLocal() as s:
            s.add(UsageLog(
                org_id=org_id, api_key_id=api_key_id, endpoint=endpoint[:200],
                status_code=status, credits_used=credits, latency_ms=latency_ms,
            ))
            if api_key_id:
                cutoff = utcnow() - timedelta(seconds=60)
                await s.execute(
                    update(APIKey)
                    .where(APIKey.id == api_key_id, or_(APIKey.last_used_at.is_(None), APIKey.last_used_at < cutoff))
                    .values(last_used_at=utcnow())
                )
            await s.commit()
    except Exception:  # never let logging break a request
        log.exception("failed to write usage log")


def schedule(org_id, api_key_id, endpoint, status, credits, latency_ms) -> None:
    task = asyncio.create_task(_write(org_id, api_key_id, endpoint, status, credits, latency_ms))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """Wait for in-flight usage writes (used by tests and graceful shutdown)."""
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
