#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agro Marketplace Bot - Головний файл запуску
Синхронізований з веб-панеллю через єдину БД
"""

import asyncio
import logging
import sys
from pathlib import Path

# Додаємо шляхи для імпортів
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Імпорт конфігурації
from config.settings import BOT_TOKEN, ADMIN_IDS, DB_PATH

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задано в .env або Variables")

# Створюємо директорію для логів
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def run_migration():
    """Запускає міграцію бази даних перед стартом бота"""
    try:
        from src.database.migrate import migrate
        logger.info("🔧 Запуск міграції бази даних...")
        migrate(str(DB_PATH), verbose=False)
        logger.info("✅ Міграція завершена успішно")
    except ImportError as e:
        logger.warning(f"⚠️  Модуль міграції не знайдено: {e}")
    except Exception as e:
        logger.error(f"❌ Помилка міграції: {e}")
        logger.warning("⚠️  Продовжуємо без міграції")


async def main():
    """Основна функція запуску бота"""
    
    logger.info("=" * 60)
    logger.info("🌾 Agro Marketplace Bot")
    logger.info("=" * 60)
    
    # Виконуємо міграцію перед стартом
    run_migration()

    # Ініціалізація бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Ініціалізація диспетчера
    dp = Dispatcher()

    # Підключення middleware для перевірки бану
    try:
        from src.bot.middlewares.ban_check import BanCheckMiddleware
        dp.message.middleware(BanCheckMiddleware())
        dp.callback_query.middleware(BanCheckMiddleware())
        logger.info("✅ BanCheckMiddleware підключено")
    except Exception as e:
        logger.warning(f"⚠️  Не вдалося підключити BanCheckMiddleware: {e}")

    # Підключення роутерів
    try:
        from src.bot.handlers import (
            start, registration, market, chat, 
            logistics, admin_tools, subscriptions, 
            offers_handlers, calculators
        )
        
        dp.include_router(registration.router)
        dp.include_router(calculators.router)
        dp.include_router(market.router)
        dp.include_router(offers_handlers.router)
        dp.include_router(chat.router)
        dp.include_router(logistics.router)
        dp.include_router(subscriptions.router)
        dp.include_router(admin_tools.router)
        dp.include_router(start.router)

        logger.info("✅ Всі роутери підключено")
    except Exception as e:
        logger.error(f"❌ Помилка підключення роутерів: {e}")
        logger.warning("⚠️  Бот запуститься без деяких функцій")

    logger.info(f"📋 Адміністратори: {ADMIN_IDS}")
    logger.info(f"💾 База даних: {DB_PATH}")
    logger.info("🚀 Запуск polling...")

    try:
        # Видалення webhook (якщо був)
        await bot.delete_webhook(drop_pending_updates=True)

        # Запуск polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as e:
        logger.error(f"❌ Помилка запуску бота: {e}")
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка: {e}", exc_info=True)
