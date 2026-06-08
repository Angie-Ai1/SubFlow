from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.webhook.router import router as webhook_router
from database.session import check_connection, get_db
from utils.logger_config import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "SubFlow starting up | env=%s host=%s port=%s",
        settings.app_env,
        settings.app_host,
        settings.app_port,
    )
    if check_connection():
        logger.info("Database connection OK")
    else:
        logger.warning("Database unreachable — some features will be unavailable")
    yield
    logger.info("SubFlow shutting down")


app = FastAPI(
    title="SubFlow",
    description="Subscription management automation — Gmail receipts, LINE Bot notifications, Streamlit dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.post("/ops/gmail-import", tags=["ops"])
async def gmail_import(db: Session = Depends(get_db)) -> dict:
    """Manually trigger a Gmail receipt import run."""
    from app.parsers.importer import run_gmail_import
    result = run_gmail_import(db)
    return {
        "total_fetched": result.total_fetched,
        "parsed": result.parsed,
        "inserted": result.inserted,
        "skipped_duplicate": result.skipped_duplicate,
        "skipped_no_amount": result.skipped_no_amount,
    }
