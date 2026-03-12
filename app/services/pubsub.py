"""Redis Pub/Sub helper for broadcasting dashboard events."""

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis

logger = logging.getLogger(__name__)

CHANNEL = "dashboard_events"

_redis_pool: redis.Redis | None = None


async def init_redis(url: str = "redis://localhost:6379") -> None:
    """Initialise the shared Redis connection pool."""
    global _redis_pool
    _redis_pool = redis.from_url(url, decode_responses=True)
    try:
        await _redis_pool.ping()
        logger.info("Redis connected at %s", url)
    except Exception:
        logger.warning("Redis not reachable at %s — dashboard events will be skipped", url)
        _redis_pool = None


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


def _pool() -> redis.Redis | None:
    return _redis_pool


async def publish_event(event_type: str, call_sid: str, **payload) -> None:
    """Publish an event to the dashboard channel.

    Silently no-ops if Redis is unavailable so the voice pipeline is never blocked.
    """
    pool = _pool()
    if pool is None:
        return
    message = {
        "type": event_type,
        "call_sid": call_sid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    try:
        await pool.publish(CHANNEL, json.dumps(message))
    except Exception:
        logger.exception("Failed to publish event %s", event_type)


async def subscribe():
    """Return an async Redis PubSub subscription on the dashboard channel."""
    pool = _pool()
    if pool is None:
        return None
    ps = pool.pubsub()
    await ps.subscribe(CHANNEL)
    return ps
