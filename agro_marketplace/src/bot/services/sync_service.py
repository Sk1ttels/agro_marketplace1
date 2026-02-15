"""
Sync Service - Real-time synchronization between Web Panel and Telegram Bot
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class SyncEvent:
    """Represents a synchronization event"""
    
    def __init__(self, event_type: str, data: Dict[str, Any], timestamp: Optional[datetime] = None):
        self.event_type = event_type
        self.data = data
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }


class SyncService:
    """Service for synchronizing data between web panel and bot"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_queue = asyncio.Queue()
        self.is_running = False
        self._task = None
        self.handlers = {}
        
    async def start(self):
        """Start the sync service"""
        if self.is_running:
            logger.warning("Sync service is already running")
            return
            
        self.is_running = True
        self._task = asyncio.create_task(self._process_events())
        logger.info("✅ Sync service started")
        
    async def stop(self):
        """Stop the sync service"""
        if not self.is_running:
            return
            
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹ Sync service stopped")
        
    def register_handler(self, event_type: str, handler):
        """Register a handler for specific event type"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"Registered handler for event: {event_type}")
        
    async def emit(self, event_type: str, data: Dict[str, Any]):
        """Emit a synchronization event"""
        event = SyncEvent(event_type, data)
        await self.event_queue.put(event)
        logger.debug(f"Event emitted: {event_type} - {data}")
        
    async def _process_events(self):
        """Process events from the queue"""
        while self.is_running:
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )
                
                handlers = self.handlers.get(event.event_type, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event.data)
                        else:
                            handler(event.data)
                    except Exception as e:
                        logger.error(f"Error in handler for {event.event_type}: {e}")
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")


class WebPanelSync:
    """Web panel synchronization utilities"""
    
    def __init__(self, sync_service: SyncService):
        self.sync = sync_service
        
    async def on_user_banned(self, user_id: int, telegram_id: int):
        """Handle user ban event from web panel"""
        await self.sync.emit('user_banned', {
            'user_id': user_id,
            'telegram_id': telegram_id,
            'timestamp': datetime.now().isoformat()
        })
        
    async def on_user_unbanned(self, user_id: int, telegram_id: int):
        """Handle user unban event from web panel"""
        await self.sync.emit('user_unbanned', {
            'user_id': user_id,
            'telegram_id': telegram_id,
            'timestamp': datetime.now().isoformat()
        })
        
    async def on_lot_status_changed(self, lot_id: int, new_status: str, owner_telegram_id: int):
        """Handle lot status change from web panel"""
        await self.sync.emit('lot_status_changed', {
            'lot_id': lot_id,
            'new_status': new_status,
            'owner_telegram_id': owner_telegram_id,
            'timestamp': datetime.now().isoformat()
        })
        
    async def on_setting_changed(self, key: str, value: str):
        """Handle setting change from web panel"""
        await self.sync.emit('setting_changed', {
            'key': key,
            'value': value,
            'timestamp': datetime.now().isoformat()
        })


class FileBasedSync:
    """File-based synchronization for simpler setups"""
    
    SYNC_FILE = Path(__file__).parent.parent.parent / "web_panel" / "data" / "sync_events.json"
    
    @classmethod
    def write_event(cls, event_type: str, data: Dict[str, Any]):
        """Write synchronization event to file"""
        try:
            cls.SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Read existing events
            events = []
            if cls.SYNC_FILE.exists():
                try:
                    with open(cls.SYNC_FILE, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                except json.JSONDecodeError:
                    events = []
            
            # Add new event
            events.append({
                'event_type': event_type,
                'data': data,
                'timestamp': datetime.now().isoformat(),
                'processed': False
            })
            
            # Keep only last 1000 events
            events = events[-1000:]
            
            # Write back
            with open(cls.SYNC_FILE, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"Sync event written: {event_type}")
            
        except Exception as e:
            logger.error(f"Error writing sync event: {e}")
    
    @classmethod
    def read_unprocessed_events(cls):
        """Read unprocessed events from file"""
        try:
            if not cls.SYNC_FILE.exists():
                return []
            
            with open(cls.SYNC_FILE, 'r', encoding='utf-8') as f:
                events = json.load(f)
            
            return [e for e in events if not e.get('processed', False)]
            
        except Exception as e:
            logger.error(f"Error reading sync events: {e}")
            return []
    
    @classmethod
    def mark_event_processed(cls, event_index: int):
        """Mark event as processed"""
        try:
            if not cls.SYNC_FILE.exists():
                return
            
            with open(cls.SYNC_FILE, 'r', encoding='utf-8') as f:
                events = json.load(f)
            
            if 0 <= event_index < len(events):
                events[event_index]['processed'] = True
            
            with open(cls.SYNC_FILE, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Error marking event as processed: {e}")


# Global sync service instance
_sync_service: Optional[SyncService] = None


def get_sync_service() -> Optional[SyncService]:
    """Get global sync service instance"""
    return _sync_service


def init_sync_service(db_path: str) -> SyncService:
    """Initialize global sync service"""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService(db_path)
    return _sync_service
