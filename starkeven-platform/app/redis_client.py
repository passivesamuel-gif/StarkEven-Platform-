from redis.asyncio import Redis

from .config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def redis_dep() -> Redis:
    """FastAPI dependency."""
    return get_redis()


def reset() -> None:
    global _client
    _client = None


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
