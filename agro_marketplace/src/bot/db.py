from __future__ import annotations

import aiosqlite
from datetime import datetime
from typing import Optional, Dict, Any

import os
from pathlib import Path

from config.settings import DB_FILE as SETTINGS_DB_FILE

def _resolve_db_path() -> str:
    """Повертає абсолютний шлях до SQLite ..."""
    raw = os.getenv("DB_FILE", SETTINGS_DB_FILE)
    if os.path.isabs(raw):
        return raw
    # проєктний корінь = .../agro_marketplace
    root = Path(__file__).resolve().parents[2]
    return str((root / raw).resolve())


DB_FILE = _resolve_db_path()


async def ensure_subscription_columns() -> None:
    """
    Додає колонки підписки в існуючу таблицю users, якщо їх ще немає.
    Безпечно: не видаляє дані, просто ALTER TABLE якщо потрібно.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("PRAGMA table_info(users)")
        cols = [row[1] for row in await cur.fetchall()]

        if "subscription_plan" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN subscription_plan TEXT DEFAULT 'free'")
        if "subscription_until" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN subscription_until TEXT")

        await db.commit()


async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Повертає юзера словником (або None) з полями підписки."""
    await ensure_subscription_columns()

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                telegram_id, role, region, company_number, company, is_banned, created_at,
                COALESCE(subscription_plan, 'free') AS subscription_plan,
                subscription_until
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def activate_pro(telegram_id: int, until: datetime) -> None:
    """Активує PRO до дати until (UTC)."""
    await ensure_subscription_columns()

    until_iso = until.replace(microsecond=0).isoformat()

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            UPDATE users
            SET subscription_plan='pro',
                subscription_until=?
            WHERE telegram_id=?
            """,
            (until_iso, telegram_id),
        )
        await db.commit()


async def is_pro_user(telegram_id: int) -> bool:
    """True якщо користувач має plan=pro і subscription_until > now(UTC)."""
    u = await get_user(telegram_id)
    if not u:
        return False

    if (u.get("subscription_plan") or "free") != "pro":
        return False

    until = u.get("subscription_until")
    if not until:
        return False

    try:
        dt_until = datetime.fromisoformat(until)
    except Exception:
        return False

    return dt_until > datetime.utcnow()


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS counter_offers (
                                                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                       lot_id INTEGER NOT NULL,
                                                                       sender_user_id INTEGER NOT NULL,
                                                                       offered_price REAL NOT NULL,
                                                                       message TEXT,
                                                                       status TEXT NOT NULL DEFAULT 'pending',
                                                                       created_at TEXT DEFAULT (datetime('now'))
                             )
                         """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_lot ON counter_offers(lot_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_sender ON counter_offers(sender_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_status ON counter_offers(status)")
        await db.commit()
