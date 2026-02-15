"""
Database connection and session management
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine
)
from sqlalchemy.pool import NullPool
from config.settings import settings
from src.bot.database.models import Base

from sqlalchemy import text as _sql_text


async def ensure_schema(conn):
    """Lightweight migrations for SQLite (adds missing tables/columns used by web panel/subscriptions)."""
    # 1) Add company_number to users if missing
    cols_res = await conn.execute(_sql_text("PRAGMA table_info(users)"))
    existing = {row[1] for row in cols_res.fetchall()}
    if "company_number" not in existing:
        await conn.execute(_sql_text("ALTER TABLE users ADD COLUMN company_number VARCHAR(30)"))

    # 2) Admins table for web panel
    await conn.execute(_sql_text(
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))

    # 3) User subscriptions table
    await conn.execute(_sql_text(
        """
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            payment_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    ))

    # 4) Payments table
    await conn.execute(_sql_text(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT DEFAULT 'UAH',
            status TEXT DEFAULT 'pending',
            provider TEXT DEFAULT 'manual',
            provider_payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    ))


# Create async engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # Use NullPool for SQLite
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database - create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_schema(conn)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
