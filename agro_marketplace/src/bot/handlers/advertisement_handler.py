"""
Обробники для взаємодії з рекламою
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
import aiosqlite
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("ad_close_"))
async def close_ad(callback: CallbackQuery):
    """Закриває рекламу"""
    try:
        await callback.message.delete()
        await callback.answer("✅ Реклама закрита")
    except Exception as e:
        logger.error(f"Error closing ad: {e}")
        await callback.answer("Помилка")


@router.callback_query(F.data.startswith("ad_click_"))
async def click_ad(callback: CallbackQuery):
    """Реєструє клік по рекламі"""
    try:
        ad_id = int(callback.data.split("_")[2])
        
        # Записуємо клік
        from config.settings import DB_PATH
        async with aiosqlite.connect(str(DB_PATH)) as db:
            # Оновлюємо лічильник кліків
            await db.execute("""
                UPDATE advertisements 
                SET clicks_count = clicks_count + 1
                WHERE id = ?
            """, (ad_id,))
            
            # Записуємо в історію
            await db.execute("""
                UPDATE advertisement_views 
                SET clicked = 1
                WHERE ad_id = ? AND user_id = ?
                  AND id = (
                      SELECT id FROM advertisement_views
                      WHERE ad_id = ? AND user_id = ?
                      ORDER BY viewed_at DESC
                      LIMIT 1
                  )
            """, (ad_id, callback.from_user.id, ad_id, callback.from_user.id))
            
            await db.commit()
        
        await callback.answer("✅ Посилання відкрито")
        
    except Exception as e:
        logger.error(f"Error recording click: {e}")
        await callback.answer("Помилка")
