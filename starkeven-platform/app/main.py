import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import db as dbmod
from . import redis_client, usage
from .config import settings
from .errors import install_handlers
from .routes import admin, auth, autopilot, billing, bulk, enrich, integrations, keys, orgs, otp_api, verify


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_secure()
    yield
    await usage.drain()
    await bulk.close_pool()
    await autopilot.close_pool()
    await redis_client.close()
    await dbmod.engine.dispose()


app = FastAPI(title="StarkEven B2B Lead & Data Intelligence API", version="1.0.0", lifespan=lifespan)
install_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=False,  # bearer tokens / API keys, never cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def usage_logging(request: Request, call_next):
    """Logs every authenticated request (including 401-after-auth, 402, 403, 429) in the background."""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        info = request.scope.get("starkeven_usage")
        if info:
            usage.schedule(
                info["org_id"], info["api_key_id"], f"{request.method} {request.url.path}",
                status, info["credits"], int((time.perf_counter() - start) * 1000),
            )


for r in (
    auth.router, keys.router, keys.ping_router, orgs.router, enrich.router, enrich.demo_router,
    verify.router, bulk.router, autopilot.router, integrations.router, billing.router,
    otp_api.router, admin.router,
):
    app.include_router(r)


@app.get("/health", tags=["meta"])
async def health():
    try:
        async with dbmod.SessionLocal() as s:
            await s.execute(text("SELECT 1"))
        await redis_client.get_redis().ping()
    except Exception:
        return JSONResponse({"status": "unavailable", "service": "starkeven-api"}, status_code=503)
    return {"status": "ok", "service": "starkeven-api"}
