"""
Database connection, engine configuration, and async session management.
Supports SQLite (aiosqlite) and PostgreSQL (asyncpg).
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.common.config import settings
from src.common.logging import logger
from src.database.models import Base

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables idempotently."""
    async with engine.begin() as conn:
        logger.info(f"Initializing database schema using URL: {settings.database_url}")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized successfully.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
