"""
Sync Middleware — обробка подій синхронізації від веб-панелі.
SyncEventProcessor читає JSON-файл кожні 2 секунди і:
  - сповіщає забанених/розбанених користувачів у Telegram
  - сповіщає власників лотів при зміні статусу
"""
import asyncio
import logging
from typing import Any, Callable, Awaitable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

try:
    from src.bot.services.sync_service import FileBasedSync
except ImportError:
    from ..services.sync_service import FileBasedSync

logger = logging.getLogger(__name__)


class SyncEventProcessor:
    """Читає події від веб-панелі і надсилає Telegram-повідомлення."""

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self._task = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("✅ SyncEventProcessor запущено (перевірка кожні 2с)")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹ SyncEventProcessor зупинено")

    async def _loop(self):
        while self.is_running:
            try:
                await self._process_events()
            except Exception as e:
                logger.error("Помилка в SyncEventProcessor: %s", e)
            await asyncio.sleep(2)

    async def _process_events(self):
        events = FileBasedSync.read_unprocessed_events()
        if not events:
            return

        for idx, event in enumerate(events):
            event_type = event.get("event_type")
            data = event.get("data", {})
            try:
                if event_type == "user_banned":
                    await self._on_user_banned(data)
                elif event_type == "user_unbanned":
                    await self._on_user_unbanned(data)
                elif event_type == "lot_status_changed":
                    await self._on_lot_status_changed(data)
                elif event_type == "settings_changed":
                    logger.info("Налаштування змінено через веб-панель")
                FileBasedSync.mark_event_processed(idx)
            except Exception as e:
                logger.error("Помилка обробки події %s: %s", event_type, e)

    async def _on_user_banned(self, data: dict):
        tg_id = data.get("telegram_id")
        if not tg_id:
            return
        try:
            await self.bot.send_message(
                tg_id,
                "⛔️ <b>Ваш акаунт заблоковано адміністратором</b>\n\n"
                "Ви більше не можете користуватися ботом.\n"
                "Якщо вважаєте, що це помилка — зверніться до підтримки.",
                parse_mode="HTML",
            )
            logger.info("Сповіщення про бан надіслано: telegram_id=%s", tg_id)
        except Exception as e:
            logger.warning("Не вдалося надіслати сповіщення про бан %s: %s", tg_id, e)

    async def _on_user_unbanned(self, data: dict):
        tg_id = data.get("telegram_id")
        if not tg_id:
            return
        try:
            await self.bot.send_message(
                tg_id,
                "✅ <b>Ваш акаунт розблоковано!</b>\n\n"
                "Ви знову можете користуватися всіма функціями бота.\n"
                "Натисніть /start для продовження.",
                parse_mode="HTML",
            )
            logger.info("Сповіщення про розбан надіслано: telegram_id=%s", tg_id)
        except Exception as e:
            logger.warning("Не вдалося надіслати сповіщення про розбан %s: %s", tg_id, e)

    async def _on_lot_status_changed(self, data: dict):
        lot_id = data.get("lot_id")
        new_status = data.get("new_status")
        tg_id = data.get("owner_telegram_id")
        if not all([lot_id, new_status, tg_id]):
            return

        messages = {
            "active":   f"✅ Ваш лот #{lot_id} активовано адміністратором.",
            "closed":   f"⏹ Ваш лот #{lot_id} закрито адміністратором.",
            "blocked":  f"⛔️ Ваш лот #{lot_id} заблоковано адміністратором.",
            "archived": f"📦 Ваш лот #{lot_id} переміщено в архів.",
        }
        text = messages.get(new_status, f"ℹ️ Статус вашого лота #{lot_id} змінено: {new_status}")

        try:
            await self.bot.send_message(tg_id, text, parse_mode="HTML")
            logger.info("Сповіщення про лот %s надіслано: telegram_id=%s", lot_id, tg_id)
        except Exception as e:
            logger.warning("Не вдалося надіслати сповіщення про лот %s: %s", lot_id, e)


class SyncMiddleware(BaseMiddleware):
    """Порожній middleware — залишений для сумісності."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        return await handler(event, data)
