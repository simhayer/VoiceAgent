"""Redis Pub/Sub helper for broadcasting dashboard events.

Uses a single shared subscription — one Redis connection for all
dashboard WebSocket clients.  Messages are fanned out in-memory via
an asyncio broadcast mechanism.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

import redis.asyncio as redis

logger = logging.getLogger(__name__)

CHANNEL = "dashboard_events"

_redis_pool: redis.Redis | None = None

# ── Shared broadcast machinery ──
# One background task subscribes to Redis; connected WS clients each get
# their own asyncio.Queue that receives a copy of every message.

_listeners: set[asyncio.Queue[str]] = set()
_listener_lock = asyncio.Lock()
_subscriber_task: asyncio.Task | None = None


async def init_redis(url: str = "redis://localhost:6379") -> None:
    """Initialise the shared Redis connection pool (max 5 connections)."""
    global _redis_pool
    _redis_pool = redis.from_url(
        url,
        decode_responses=True,
        max_connections=5,
    )
    try:
        await _redis_pool.ping()
        logger.info("Redis connected at %s", url)
        # Start the single shared subscriber
        _start_subscriber()
    except Exception:
        logger.warning(
            "Redis not reachable at %s — dashboard events will be skipped", url
        )
        _redis_pool = None


async def close_redis() -> None:
    global _redis_pool, _subscriber_task
    if _subscriber_task and not _subscriber_task.done():
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass
        _subscriber_task = None
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


def _pool() -> redis.Redis | None:
    return _redis_pool


# ── Publishing ──


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


# ── Single shared subscriber ──


def _start_subscriber() -> None:
    """Ensure exactly one background task is reading from Redis pub/sub."""
    global _subscriber_task
    if _subscriber_task and not _subscriber_task.done():
        return  # already running
    _subscriber_task = asyncio.create_task(_subscriber_loop())


async def _subscriber_loop() -> None:
    """Background loop: subscribe to Redis channel and broadcast to all queues."""
    pool = _pool()
    if pool is None:
        return
    ps = pool.pubsub()
    try:
        await ps.subscribe(CHANNEL)
        logger.info("Shared Redis subscriber started on channel %s", CHANNEL)
        async for raw_message in ps.listen():
            if raw_message["type"] != "message":
                continue
            data = raw_message.get("data")
            if not isinstance(data, str):
                continue
            # Fan out to all connected listeners
            async with _listener_lock:
                dead: list[asyncio.Queue] = []
                for q in _listeners:
                    try:
                        q.put_nowait(data)
                    except asyncio.QueueFull:
                        dead.append(q)
                # Drop any queues that are full (slow/dead clients)
                for q in dead:
                    _listeners.discard(q)
    except asyncio.CancelledError:
        logger.info("Shared Redis subscriber stopped")
    except Exception:
        logger.exception("Shared Redis subscriber crashed")
    finally:
        await ps.unsubscribe()
        await ps.aclose()


async def listen() -> AsyncIterator[str]:
    """Yield messages from the shared subscription.

    Each caller gets its own asyncio.Queue — no extra Redis connections.
    """
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
    async with _listener_lock:
        _listeners.add(q)
    try:
        while True:
            msg = await q.get()
            yield msg
    finally:
        async with _listener_lock:
            _listeners.discard(q)
