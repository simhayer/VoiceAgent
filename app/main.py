import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.config import settings
from app.database import async_session, engine
from app.routers import admin, auth, calls, dashboard_ws, super_admin
from app.services import active_calls, tenant_runtime
from app.services import cache as ref_cache
from app.services.pubsub import init_redis, close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _watch_tenant_runtime_updates(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with async_session() as db:
                changed_tenant_ids = await tenant_runtime.refresh_all(db)
            for tenant_id in changed_tenant_ids:
                await active_calls.propagate_tenant_config(
                    tenant_id,
                    tenant_runtime.get_tenant_config(tenant_id),
                )
        except Exception:
            logger.exception("Tenant runtime refresh loop failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.tenant_runtime_refresh_interval_s,
            )
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Receptionist (multi-tenant)")
    stop_event = asyncio.Event()
    tenant_runtime_task: asyncio.Task | None = None

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("DB connection pool pre-warmed")

    async with async_session() as db:
        await ref_cache.warm_all(db)
        await tenant_runtime.warm_all(db)

    await init_redis(settings.redis_url)
    tenant_runtime_task = asyncio.create_task(_watch_tenant_runtime_updates(stop_event))
    yield
    stop_event.set()
    if tenant_runtime_task:
        await tenant_runtime_task
    await close_redis()
    logger.info("Shutting down")


app = FastAPI(
    title="AI Receptionist - Multi-Tenant",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calls.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(super_admin.router)
app.include_router(dashboard_ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}
