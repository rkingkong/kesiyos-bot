"""
Kesiyos Bot — Database Engine

Async SQLAlchemy engine and session management.
Uses asyncpg for production-grade async PostgreSQL access.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Async engine — connection pool managed by SQLAlchemy
engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),  # SQL logging only in dev
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,  # Verify connections before use
)

# Session factory — use this to create sessions in request handlers
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """FastAPI dependency — yields a database session per request."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    """Health check — can we reach the database?"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# Import text for health check
from sqlalchemy import text
