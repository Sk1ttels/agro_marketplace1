"""
Middleware для перевірки статусу бану користувачів (aiogram 3.x)

В aiogram 3 middleware отримує конкретну подію (Message / CallbackQuery),
а не Update. Тому не використовуємо event.message / event.callback_query.
"""

from __future__ import annotations

from typing import Callable, Dict, Any, Awaitable, Optional
import aiosqlite
import logging
import os

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)

# Отримуємо шлях до БД з конфігурації/ENV
try:
    from config.settings import DB_PATH  # type: ignore
    DB_FILE = str(DB_PATH)
except Exception:
    DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db")


class BanCheckMiddleware(BaseMiddleware):
    """Блокує обробку подій від забанених користувачів."""

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:

        user = None
        reply_message: Optional[Message] = None
        cb: Optional[CallbackQuery] = None

        if isinstance(event, Message):
            user = event.from_user
            reply_message = event

        elif isinstance(event, CallbackQuery):
            user = event.from_user
            cb = event

        # Якщо це не Message/CallbackQuery — не чіпаємо
        if not user:
            return await handler(event, data)

        # Перевірка бану в БД
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                cursor = await db.execute(
                    "SELECT is_banned FROM users WHERE telegram_id = ?",
                    (user.id,),
                )
                row = await cursor.fetchone()

            if row and int(row[0]) == 1:
                logger.info("Blocked access attempt from banned user %s", user.id)

                if reply_message:
                    await reply_message.answer(
                        "🚫 <b>Ваш акаунт заблокований</b>\n\n"
                        "Ви не можете використовувати бота.\n"
                        "Для отримання додаткової інформації зверніться до адміністрації."
                    )
                elif cb:
                    await cb.answer("🚫 Ваш акаунт заблокований", show_alert=True)

                return  # stop pipeline

        except Exception as e:
            logger.exception("Error checking ban status for user %s: %s", user.id, e)

        return await handler(event, data)
