"""
Throttle middleware — захист від спаму та дублювання повідомлень.
Ігнорує повідомлення від одного юзера якщо попереднє ще обробляється,
або якщо той самий текст надійшов двічі підряд менш ніж за 1.5 секунди.
"""
import time
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)

# Мінімальний інтервал між однаковими повідомленнями (секунди)
SAME_MSG_THROTTLE = 1.5
# Мінімальний інтервал між будь-якими повідомленнями від одного юзера
ANY_MSG_THROTTLE = 0.3


class ThrottleMiddleware(BaseMiddleware):
    """Захищає від спаму і дублювання кнопок."""

    def __init__(self):
        super().__init__()
        # {user_id: (last_text, last_time)}
        self._last: Dict[int, tuple] = {}
        # {user_id: last_any_time}
        self._last_any: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        text = None

        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            text = event.text or event.caption or "__media__"
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            text = event.data or "__cb__"

        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()

        # Перевірка загальної частоти
        last_any = self._last_any.get(user_id, 0)
        if now - last_any < ANY_MSG_THROTTLE:
            # Занадто часто — ігноруємо
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None

        # Перевірка дублювання того самого тексту
        last_text, last_time = self._last.get(user_id, (None, 0))
        if text == last_text and (now - last_time) < SAME_MSG_THROTTLE:
            logger.debug(f"Throttled duplicate from {user_id}: {text!r}")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None

        # Оновлюємо лічильники
        self._last[user_id] = (text, now)
        self._last_any[user_id] = now

        # Очищаємо старі записи щоб не росла пам'ять
        if len(self._last) > 10000:
            cutoff = now - 60
            self._last = {k: v for k, v in self._last.items() if v[1] > cutoff}
            self._last_any = {k: v for k, v in self._last_any.items() if v > cutoff}

        return await handler(event, data)
