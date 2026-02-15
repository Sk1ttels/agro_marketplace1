from __future__ import annotations

import os
import json
import logging
import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db")

def _admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    if not raw:
        return set()
    # allow "1,2,3" or JSON list
    try:
        if raw.strip().startswith("["):
            return set(int(x) for x in json.loads(raw))
    except Exception:
        pass
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

def is_admin(tg_id: int) -> bool:
    return tg_id in _admin_ids()

def kb_admin():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="📦 Останні лоти", callback_data="admin:lots")
    kb.adjust(1)
    return kb.as_markup()

@router.message(Command("admin"))
@router.message(F.text == "🛠 Адмін-панель")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу.")
        return
    await message.answer("🛠 <b>Адмін-панель</b>", reply_markup=kb_admin())

@router.callback_query(F.data == "admin:stats")
async def admin_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Немає доступу", show_alert=True)
        return
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM lots")
        lots = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM lots WHERE status='active'")
        active = (await cur.fetchone())[0]
    await cb.message.answer(f"📊 Статистика:\n👥 Користувачів: <b>{users}</b>\n📦 Лотів: <b>{lots}</b>\n✅ Активних: <b>{active}</b>")
    await cb.answer()

@router.callback_query(F.data == "admin:lots")
async def admin_lots(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Немає доступу", show_alert=True)
        return
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, type, crop, region, price, status FROM lots ORDER BY id DESC LIMIT 10")
        rows = await cur.fetchall()
    if not rows:
        await cb.message.answer("Лотів немає.")
        await cb.answer()
        return
    for r in rows:
        t = "📤 Продаж" if r["type"] == "sell" else "📥 Купівля"
        await cb.message.answer(f"{t} • #{r['id']} • 🌾 {r['crop']} • 📍 {r['region']} • 💰 {r['price'] or '—'} • {r['status']}")
    await cb.answer()
