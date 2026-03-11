import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sqlalchemy import text

from app.config import settings
from app.database import async_session, engine, init_db
from app.routers import admin, calls
from app.services import cache as ref_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s AI Receptionist", settings.office_name)
    await init_db()

    # Pre-warm the connection pool so the first call doesn't pay cold-start cost
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("DB connection pool pre-warmed")

    async with async_session() as db:
        await ref_cache.warm(db)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=f"{settings.office_name} - AI Receptionist",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(calls.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "office": settings.office_name, "version": "0.2.0"}
