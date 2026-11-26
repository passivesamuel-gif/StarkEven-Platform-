from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES = {
    400: "bad_request", 401: "unauthorized", 402: "payment_required", 403: "forbidden",
    404: "not_found", 405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
    422: "validation_error", 429: "rate_limited", 503: "service_unavailable",
}


class InsufficientCredits(Exception):
    pass


class DomainNotFound(Exception):
    pass


def error_body(code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, **extra}}


def install_handlers(app: FastAPI) -> None:
    from .netguard import UnsafeTarget

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        code = CODES.get(exc.status_code, f"http_{exc.status_code}")
        return JSONResponse(
            error_body(code, str(exc.detail)), status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        details = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        msg = f"{details[0]['loc']}: {details[0]['msg']}" if details else "Invalid request"
        return JSONResponse(error_body("validation_error", msg, details=details), status_code=422)

    @app.exception_handler(InsufficientCredits)
    async def credits_exc(request: Request, exc: InsufficientCredits):
        return JSONResponse(error_body("payment_required", "Insufficient credits"), status_code=402)

    @app.exception_handler(UnsafeTarget)
    async def unsafe_exc(request: Request, exc: UnsafeTarget):
        return JSONResponse(
            error_body("unsafe_target", "Target resolves to a non-public address and was refused"),
            status_code=422,
        )

    @app.exception_handler(DomainNotFound)
    async def notfound_exc(request: Request, exc: DomainNotFound):
        return JSONResponse(
            error_body("domain_not_found", "Domain has no DNS records (no charge applied)"),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        return JSONResponse(error_body("internal_error", "Internal server error"), status_code=500)
