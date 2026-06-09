from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.webhook.router import router as webhook_router
from database.session import SessionLocal, check_connection, get_db
from utils.logger_config import get_logger

logger = get_logger(__name__)


def _check_required_env() -> None:
    """Log errors for missing env vars so failures surface at startup, not runtime."""
    checks = {
        "LINE_CHANNEL_ACCESS_TOKEN": settings.line_channel_access_token,
        "LINE_CHANNEL_SECRET": settings.line_channel_secret,
        "GMAIL_TARGET_ADDRESS": settings.gmail_target_address,
    }
    missing = [k for k, v in checks.items() if not v]
    if missing:
        for key in missing:
            logger.error("未設定必要環境變數: %s — 請參考 docs/SETUP.md", key)
        logger.error(
            "共 %d 個必要變數未設定，部分功能將無法使用。執行 .\\setup.ps1 可互動式建立 .env",
            len(missing),
        )


def _with_db(fn):
    """Wrap a scheduled job so it receives a fresh DB session and closes it on exit."""
    def _job():
        db = SessionLocal()
        try:
            fn(db)
        except Exception as exc:
            logger.error("scheduled job %s failed: %s", fn.__name__, exc)
        finally:
            db.close()
    _job.__name__ = fn.__name__
    return _job


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "SubFlow starting up | env=%s host=%s port=%s",
        settings.app_env,
        settings.app_host,
        settings.app_port,
    )
    _check_required_env()
    if check_connection():
        logger.info("Database connection OK")
    else:
        logger.warning("Database unreachable — some features will be unavailable")

    from app.webhook.notifier import run_daily_billing_check, run_scheduled_gmail_import

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _with_db(run_daily_billing_check),
        trigger=CronTrigger(hour=settings.cron_notification_hour, minute=0),
        id="daily_billing_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _with_db(run_scheduled_gmail_import),
        trigger=IntervalTrigger(hours=6),
        id="gmail_import_interval",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started | billing_check=%02d:00 gmail_import=every6h",
        settings.cron_notification_hour,
    )

    yield

    scheduler.shutdown(wait=False)
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
