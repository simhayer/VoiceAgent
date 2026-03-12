import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.config import settings
from app.database import async_session, engine
from app.routers import admin, auth, calls, dashboard_ws, super_admin
from app.services import cache as ref_cache
from app.services.pubsub import init_redis, close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Receptionist (multi-tenant)")

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("DB connection pool pre-warmed")

    async with async_session() as db:
        await ref_cache.warm_all(db)

    await init_redis(settings.redis_url)
    yield
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
