import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.routers import admin, calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s AI Receptionist", settings.office_name)
    await init_db()
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
