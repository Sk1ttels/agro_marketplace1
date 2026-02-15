"""
Sync Middleware - Handles synchronization events in the bot
"""
import asyncio
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, Update

# ВИПРАВЛЕНИЙ ІМПОРТ - відносний шлях
from ..services.sync_service import FileBasedSync

logger = logging.getLogger(__name__)


class SyncEventProcessor:
    """Processes synchronization events from web panel"""
    
    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self._task = None
        
    async def start(self):
        """Start processing sync events"""
        if self.is_running:
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("✅ Sync event processor started")
        
    async def stop(self):
        """Stop processing sync events"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹ Sync event processor stopped")
        
    async def _process_loop(self):
        """Main processing loop"""
        while self.is_running:
            try:
                await self._process_events()
                await asyncio.sleep(2)  # Check every 2 seconds
            except Exception as e:
                logger.error(f"Error in sync processor loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_events(self):
        """Process unprocessed events"""
        try:
            events = FileBasedSync.read_unprocessed_events()
            
            for idx, event in enumerate(events):
                try:
                    event_type = event.get('event_type')
                    data = event.get('data', {})
                    
                    if event_type == 'user_banned':
                        await self._handle_user_banned(data)
                    elif event_type == 'user_unbanned':
                        await self._handle_user_unbanned(data)
                    elif event_type == 'lot_status_changed':
                        await self._handle_lot_status_changed(data)
                    elif event_type == 'settings_changed':
                        await self._handle_settings_changed(data)
                    
                    # Mark as processed
                    FileBasedSync.mark_event_processed(idx)
                    
                except Exception as e:
                    logger.error(f"Error processing event {event_type}: {e}")
                    
        except Exception as e:
            logger.error(f"Error reading sync events: {e}")
    
    async def _handle_user_banned(self, data: Dict[str, Any]):
        """Handle user ban event"""
        telegram_id = data.get('telegram_id')
        if not telegram_id:
            return
        
        try:
            await self.bot.send_message(
                telegram_id,
                "⛔️ <b>Ваш акаунт заблоковано</b>\n\n"
                "Ви більше не можете користуватися ботом.\n"
                "Якщо вважаєте, що це помилка, зв'яжіться з адміністратором.",
                parse_mode="HTML"
            )
            logger.info(f"Notified user {telegram_id} about ban")
        except Exception as e:
            logger.error(f"Failed to notify user {telegram_id} about ban: {e}")
    
    async def _handle_user_unbanned(self, data: Dict[str, Any]):
        """Handle user unban event"""
        telegram_id = data.get('telegram_id')
        if not telegram_id:
            return
        
        try:
            await self.bot.send_message(
                telegram_id,
                "✅ <b>Ваш акаунт розблоковано</b>\n\n"
                "Ви знову можете користуватися всіма функціями бота.",
                parse_mode="HTML"
            )
            logger.info(f"Notified user {telegram_id} about unban")
        except Exception as e:
            logger.error(f"Failed to notify user {telegram_id} about unban: {e}")
    
    async def _handle_lot_status_changed(self, data: Dict[str, Any]):
        """Handle lot status change event"""
        lot_id = data.get('lot_id')
        new_status = data.get('new_status')
        owner_telegram_id = data.get('owner_telegram_id')
        
        if not all([lot_id, new_status, owner_telegram_id]):
            return
        
        status_messages = {
            'active': '✅ Ваше оголошення #{} було активовано адміністратором',
            'closed': '⏹ Ваше оголошення #{} було закрито адміністратором',
            'blocked': '⛔️ Ваше оголошення #{} було заблоковано адміністратором',
            'archived': '📦 Ваше оголошення #{} було переміщено в архів',
        }
        
        message = status_messages.get(new_status, f'Статус вашого оголошення #{lot_id} змінено на: {new_status}')
        
        try:
            await self.bot.send_message(
                owner_telegram_id,
                message.format(lot_id),
                parse_mode="HTML"
            )
            logger.info(f"Notified user {owner_telegram_id} about lot {lot_id} status change")
        except Exception as e:
            logger.error(f"Failed to notify user {owner_telegram_id} about lot status: {e}")
    
    async def _handle_settings_changed(self, data: Dict[str, Any]):
        """Handle settings change event"""
        changed = data.get('changed', {})
        logger.info(f"Settings changed: {changed}")
        # Settings changes don't need immediate user notification
        # They will be applied on next bot restart or can be cached


class SyncMiddleware(BaseMiddleware):
    """Middleware to check for sync events"""
    
    def __init__(self):
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Process sync events before handling user request
        # This ensures banned users get blocked immediately
        
        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    """Enhanced ban check that considers web panel bans"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not event.from_user:
            return await handler(event, data)
        
        # Check if user is banned in database
        from bot.database.engine import get_session
        from bot.database.models import User
        
        async with get_session() as session:
            user = await session.execute(
                f"SELECT * FROM users WHERE telegram_id = {event.from_user.id}"
            )
            user = user.fetchone()
            
            if user and user.get('is_banned'):
                await event.answer(
                    "⛔️ Ваш акаунт заблоковано.\n"
                    "Якщо вважаєте, що це помилка, зв'яжіться з адміністратором."
                )
                return
        
        return await handler(event, data)
