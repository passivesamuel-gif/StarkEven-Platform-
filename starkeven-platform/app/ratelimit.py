import uuid

from redis.asyncio import Redis

# Atomic sliding window over a sorted set (score = Redis server time in ms).
_SLIDING = """
local key=KEYS[1]
local t=redis.call('TIME')
local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000)
local window=tonumber(ARGV[1])
local limit=tonumber(ARGV[2])
local member=now..'-'..ARGV[3]
redis.call('ZREMRANGEBYSCORE',key,0,now-window)
local count=redis.call('ZCARD',key)
if count>=limit then
  local oldest=redis.call('ZRANGE',key,0,0,'WITHSCORES')
  local retry=math.ceil((tonumber(oldest[2])+window-now)/1000)
  if retry<1 then retry=1 end
  return {0,retry}
end
redis.call('ZADD',key,now,member)
redis.call('PEXPIRE',key,window)
return {1,0}
"""


async def sliding_window(redis: Redis, key: str, limit: int, window_ms: int = 60_000) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    res = await redis.eval(_SLIDING, 1, key, window_ms, limit, uuid.uuid4().hex[:8])
    return bool(int(res[0])), int(res[1])


async def fixed_window(redis: Redis, key: str, limit: int, window_s: int) -> tuple[bool, int]:
    """Cheap counter limiter for logins / signups / demo. Returns (allowed, retry_after_seconds)."""
    count = await redis.incr(key)
    ttl = await redis.ttl(key)
    if count == 1 or ttl < 0:
        await redis.expire(key, window_s)
        ttl = window_s
    return count <= limit, max(int(ttl), 1)
