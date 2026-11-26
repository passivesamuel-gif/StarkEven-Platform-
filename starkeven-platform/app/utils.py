from fastapi import Request


def client_ip(request: Request) -> str:
    """Caddy overwrites X-Forwarded-For with the real client address; the API port is only
    published on 127.0.0.1, so the first entry is trustworthy in the supplied deployment."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
