import csv
import io
import uuid

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from ..config import settings
from ..db import get_db
from ..engine.enrichment import CSV_FIELDS
from ..models import BulkJob
from ..netguard import assert_public_url, UnsafeTarget
from ..security import AuthContext, require
from ..worker import run_bulk_job

router = APIRouter(prefix="/api/v1/enrich/bulk", tags=["bulk"])
MAX_DOMAINS = 10_000
MAX_UPLOAD = 5 * 1024 * 1024
_arq_pool = None


class BulkJson(BaseModel):
    domains: list[str]
    webhook_url: str | None = None


async def enqueue_bulk(job_id: str) -> bool:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    if not await _arq_pool.exists("arq:queue:health-check"):
        return False
    await _arq_pool.enqueue_job("process_bulk", job_id, _job_id=job_id)
    return True


async def close_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None


def parse_csv(raw: bytes) -> list[str]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    cols = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
    if "domain" not in cols:
        raise HTTPException(400, "CSV must contain a 'domain' column")
    col = cols["domain"]
    return [(row.get(col) or "").strip() for row in reader if (row.get(col) or "").strip()]


def safe_cell(value) -> str:
    """Neutralise spreadsheet formula injection in CSV downloads."""
    s = "" if value is None else str(value)
    return "'" + s if s and s[0] in "=+-@\t\r" else s


@router.post("", status_code=202)
async def create_bulk(
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require("bulk:write", billable=True)),
    db: AsyncSession = Depends(get_db),
):
    if ctx.sandbox:
        raise HTTPException(403, "Sandbox (sk_test_) keys cannot run bulk jobs")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD + 1024 * 1024:
        raise HTTPException(413, "Upload too large (max 5 MB)")

    ctype = request.headers.get("content-type", "")
    webhook_url = None
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(400, "Provide a CSV file in the 'file' field")
        raw = await upload.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Upload too large (max 5 MB)")
        domains = parse_csv(raw)
        wh = form.get("webhook_url")
        webhook_url = wh.strip() or None if isinstance(wh, str) else None
    else:
        try:
            payload = BulkJson.model_validate(await request.json())
        except (ValueError, ValidationError):
            raise HTTPException(422, 'Body must be {"domains": [...], "webhook_url": "..."}')
        domains = [d.strip() for d in payload.domains if isinstance(d, str) and d.strip()]
        webhook_url = (payload.webhook_url or "").strip() or None

    seen, unique = set(), []
    for d in domains:  # de-duplicate, keep order
        k = d.lower()
        if k not in seen:
            seen.add(k)
            unique.append(d)
    if not unique or len(unique) > MAX_DOMAINS:
        raise HTTPException(400, f"Provide between 1 and {MAX_DOMAINS} domains")
    if ctx.org.credit_balance < len(unique):
        raise HTTPException(402, f"Insufficient credits: {len(unique)} domains need up to {len(unique)} credits, "
                                 f"balance is {ctx.org.credit_balance}")
    if webhook_url:
        try:
            await assert_public_url(webhook_url)
        except ValueError as e:
            raise HTTPException(422, f"webhook_url: {e}")
        except UnsafeTarget:
            raise HTTPException(422, "webhook_url resolves to a non-public address")

    job = BulkJob(
        id=uuid.uuid4().hex, org_id=ctx.org.id, status="queued", total_domains=len(unique),
        results_json=[{"domain": d} for d in unique], webhook_url=webhook_url,
    )
    db.add(job)
    await db.commit()
    try:
        enqueued = await enqueue_bulk(job.id)
    except Exception:
        enqueued = False
    if enqueued is False:
        background_tasks.add_task(run_bulk_job, job.id)
    return {"batch_id": job.id, "status": "queued", "total_domains": job.total_domains}


def _parse_batch_id(batch_id: str) -> str:
    try:
        return uuid.UUID(batch_id).hex
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(422, "Invalid batch_id; must be a valid UUID")


async def _owned_job(db: AsyncSession, batch_id: str, org_id: int) -> BulkJob:
    normalized_id = _parse_batch_id(batch_id)
    job = (
        await db.execute(
            select(BulkJob).where(BulkJob.id == normalized_id, BulkJob.org_id == org_id)
        )
    ).scalar_one_or_none()
    if job is None:  # same 404 for "missing" and "someone else's"
        raise HTTPException(404, "Batch not found")
    return job


@router.get("/{batch_id}")
async def bulk_status(
    batch_id: str, ctx: AuthContext = Depends(require("bulk:write")), db: AsyncSession = Depends(get_db),
):
    job = await _owned_job(db, batch_id, ctx.org.id)
    out = {
        "batch_id": job.id, "status": job.status, "total_domains": job.total_domains,
        "processed_domains": job.processed_domains,
        "progress": round(job.processed_domains / job.total_domains, 4) if job.total_domains else 1.0,
        "credits_used": job.credits_used, "created_at": job.created_at,
        "completed_at": job.completed_at, "error": job.error,
    }
    if job.status == "completed":
        out["results"] = job.results_json
    return out


@router.get("/{batch_id}/download")
async def bulk_download(
    batch_id: str, ctx: AuthContext = Depends(require("bulk:write")), db: AsyncSession = Depends(get_db),
):
    job = await _owned_job(db, batch_id, ctx.org.id)
    if job.status != "completed":
        raise HTTPException(409, f"Batch is {job.status}; download is available once completed")
    rows = job.results_json

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_FIELDS)
        yield buf.getvalue()
        for r in rows:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([safe_cell(r.get(f)) for f in CSV_FIELDS])
            yield buf.getvalue()

    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="starkeven-{job.id}.csv"'},
    )
