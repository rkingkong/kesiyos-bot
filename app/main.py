"""
Kesiyos Bot — FastAPI Application Entry Point

Handles startup/shutdown lifecycle, logging, and health checks.
Run with: uvicorn app.main:app --host 0.0.0.0 --port 8444
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.engine import check_db_health, engine


def setup_logging() -> None:
    """Configure structured logging to stdout and file."""
    log_dir = Path(settings.app_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "kesiyos-bot.log"),
    ]

    logging.basicConfig(
        level=getattr(logging, settings.app_log_level.upper(), logging.INFO),
        format=log_format,
        handlers=handlers,
    )

    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.app_env == "development" else logging.WARNING
    )


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    setup_logging()
    logger.info("Kesiyos Bot starting up (env=%s, port=%s)", settings.app_env, settings.app_port)

    # Verify knowledge base exists
    kb_path = settings.knowledge_base_path
    if kb_path.exists():
        logger.info("Knowledge base loaded: %s (%d bytes)", kb_path, kb_path.stat().st_size)
    else:
        logger.warning("Knowledge base NOT FOUND at %s — bot will not be able to answer questions", kb_path)

    # Verify database connectivity
    db_ok = await check_db_health()
    if db_ok:
        logger.info("Database connection verified: %s@%s/%s", settings.db_user, settings.db_host, settings.db_name)
    else:
        logger.error("Database connection FAILED — check credentials and ensure DB exists")

    yield

    # Shutdown
    logger.info("Kesiyos Bot shutting down")
    await engine.dispose()


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kesiyos Bot",
    description="WhatsApp/Messenger/Instagram agent for Kesiyos restaurant",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint for Nginx and monitoring."""
    db_ok = await check_db_health()
    kb_exists = settings.knowledge_base_path.exists()

    status = "healthy" if (db_ok and kb_exists) else "degraded"
    return JSONResponse(
        status_code=200 if status == "healthy" else 503,
        content={
            "status": status,
            "database": "connected" if db_ok else "disconnected",
            "knowledge_base": "loaded" if kb_exists else "missing",
            "environment": settings.app_env,
        },
    )


# ---------------------------------------------------------------------------
# Register routers (will be added as we build each module)
# ---------------------------------------------------------------------------

from app.webhooks import router as webhook_router
app.include_router(webhook_router)
