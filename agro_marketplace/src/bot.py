#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agro Marketplace Bot - Головний файл запуску

Telegram бот для аграрного маркетплейсу
"""

import asyncio
import logging
import sys
from pathlib import Path

# Додаємо шлях до src для імпортів
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Імпорт конфігурації
from config.settings import BOT_TOKEN, ADMIN_IDS, DB_FILE

# Імпорт handlers
from bot.handlers import start, registration, market, chat, logistics, admin_tools, subscriptions, offers_handlers, calculators

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


def run_migration():
    """Запускає міграцію бази даних перед стартом бота"""
    try:
        from database.migrate import migrate
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

    # Ініціалізація бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Ініціалізація диспетчера
    dp = Dispatcher()

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

    try:
        # Видалення webhook (якщо був)
        await bot.delete_webhook(drop_pending_updates=True)

        # Запуск polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as e:
        logger.error(f"❌ Помилка запуску бота: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка: {e}")
