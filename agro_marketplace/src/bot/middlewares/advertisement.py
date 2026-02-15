"""
Middleware для показу реклами користувачам
"""

import random
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

logger = logging.getLogger(__name__)


class AdvertisementMiddleware(BaseMiddleware):
    """Показує рекламу користувачам"""
    
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.action_counter = {}  # Лічильник дій користувача
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Спочатку обробляємо повідомлення
        result = await handler(event, data)
        
        # Перевіряємо чи треба показати рекламу
        if event.from_user:
            user_id = event.from_user.id
            
            # Лічильник дій
            self.action_counter[user_id] = self.action_counter.get(user_id, 0) + 1
            
            # Перевіряємо чи є активна реклама
            ad = await self._get_active_ad(user_id)
            
            if ad and self._should_show_ad(user_id, ad['show_frequency']):
                await self._show_ad(event, ad)
                self.action_counter[user_id] = 0  # Скидаємо лічильник
        
        return result
    
    def _should_show_ad(self, user_id: int, frequency: int) -> bool:
        """Чи треба показати рекламу цьому користувачу"""
        count = self.action_counter.get(user_id, 0)
        return count >= frequency
    
    async def _get_active_ad(self, user_id: int) -> dict:
        """Отримує активну рекламу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Отримуємо всі активні оголошення
                cursor = await db.execute("""
                    SELECT * FROM advertisements 
                    WHERE is_active = 1 
                    ORDER BY RANDOM() 
                    LIMIT 1
                """)
                
                row = await cursor.fetchone()
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"Error getting ad: {e}")
            return None
    
    async def _show_ad(self, message: Message, ad: dict):
        """Показує рекламу користувачу"""
        try:
            # Записуємо перегляд
            await self._record_view(ad['id'], message.from_user.id)
            
            # Формуємо текст
            text = f"📢 <b>Реклама</b>\n\n{ad['content']}"
            
            # Кнопки
            keyboard = None
            if ad['button_text'] and ad['button_url']:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=ad['button_text'],
                        url=ad['button_url']
                    )],
                    [InlineKeyboardButton(
                        text="❌ Закрити",
                        callback_data=f"ad_close_{ad['id']}"
                    )]
                ])
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="❌ Закрити",
                        callback_data=f"ad_close_{ad['id']}"
                    )]
                ])
            
            # Відправляємо
            if ad['type'] == 'image' and ad['image_url']:
                await message.answer_photo(
                    photo=ad['image_url'],
                    caption=text,
                    reply_markup=keyboard
                )
            else:
                await message.answer(
                    text=text,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            
            logger.info(f"Ad {ad['id']} shown to user {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"Error showing ad: {e}")
    
    async def _record_view(self, ad_id: int, user_id: int):
        """Записує перегляд реклами"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Записуємо перегляд
                await db.execute("""
                    INSERT INTO advertisement_views (ad_id, user_id)
                    VALUES (?, ?)
                """, (ad_id, user_id))
                
                # Оновлюємо лічильник
                await db.execute("""
                    UPDATE advertisements 
                    SET views_count = views_count + 1
                    WHERE id = ?
                """, (ad_id,))
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error recording view: {e}")
