import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import admin, calls
from app.routers import dashboard_ws
from app.services.pubsub import init_redis, close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s AI Receptionist", settings.office_name)
    await init_db()
    await init_redis(settings.redis_url)
    yield
    await close_redis()
    logger.info("Shutting down")


app = FastAPI(
    title=f"{settings.office_name} - AI Receptionist",
    version="0.2.0",
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
app.include_router(dashboard_ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "office": settings.office_name, "version": "0.2.0"}

