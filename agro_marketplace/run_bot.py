#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Запуск Agro Marketplace Bot з синхронізацією
"""

import asyncio
import logging
import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite

# Додаємо поточну директорію до шляху
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Імпорт конфігурації
from config.settings import BOT_TOKEN, ADMIN_IDS, DB_FILE

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задано в .env або Variables")

# Імпорт handlers (з src)
from src.bot.handlers import (
    start, registration, market, chat, logistics,
    admin_tools, subscriptions, offers_handlers, calculators
)

# Імпорт синхронізації
from src.bot.middlewares.sync import SyncEventProcessor

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

_LOCK_NAME = "telegram_polling"
_LOCK_TTL_SECONDS = int(os.getenv("BOT_LOCK_TTL_SECONDS", "45"))
_LOCK_HEARTBEAT_SECONDS = int(os.getenv("BOT_LOCK_HEARTBEAT_SECONDS", "15"))
_LOCK_OWNER = f"{socket.gethostname()}:{os.getpid()}"


async def _acquire_bot_lock(owner: str | None = None) -> bool:
    """Acquire a DB-backed bot lock to prevent duplicate polling instances."""
    owner = owner or _LOCK_OWNER
    now = datetime.utcnow()

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_runtime_locks (
                lock_name TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cur = await db.execute(
            "SELECT owner, updated_at FROM bot_runtime_locks WHERE lock_name = ?",
            (_LOCK_NAME,),
        )
        row = await cur.fetchone()

        if row:
            lock_owner, updated_at = row
            try:
                lock_time = datetime.fromisoformat(updated_at)
            except Exception:
                lock_time = now - timedelta(seconds=_LOCK_TTL_SECONDS + 1)

            if lock_owner != owner and (now - lock_time).total_seconds() < _LOCK_TTL_SECONDS:
                return False

        await db.execute(
            """
            INSERT INTO bot_runtime_locks(lock_name, owner, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(lock_name) DO UPDATE SET owner=excluded.owner, updated_at=excluded.updated_at
            """,
            (_LOCK_NAME, owner, now.isoformat()),
        )
        await db.commit()

    return True


async def _refresh_bot_lock(owner: str | None = None) -> None:
    owner = owner or _LOCK_OWNER
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE bot_runtime_locks SET updated_at = ? WHERE lock_name = ? AND owner = ?",
            (datetime.utcnow().isoformat(), _LOCK_NAME, owner),
        )
        await db.commit()


async def _release_bot_lock(owner: str | None = None) -> None:
    owner = owner or _LOCK_OWNER
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM bot_runtime_locks WHERE lock_name = ? AND owner = ?",
            (_LOCK_NAME, owner),
        )
        await db.commit()


async def _bot_lock_heartbeat(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(_LOCK_HEARTBEAT_SECONDS)
        await _refresh_bot_lock()


def run_migration():
    """Запускає міграцію бази даних перед стартом бота"""
    try:
        from src.database.migrate import migrate
        logger.info("🔧 Запуск міграції бази даних...")
        migrate(DB_FILE, verbose=False)
        logger.info("✅ Міграція завершена успішно")
    except ImportError:
        logger.warning("⚠️  Модуль міграції не знайдено, пропускаємо")
    except Exception as e:
        logger.error(f"❌ Помилка міграції: {e}")
        logger.warning("⚠️  Продовжуємо без міграції")


async def main():
    """Основна функція запуску бота"""

    # Виконуємо міграцію перед стартом
    run_migration()

    lock_acquired = await _acquire_bot_lock()
    if not lock_acquired:
        logger.error("❌ Виявлено інший активний інстанс бота. Поточний екземпляр завершує роботу.")
        return

    lock_stop_event = asyncio.Event()
    lock_task = asyncio.create_task(_bot_lock_heartbeat(lock_stop_event))

    # Ініціалізація бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Ініціалізація диспетчера
    dp = Dispatcher()

    # Ініціалізація sync processor
    sync_processor = SyncEventProcessor(bot)

    # Підключення роутерів
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(calculators.router)
    dp.include_router(market.router)
    dp.include_router(offers_handlers.router)
    dp.include_router(chat.router)
    dp.include_router(logistics.router)
    dp.include_router(subscriptions.router)
    dp.include_router(admin_tools.router)

    logger.info("🌾 Agro Marketplace Bot запущено!")
    logger.info(f"📋 Адміністратори: {ADMIN_IDS}")
    logger.info(f"💾 База даних: {DB_FILE}")
    logger.info("🔄 Синхронізація з веб-панеллю активована")

    try:
        # Видалення webhook (якщо був)
        await bot.delete_webhook(drop_pending_updates=True)

        # Запуск sync processor
        await sync_processor.start()

        # Запуск polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as e:
        logger.error(f"❌ Помилка запуску бота: {e}")
    finally:
        lock_stop_event.set()
        lock_task.cancel()
        try:
            await lock_task
        except Exception:
            pass

        await _release_bot_lock()

        # Зупинка sync processor
        await sync_processor.stop()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка: {e}")