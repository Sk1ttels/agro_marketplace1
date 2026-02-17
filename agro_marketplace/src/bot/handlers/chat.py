"""
💬 Чати та 📇 Контакти
- Запит на контакт → присилає повне фото+ім'я+номер+username
- Прийняв → відкривається двосторонній чат у боті
- Повідомлення пересилаються в реальному часі
"""
from __future__ import annotations

import os
import logging
from typing import Optional

import aiosqlite
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.bot.keyboards.main import main_menu

logger = logging.getLogger(__name__)
router = Router()

try:
    from config.settings import DB_PATH as _DB
    DB_FILE = str(_DB)
except Exception:
    DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db")


# ══════════════════════ FSM ══════════════════════

class ChatState(StatesGroup):
    chatting = State()


# ══════════════════════ DB INIT ══════════════════════

async def _ensure_tables():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id    INTEGER NOT NULL,
                user2_id    INTEGER NOT NULL,
                lot_id      INTEGER,
                status      TEXT NOT NULL DEFAULT 'active',
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL,
                sender_user_id  INTEGER NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                contact_user_id  INTEGER NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending',
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, contact_user_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cs_u1 ON chat_sessions(user1_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cs_u2 ON chat_sessions(user2_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cm_s  ON chat_messages(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_co_u  ON contacts(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_co_c  ON contacts(contact_user_id)")
        await db.commit()


# ══════════════════════ DB HELPERS ══════════════════════

async def _get_user_id(telegram_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def _get_user_full(user_id: int) -> Optional[dict]:
    """Повертає всі дані юзера: telegram_id, role, region, phone, company"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, telegram_id, role, region, phone, company FROM users WHERE id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def _get_telegram_id(user_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def _get_lot_owner(lot_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT owner_user_id FROM lots WHERE id=?", (lot_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def _contact_status(from_id: int, to_id: int) -> str:
    """none | pending | accepted"""
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT status FROM contacts WHERE user_id=? AND contact_user_id=?",
            (from_id, to_id)
        )
        row = await cur.fetchone()
        return row[0] if row else "none"


async def _get_or_create_session(u1: int, u2: int, lot_id: Optional[int]) -> int:
    a, b = sorted([u1, u2])
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id FROM chat_sessions
               WHERE user1_id=? AND user2_id=? AND COALESCE(lot_id,0)=COALESCE(?,0)
               AND status='active'""",
            (a, b, lot_id)
        )
        row = await cur.fetchone()
        if row:
            return row["id"]
        cur = await db.execute(
            "INSERT INTO chat_sessions(user1_id,user2_id,lot_id) VALUES(?,?,?)",
            (a, b, lot_id)
        )
        await db.commit()
        return cur.lastrowid


# ══════════════════════ KEYBOARDS ══════════════════════

def kb_in_chat() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Вийти з чату", callback_data="chat:exit")
    kb.button(text="📇 Надіслати контакт", callback_data="chat:send_contact")
    kb.adjust(2)
    return kb.as_markup()


def kb_exit_chat():
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ Вийти з чату")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def kb_contact_request(from_user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Прийняти", callback_data=f"contact:accept:{from_user_id}")
    kb.button(text="❌ Відхилити", callback_data=f"contact:decline:{from_user_id}")
    kb.adjust(2)
    return kb.as_markup()


def kb_open_chat(session_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Відкрити чат", callback_data=f"chat:open:{session_id}")
    kb.adjust(1)
    return kb.as_markup()


def kb_write_contact(contact_user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написати", callback_data=f"contact:chat:{contact_user_id}")
    kb.adjust(1)
    return kb.as_markup()


# ══════════════════════ FORMAT HELPERS ══════════════════════

ROLE_LABELS = {
    "farmer":   "👨‍🌾 Фермер",
    "buyer":    "🧑‍💼 Покупець",
    "logistic": "🚚 Логіст",
    "admin":    "🛡 Адмін",
}


async def _send_contact_card(bot: Bot, to_telegram_id: int, user_info: dict,
                              tg_user, title: str = "📇 Контакт"):
    """
    Відправляє картку контакту: фото (якщо є) + всі дані.
    tg_user — об'єкт aiogram User щоб отримати фото і username.
    """
    role = ROLE_LABELS.get(user_info.get("role", ""), "—")
    phone = user_info.get("phone") or "—"
    company = user_info.get("company") or "—"
    region = user_info.get("region") or "—"
    tg_id = user_info.get("telegram_id")

    first = tg_user.first_name or ""
    last = tg_user.last_name or ""
    full_name = f"{first} {last}".strip() or "—"
    username = f"@{tg_user.username}" if tg_user.username else "—"

    text = (
        f"{title}\n\n"
        f"👤 <b>{full_name}</b>\n"
        f"🎭 Роль: {role}\n"
        f"📱 Username: {username}\n"
        f"📞 Телефон: <b>{phone}</b>\n"
        f"🏢 Компанія: {company}\n"
        f"📍 Регіон: {region}\n"
        f"🆔 Telegram ID: <code>{tg_id}</code>"
    )

    # Пробуємо надіслати фото профілю
    sent_photo = False
    try:
        photos = await bot.get_user_profile_photos(tg_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            await bot.send_photo(to_telegram_id, photo=file_id, caption=text)
            sent_photo = True
    except Exception:
        pass

    if not sent_photo:
        await bot.send_message(to_telegram_id, text)


# ══════════════════════ 💬 МОЇ ЧАТИ ══════════════════════

@router.message(F.text == "💬 Мої чати")
async def my_chats(message: Message):
    await _ensure_tables()
    user_id = await _get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("Спочатку пройдіть реєстрацію: /start")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT cs.id, cs.user1_id, cs.user2_id, cs.lot_id, cs.status,
                      u1.company as c1, u2.company as c2,
                      u1.telegram_id as tg1, u2.telegram_id as tg2
               FROM chat_sessions cs
               LEFT JOIN users u1 ON cs.user1_id=u1.id
               LEFT JOIN users u2 ON cs.user2_id=u2.id
               WHERE (cs.user1_id=? OR cs.user2_id=?) AND cs.status='active'
               ORDER BY cs.id DESC LIMIT 20""",
            (user_id, user_id)
        )
        rows = await cur.fetchall()

    if not rows:
        await message.answer(
            "💬 <b>Мої чати</b>\n\n"
            "У вас ще немає активних чатів.\n\n"
            "💡 Натисніть «💬 Написати» на картці лота в Маркеті."
        )
        return

    await message.answer(f"💬 <b>Активних чатів: {len(rows)}</b>")
    for r in rows:
        is_u1 = (r["user1_id"] == user_id)
        other_company = r["c2"] if is_u1 else r["c1"]
        other_tg = r["tg2"] if is_u1 else r["tg1"]
        lot_text = f" • лот #{r['lot_id']}" if r["lot_id"] else ""
        await message.answer(
            f"💬 <b>{other_company or 'Користувач'}</b>{lot_text}",
            reply_markup=kb_open_chat(r["id"])
        )


# ══════════════════════ 📇 МОЇ КОНТАКТИ ══════════════════════

@router.message(F.text == "📇 Мої контакти")
async def my_contacts(message: Message):
    await _ensure_tables()
    user_id = await _get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("Спочатку пройдіть реєстрацію: /start")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Прийняті контакти
        cur = await db.execute(
            """SELECT u.id, u.telegram_id, u.phone, u.company, u.role, u.region
               FROM contacts c JOIN users u ON c.contact_user_id=u.id
               WHERE c.user_id=? AND c.status='accepted'
               ORDER BY c.created_at DESC LIMIT 30""",
            (user_id,)
        )
        accepted = await cur.fetchall()

        # Вхідні запити
        cur = await db.execute(
            """SELECT u.id, u.telegram_id, u.phone, u.company, u.role
               FROM contacts c JOIN users u ON c.user_id=u.id
               WHERE c.contact_user_id=? AND c.status='pending'
               ORDER BY c.created_at DESC LIMIT 10""",
            (user_id,)
        )
        incoming = await cur.fetchall()

        # Відправлені запити
        cur = await db.execute(
            """SELECT u.id, u.telegram_id, u.company
               FROM contacts c JOIN users u ON c.contact_user_id=u.id
               WHERE c.user_id=? AND c.status='pending'
               ORDER BY c.created_at DESC LIMIT 10""",
            (user_id,)
        )
        outgoing = await cur.fetchall()

    # Вхідні запити — показуємо першими
    if incoming:
        await message.answer(f"📬 <b>Вхідні запити на контакт: {len(incoming)}</b>")
        for u in incoming:
            role = ROLE_LABELS.get(u["role"], "—")
            company = u["company"] or "—"
            text = (
                f"👤 <b>Запит від користувача</b>\n"
                f"🎭 {role}\n"
                f"🏢 {company}\n"
                f"🆔 <code>{u['telegram_id']}</code>"
            )
            await message.answer(text, reply_markup=kb_contact_request(u["id"]))

    # Підтверджені контакти
    if accepted:
        await message.answer(f"✅ <b>Контакти: {len(accepted)}</b>")
        for u in accepted:
            role = ROLE_LABELS.get(u["role"], "—")
            phone = u["phone"] or "—"
            company = u["company"] or "—"
            region = u["region"] or "—"
            tg_id = u["telegram_id"]

            # Отримуємо username через Telegram
            try:
                tg_chat = await message.bot.get_chat(tg_id)
                username_line = f"\n📱 @{tg_chat.username}" if tg_chat.username else ""
                full_name = tg_chat.full_name or "—"
            except Exception:
                username_line = ""
                full_name = "—"

            text = (
                f"👤 <b>{full_name}</b>\n"
                f"🎭 {role}\n"
                f"🏢 {company}\n"
                f"📍 {region}\n"
                f"📞 <b>{phone}</b>"
                f"{username_line}"
            )
            await message.answer(text, reply_markup=kb_write_contact(u["id"]))
    elif not incoming:
        await message.answer(
            "📇 <b>Мої контакти</b>\n\n"
            "У вас ще немає контактів.\n\n"
            "💡 Знайдіть потрібний лот у Маркеті і надішліть запит на контакт."
        )

    # Відправлені запити в очікуванні
    if outgoing:
        text = f"⏳ <b>Очікують відповіді: {len(outgoing)}</b>\n\n"
        for u in outgoing:
            text += f"• {u['company'] or 'Користувач'} (<code>{u['telegram_id']}</code>)\n"
        await message.answer(text)


# ══════════════════════ ВІДКРИТИ ЧАТ ══════════════════════

@router.callback_query(F.data.startswith("chat:open:"))
async def open_chat(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    session_id = int(cb.data.split(":")[-1])
    user_id = await _get_user_id(cb.from_user.id)
    if not user_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,user1_id,user2_id,status FROM chat_sessions WHERE id=?",
            (session_id,)
        )
        sess = await cur.fetchone()

    if not sess or sess["status"] != "active":
        await cb.answer("Чат не активний", show_alert=True)
        return
    if user_id not in (sess["user1_id"], sess["user2_id"]):
        await cb.answer("Немає доступу", show_alert=True)
        return

    # Показуємо останні 10 повідомлень
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT m.content, m.sender_user_id, m.created_at,
                      u.company, u.telegram_id
               FROM chat_messages m LEFT JOIN users u ON m.sender_user_id=u.id
               WHERE m.session_id=? ORDER BY m.id DESC LIMIT 10""",
            (session_id,)
        )
        msgs = list(reversed(await cur.fetchall()))

    await state.update_data(chat_session_id=session_id)
    await state.set_state(ChatState.chatting)

    if msgs:
        history = "📜 <b>Останні повідомлення:</b>\n\n"
        for m in msgs:
            me = "→ Ви" if m["sender_user_id"] == user_id else f"← {m['company'] or 'Співрозмовник'}"
            history += f"<i>{m['created_at'][:16]}</i> <b>{me}:</b>\n{m['content']}\n\n"
        await cb.message.answer(history)

    await cb.message.answer(
        "💬 <b>Чат відкрито.</b> Пишіть повідомлення — вони надходять співрозмовнику.\n\n"
        "📇 Натисніть <b>«Надіслати контакт»</b> щоб поділитися своїм телефоном і username.",
        reply_markup=kb_exit_chat()
    )
    await cb.answer()


# ══════════════════════ НАПИСАТИ КОНТАКТУ ══════════════════════

@router.callback_query(F.data.startswith("contact:chat:"))
async def chat_with_contact(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    contact_user_id = int(cb.data.split(":")[-1])
    my_id = await _get_user_id(cb.from_user.id)
    if not my_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    status = await _contact_status(my_id, contact_user_id)
    if status != "accepted":
        await cb.answer("Спочатку прийміть запит на контакт", show_alert=True)
        return

    session_id = await _get_or_create_session(my_id, contact_user_id, None)
    await state.update_data(chat_session_id=session_id)
    await state.set_state(ChatState.chatting)
    await cb.message.answer(
        "💬 <b>Чат відкрито.</b> Пишіть повідомлення.",
        reply_markup=kb_exit_chat()
    )
    await cb.answer()


# ══════════════════════ ЧАТ З ЛОТА ══════════════════════

@router.callback_query(F.data.startswith("chat:start:lot:"))
async def start_chat_from_lot(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    lot_id = int(cb.data.split(":")[-1])
    me = await _get_user_id(cb.from_user.id)
    if not me:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    owner = await _get_lot_owner(lot_id)
    if not owner:
        await cb.answer("Лот не знайдено", show_alert=True)
        return
    if owner == me:
        await cb.answer("Це ваш лот 🙂", show_alert=True)
        return

    status = await _contact_status(me, owner)

    if status == "accepted":
        session_id = await _get_or_create_session(me, owner, lot_id)
        await state.update_data(chat_session_id=session_id)
        await state.set_state(ChatState.chatting)
        await cb.message.answer("💬 <b>Чат відкрито.</b> Пишіть повідомлення.", reply_markup=kb_exit_chat())
        await cb.answer()
        return

    # Не в контактах — пропонуємо надіслати запит
    owner_info = await _get_user_full(owner)
    company = (owner_info or {}).get("company") or "Користувач"
    role = ROLE_LABELS.get((owner_info or {}).get("role", ""), "")

    kb = InlineKeyboardBuilder()
    if status == "pending":
        kb.button(text="⏳ Запит вже надіслано", callback_data="noop")
    else:
        kb.button(text="📇 Надіслати запит на контакт", callback_data=f"contact:request:{owner}:lot:{lot_id}")
    kb.button(text="❌ Скасувати", callback_data="noop")
    kb.adjust(1)

    msg = (
        f"📇 <b>Щоб писати {company}</b> ({role}), спочатку надішліть запит на контакт.\n\n"
        f"Після підтвердження ви отримаєте повні контактні дані і зможете спілкуватися."
        if status != "pending" else
        f"⏳ Ви вже надіслали запит до <b>{company}</b>. Очікуйте підтвердження."
    )
    await cb.message.answer(msg, reply_markup=kb.as_markup())
    await cb.answer()


# ══════════════════════ НАДІСЛАТИ ЗАПИТ НА КОНТАКТ ══════════════════════

@router.callback_query(F.data.startswith("contact:request:"))
async def send_contact_request(cb: CallbackQuery):
    await _ensure_tables()
    parts = cb.data.split(":")
    to_user_id = int(parts[2])
    # lot_id опційний (contact:request:{uid}:lot:{lid})
    lot_id = int(parts[4]) if len(parts) > 4 else None

    from_id = await _get_user_id(cb.from_user.id)
    if not from_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    # Перевіряємо чи вже є
    status = await _contact_status(from_id, to_user_id)
    if status == "accepted":
        await cb.answer("Ви вже в контактах ✅", show_alert=True)
        return
    if status == "pending":
        await cb.answer("Запит вже надіслано ⏳", show_alert=True)
        return

    # Створюємо запит
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO contacts(user_id,contact_user_id,status) VALUES(?,?,'pending')",
            (from_id, to_user_id)
        )
        await db.commit()

    # Отримуємо дані відправника для картки
    from_info = await _get_user_full(from_id)
    to_tg = await _get_telegram_id(to_user_id)

    if to_tg:
        try:
            # Надсилаємо картку контакту + кнопки прийняти/відхилити
            await _send_contact_card(
                cb.bot, to_tg,
                from_info or {},
                cb.from_user,
                title=f"📬 <b>Запит на контакт</b>"
            )
            # Кнопки окремим повідомленням
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Прийняти і відкрити чат", callback_data=f"contact:accept:{from_id}")
            kb.button(text="❌ Відхилити", callback_data=f"contact:decline:{from_id}")
            kb.adjust(1)
            await cb.bot.send_message(
                to_tg,
                "Прийняти цей запит?",
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            logger.error(f"Помилка надсилання запиту контакту: {e}")

    try:
        await cb.message.edit_text(
            "✅ <b>Запит надіслано!</b>\n\n"
            "Коли людина прийме запит — ви отримаєте її контактні дані і зможете почати спілкування."
        )
    except Exception:
        pass
    await cb.answer("Запит надіслано ✅")


# ══════════════════════ ПРИЙНЯТИ ЗАПИТ ══════════════════════

@router.callback_query(F.data.startswith("contact:accept:"))
async def accept_contact(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    from_user_id = int(cb.data.split(":")[-1])
    my_id = await _get_user_id(cb.from_user.id)
    if not my_id:
        await cb.answer("Помилка", show_alert=True)
        return

    # Приймаємо: оновлюємо запит і створюємо зворотній
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE contacts SET status='accepted' WHERE user_id=? AND contact_user_id=?",
            (from_user_id, my_id)
        )
        await db.execute(
            "INSERT OR REPLACE INTO contacts(user_id,contact_user_id,status) VALUES(?,?,'accepted')",
            (my_id, from_user_id)
        )
        await db.commit()

    # Надсилаємо ініціатору повну картку
    from_tg = await _get_telegram_id(from_user_id)
    my_info = await _get_user_full(my_id)

    if from_tg:
        try:
            await _send_contact_card(
                cb.bot, from_tg,
                my_info or {},
                cb.from_user,
                title="✅ <b>Запит прийнято! Ось контакт:</b>"
            )
            # Кнопка відкрити чат
            session_id = await _get_or_create_session(my_id, from_user_id, None)
            await cb.bot.send_message(
                from_tg,
                "Тепер ви можете спілкуватися в особистому чаті:",
                reply_markup=kb_open_chat(session_id)
            )
        except Exception as e:
            logger.error(f"Помилка надсилання картки: {e}")

    # Тому хто прийняв — надсилаємо картку ініціатора
    from_info = await _get_user_full(from_user_id)
    from_tg_user = None
    if from_tg:
        try:
            from_tg_user_obj = await cb.bot.get_chat(from_tg)
        except Exception:
            from_tg_user_obj = None
    
    if from_info and from_tg:
        # Надсилаємо картку ініціатора тому хто прийняв
        try:
            # Мінімальний proxy-об'єкт для _send_contact_card
            class _U:
                def __init__(self, tg_id, fname, lname, uname):
                    self.first_name = fname
                    self.last_name = lname
                    self.username = uname
            tg_id_init = from_info.get("telegram_id")
            try:
                chat_obj = await cb.bot.get_chat(tg_id_init)
                proxy = _U(tg_id_init, chat_obj.first_name, chat_obj.last_name, chat_obj.username)
            except Exception:
                proxy = _U(tg_id_init, from_info.get("company",""), "", None)
            await _send_contact_card(
                cb.bot, cb.from_user.id,
                from_info,
                proxy,
                title="📇 <b>Контакт доданий:</b>"
            )
        except Exception as e:
            logger.error(f"Помилка картки ініціатора: {e}")

    # Відкриваємо чат тому хто прийняв
    session_id = await _get_or_create_session(my_id, from_user_id, None)
    try:
        await cb.message.edit_text("✅ Контакт прийнято!")
    except Exception:
        pass
    await cb.message.answer(
        "💬 Чат відкрито. Пишіть повідомлення:",
        reply_markup=kb_exit_chat()
    )
    await state.update_data(chat_session_id=session_id)
    await state.set_state(ChatState.chatting)
    await cb.answer("Контакт прийнято ✅")


# ══════════════════════ ВІДХИЛИТИ ЗАПИТ ══════════════════════

@router.callback_query(F.data.startswith("contact:decline:"))
async def decline_contact(cb: CallbackQuery):
    from_user_id = int(cb.data.split(":")[-1])
    my_id = await _get_user_id(cb.from_user.id)
    if not my_id:
        await cb.answer("Помилка", show_alert=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM contacts WHERE user_id=? AND contact_user_id=?",
            (from_user_id, my_id)
        )
        await db.commit()

    try:
        await cb.message.edit_text("❌ Запит відхилено.")
    except Exception:
        pass
    await cb.answer("Відхилено")


# ══════════════════════ NOOP ══════════════════════

@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


# ══════════════════════ НАДІСЛАТИ СВІЙ КОНТАКТ У ЧАТ ══════════════════════

@router.callback_query(F.data == "chat:send_contact")
async def send_my_contact_in_chat(cb: CallbackQuery, state: FSMContext):
    """Надсилає співрозмовнику свою картку контакту"""
    data = await state.get_data()
    session_id = data.get("chat_session_id")
    if not session_id:
        await cb.answer("Спочатку відкрийте чат", show_alert=True)
        return

    my_id = await _get_user_id(cb.from_user.id)
    if not my_id:
        await cb.answer("Помилка", show_alert=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user1_id,user2_id FROM chat_sessions WHERE id=?", (session_id,))
        sess = await cur.fetchone()

    if not sess:
        await cb.answer("Чат не знайдено", show_alert=True)
        return

    other_id = sess["user2_id"] if sess["user1_id"] == my_id else sess["user1_id"]
    other_tg = await _get_telegram_id(other_id)
    my_info = await _get_user_full(my_id)

    if other_tg:
        try:
            await _send_contact_card(
                cb.bot, other_tg,
                my_info or {},
                cb.from_user,
                title="📇 <b>Контакт від співрозмовника:</b>"
            )
        except Exception as e:
            logger.error(f"Помилка надсилання контакту: {e}")

    await cb.answer("Контакт надіслано ✅")


# ══════════════════════ ВИЙТИ З ЧАТУ ══════════════════════

@router.callback_query(F.data == "chat:exit")
async def exit_chat_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    raw = os.getenv("ADMIN_IDS", "")
    is_adm = str(cb.from_user.id) in raw
    await cb.message.answer("Вийшли з чату ✅", reply_markup=main_menu(is_admin=is_adm))
    await cb.answer()


@router.message(ChatState.chatting, F.text == "❌ Вийти з чату")
async def exit_chat_btn(message: Message, state: FSMContext):
    await state.clear()
    raw = os.getenv("ADMIN_IDS", "")
    is_adm = str(message.from_user.id) in raw
    await message.answer("Вийшли з чату ✅", reply_markup=main_menu(is_admin=is_adm))


# ══════════════════════ ПЕРЕСИЛАННЯ ПОВІДОМЛЕНЬ ══════════════════════

@router.message(ChatState.chatting)
async def relay_message(message: Message, state: FSMContext):
    """Пересилає будь-яке повідомлення (текст/фото/файл/голос) співрозмовнику"""
    data = await state.get_data()
    session_id = data.get("chat_session_id")
    if not session_id:
        await state.clear()
        await message.answer("Чат не знайдено. Поверніться до меню.")
        return

    sender_id = await _get_user_id(message.from_user.id)
    if not sender_id:
        await state.clear()
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT user1_id,user2_id FROM chat_sessions WHERE id=? AND status='active'",
            (session_id,)
        )
        sess = await cur.fetchone()

    if not sess:
        await state.clear()
        await message.answer("Чат завершено.")
        return

    other_id = sess["user2_id"] if sess["user1_id"] == sender_id else sess["user1_id"]
    other_tg = await _get_telegram_id(other_id)

    # Зберігаємо текст в БД
    content = message.text or message.caption or "[медіа]"
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO chat_messages(session_id,sender_user_id,content) VALUES(?,?,?)",
            (session_id, sender_id, content)
        )
        await db.execute(
            "UPDATE chat_sessions SET updated_at=datetime('now') WHERE id=?",
            (session_id,)
        )
        await db.commit()

    if not other_tg:
        await message.answer("⚠️ Не вдалося надіслати — співрозмовника не знайдено.")
        return

    # Пересилаємо повідомлення у будь-якому форматі
    try:
        me = message.from_user
        sender_label = f"💬 <b>{me.first_name or 'Користувач'}</b>"
        if me.username:
            sender_label += f" (@{me.username})"

        if message.text:
            await message.bot.send_message(
                other_tg,
                f"{sender_label}:\n\n{message.text}"
            )
        elif message.photo:
            await message.bot.send_photo(
                other_tg,
                message.photo[-1].file_id,
                caption=f"{sender_label}:\n\n{message.caption or ''}"
            )
        elif message.document:
            await message.bot.send_document(
                other_tg,
                message.document.file_id,
                caption=f"{sender_label}:\n\n{message.caption or ''}"
            )
        elif message.voice:
            await message.bot.send_voice(
                other_tg,
                message.voice.file_id,
                caption=sender_label
            )
        elif message.video:
            await message.bot.send_video(
                other_tg,
                message.video.file_id,
                caption=f"{sender_label}:\n\n{message.caption or ''}"
            )
        elif message.sticker:
            await message.bot.send_sticker(other_tg, message.sticker.file_id)
        else:
            await message.bot.forward_message(other_tg, message.chat.id, message.message_id)

        await message.answer("✅")
    except Exception as e:
        logger.error(f"Помилка пересилання: {e}")
        await message.answer("⚠️ Не вдалося надіслати повідомлення.")
