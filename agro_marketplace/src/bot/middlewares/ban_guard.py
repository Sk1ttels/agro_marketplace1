from __future__ import annotations

import aiosqlite
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

DB_FILE = "agro_bot.db"


class BanGuardMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        user_id = user.id

        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT is_banned FROM users WHERE telegram_id=?",
                (user_id,),
            )
            row = await cur.fetchone()

        if row and row["is_banned"]:
            if isinstance(event, Message):
                await event.answer("⛔ Ваш акаунт заблокований.", reply_markup=ReplyKeyboardRemove())
                return

            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⛔ Ваш акаунт заблокований.", show_alert=True)
                except Exception:
                    pass
                try:
                    await event.message.answer("⛔ Ваш акаунт заблокований.", reply_markup=ReplyKeyboardRemove())
                except Exception:
                    pass
                return

            return

        return await handler(event, data)
