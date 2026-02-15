"""
Middleware для показу реклами користувачам
Показує рекламу після N дій (повідомлення АБО натискань кнопок)
"""

import logging
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

logger = logging.getLogger(__name__)


class AdvertisementMiddleware(BaseMiddleware):
    """Показує рекламу користувачам після певної кількості взаємодій."""

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.action_counter: Dict[int, int] = {}

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        # 1) Спочатку обробляємо подію
        result = await handler(event, data)

        try:
            user_id: Optional[int] = None
            reply_target: Optional[Message] = None

            if isinstance(event, Message) and event.from_user:
                user_id = event.from_user.id
                reply_target = event
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_id = event.from_user.id
                # Відповідати будемо в той же чат, де натиснули кнопку
                reply_target = event.message

            if not user_id or not reply_target:
                return result

            # 2) Рахуємо "дію"
            self.action_counter[user_id] = self.action_counter.get(user_id, 0) + 1

            # 3) Беремо активну рекламу
            ad = await self._get_active_ad()

            # 4) Показуємо, якщо настав час
            if ad and self._should_show_ad(user_id, int(ad.get('show_frequency') or 3)):
                await self._show_ad(reply_target, user_id, ad)
                self.action_counter[user_id] = 0

        except Exception as e:
            logger.error(f"AdvertisementMiddleware error: {e}")

        return result

    def _should_show_ad(self, user_id: int, frequency: int) -> bool:
        return self.action_counter.get(user_id, 0) >= max(1, frequency)

    async def _get_active_ad(self) -> Optional[dict]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT * FROM advertisements
                    WHERE is_active = 1
                    ORDER BY RANDOM()
                    LIMIT 1
                    """
                )
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting ad: {e}")
            return None

    async def _show_ad(self, message: Message, user_id: int, ad: dict):
        try:
            await self._record_view(int(ad['id']), user_id)

            text = f"📢 <b>Реклама</b>\n\n{ad.get('content','')}"

            # Кнопки
            keyboard_rows = []
            btn_text = (ad.get('button_text') or '').strip()
            btn_url = (ad.get('button_url') or '').strip()
            if btn_text and btn_url:
                keyboard_rows.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
            keyboard_rows.append([InlineKeyboardButton(text="❌ Закрити", callback_data=f"ad_close_{ad['id']}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

            ad_type = (ad.get('type') or 'text').lower()
            image_url = (ad.get('image_url') or '').strip()

            if ad_type == 'image' and image_url:
                await message.answer_photo(photo=image_url, caption=text, reply_markup=keyboard)
            else:
                await message.answer(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing ad: {e}")

    async def _record_view(self, ad_id: int, user_id: int):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO advertisement_views (ad_id, user_id) VALUES (?, ?)",
                    (ad_id, user_id),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error recording view: {e}")
