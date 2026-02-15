from __future__ import annotations

import os
import logging
from typing import Optional

import aiosqlite
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.bot.keyboards.main import main_menu

logger = logging.getLogger(__name__)
router = Router()

DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db")

class ChatState(StatesGroup):
    chatting = State()

def kb_chat_controls():
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ Вийти з чату")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def kb_open_chat(session_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Відкрити чат", callback_data=f"chat:open:{session_id}")
    kb.adjust(1)
    return kb.as_markup()

async def _ensure_tables():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                lot_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        # Таблиця контактів
        await db.execute(
            """CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                contact_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, contact_user_id)
            )"""
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_u1 ON chat_sessions(user1_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_u2 ON chat_sessions(user2_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_sess ON chat_messages(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_contacts_contact ON contacts(contact_user_id)")
        await db.commit()

async def _check_contacts(user1_id: int, user2_id: int) -> tuple[bool, str]:
    """
    Перевіряє чи користувачі є в контактах один у одного
    Повертає: (є_в_контактах, статус)
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Перевіряємо чи user1 додав user2
        cur = await db.execute(
            "SELECT status FROM contacts WHERE user_id=? AND contact_user_id=?",
            (user1_id, user2_id)
        )
        row = await cur.fetchone()
        if row and row["status"] == "accepted":
            return True, "accepted"
        elif row and row["status"] == "pending":
            return False, "pending"
        return False, "none"

async def _add_contact_request(from_user_id: int, to_user_id: int) -> bool:
    """Створює запит на додавання в контакти.

    Повертає True, якщо запит створено вперше (INSERT), і False, якщо такий запис вже існував.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO contacts(user_id, contact_user_id, status) VALUES(?, ?, 'pending')",
            (from_user_id, to_user_id),
        )
        await db.commit()
        # rowcount = 1 тільки якщо реально вставили рядок
        try:
            return (cur.rowcount or 0) > 0
        except Exception:
            # запасний варіант
            return True

async def _accept_contact(user_id: int, contact_user_id: int):
    """Приймає запит на додавання в контакти"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Оновлюємо статус запиту від contact_user_id до user_id
        await db.execute(
            "UPDATE contacts SET status='accepted' WHERE user_id=? AND contact_user_id=?",
            (contact_user_id, user_id)
        )
        # Додаємо зворотний зв'язок (взаємні контакти)
        try:
            await db.execute(
                "INSERT INTO contacts(user_id, contact_user_id, status) VALUES(?, ?, 'accepted')",
                (user_id, contact_user_id)
            )
        except:
            # Якщо вже є - оновлюємо
            await db.execute(
                "UPDATE contacts SET status='accepted' WHERE user_id=? AND contact_user_id=?",
                (user_id, contact_user_id)
            )
        await db.commit()

async def _get_user_telegram_id(user_id: int) -> Optional[int]:
    """Отримує telegram_id користувача по user_id"""
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def _get_user_info(user_id: int) -> Optional[dict]:
    """Отримує інформацію про користувача"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, telegram_id, full_name, username, company FROM users WHERE id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        return None

async def _get_user_id(telegram_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def _get_lot_owner_user_id(lot_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT owner_user_id FROM lots WHERE id=?", (lot_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def _get_or_create_session(user1_id: int, user2_id: int, lot_id: int | None):
    # normalize order to avoid duplicates
    a, b = sorted([user1_id, user2_id])
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id FROM chat_sessions
                 WHERE user1_id=? AND user2_id=? AND COALESCE(lot_id,0)=COALESCE(?,0)
                 AND status='active'""",
            (a, b, lot_id),
        )
        row = await cur.fetchone()
        if row:
            return row["id"]
        cur = await db.execute(
            "INSERT INTO chat_sessions(user1_id, user2_id, lot_id) VALUES(?,?,?)",
            (a, b, lot_id),
        )
        await db.commit()
        return cur.lastrowid

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
            """SELECT id, user1_id, user2_id, lot_id, status, created_at
                 FROM chat_sessions
                 WHERE (user1_id=? OR user2_id=?)
                 ORDER BY id DESC LIMIT 20""",
            (user_id, user_id),
        )
        rows = await cur.fetchall()

    if not rows:
        await message.answer("💬 У вас ще немає чатів. Відкрийте лот у Маркеті і натисніть «💬 Написати».")
        return

    await message.answer("💬 <b>Мої чати</b> (останні 20):")
    for r in rows:
        await message.answer(
            f"Чат #{r['id']} • лот: {r['lot_id'] or '—'} • статус: {r['status']}",
            reply_markup=kb_open_chat(r["id"]),
        )


@router.message(F.text == "📇 Мої контакти")
async def my_contacts(message: Message):
    """Показує список контактів користувача"""
    await _ensure_tables()
    user_id = await _get_user_id(message.from_user.id)
    
    if not user_id:
        await message.answer("Спочатку пройдіть реєстрацію: /start")
        return
    
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            
            # Отримуємо прийняті контакти
            cur = await db.execute(
                """SELECT c.contact_user_id, u.full_name, u.username, u.company, u.telegram_id, u.phone
                   FROM contacts c
                   JOIN users u ON c.contact_user_id = u.id
                   WHERE c.user_id = ? AND c.status = 'accepted'
                   ORDER BY c.created_at DESC
                   LIMIT 20""",
                (user_id,)
            )
            accepted = await cur.fetchall()
            
            # Отримуємо очікувані запити (які я надіслав)
            cur = await db.execute(
                """SELECT c.contact_user_id, u.full_name, u.username, u.company
                   FROM contacts c
                   JOIN users u ON c.contact_user_id = u.id
                   WHERE c.user_id = ? AND c.status = 'pending'
                   ORDER BY c.created_at DESC
                   LIMIT 10""",
                (user_id,)
            )
            pending_sent = await cur.fetchall()
            
            # Отримуємо вхідні запити (які мені надіслали)
            cur = await db.execute(
                """SELECT c.user_id, u.full_name, u.username, u.company
                   FROM contacts c
                   JOIN users u ON c.user_id = u.id
                   WHERE c.contact_user_id = ? AND c.status = 'pending'
                   ORDER BY c.created_at DESC
                   LIMIT 10""",
                (user_id,)
            )
            pending_received = await cur.fetchall()
        
        # Статистика
        total_contacts = len(accepted)
        pending_count = len(pending_sent)
        requests_count = len(pending_received)
        
        header = (
            f"📇 <b>Мої контакти</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"✅ Контактів: {total_contacts}\n"
            f"⏳ Очікують: {pending_count}\n"
            f"📬 Запити: {requests_count}\n"
        )
        
        await message.answer(header)
        
        # Показуємо контакти
        if accepted:
            await message.answer("✅ <b>Мої контакти:</b>\n")
            
            for idx, contact in enumerate(accepted, 1):
                name = contact["full_name"] or "Без імені"

                # Username / нікнейм для швидкого написання
                uname = (contact["username"] or "").strip().lstrip("@")
                username_line = f"\\n👤 @{uname}" if uname else ""

                # Якщо немає username — даємо прямий клік-профіль через telegram_id (працює у більшості клієнтів)
                try:
                    tg_id = contact["telegram_id"]
                except Exception:
                    tg_id = None
                tg_link_line = f"\\n🔗 <a href=\"tg://user?id={tg_id}\">Відкрити профіль</a>" if (not uname and tg_id) else ""

                company = f"\\n🏢 {contact['company']}" if contact['company'] else ""

                # Перевіряємо чи є поле phone
                try:
                    phone = f"\\n📱 {contact['phone']}" if contact['phone'] else ""
                except (KeyError, IndexError):
                    phone = ""

                text = f"{idx}. <b>{name}</b>{username_line}{tg_link_line}{company}{phone}"

                # Кнопки
                kb = InlineKeyboardBuilder()
                kb.button(text="💬 Написати", callback_data=f"contact:chat:{contact['contact_user_id']}")

                if uname:
                    kb.button(text="👤 Профіль", url=f"https://t.me/{uname}")
                elif tg_id:
                    kb.button(text="👤 Профіль", url=f"tg://user?id={tg_id}")

                kb.adjust(2)

                await message.answer(text, reply_markup=kb.as_markup())

        else:
            await message.answer(
                "У вас ще немає підтверджених контактів.\n\n"
                "💡 <i>Додайте контакти через лоти в Маркеті</i>"
            )
        
        # Очікувані запити
        if pending_sent:
            text = "⏳ <b>Очікують підтвердження:</b>\n\n"
            for contact in pending_sent:
                name = contact["full_name"] or "Без імені"
                username = f" @{contact['username']}" if contact["username"] else ""
                company = f" • {contact['company']}" if contact['company'] else ""
                text += f"• <b>{name}</b>{username}{company}\n"
            
            await message.answer(text)
        
        # Вхідні запити
        if pending_received:
            await message.answer("📬 <b>Вхідні запити:</b>")
            for contact in pending_received:
                user_id_req = contact["user_id"]
                name = contact["full_name"] or "Без імені"
                username = f" @{contact['username']}" if contact["username"] else ""
                company = f"\n🏢 {contact['company']}" if contact['company'] else ""
                
                text = f"👤 <b>{name}</b>{username}{company}\n\nХоче додати вас в контакти"
                
                kb = InlineKeyboardBuilder()
                kb.button(text="✅ Прийняти", callback_data=f"contact:accept:{user_id_req}")
                kb.button(text="❌ Відхилити", callback_data=f"contact:decline:{user_id_req}")
                kb.adjust(2)
                
                await message.answer(text, reply_markup=kb.as_markup())
    
    except Exception as e:
        logger.error(f"Помилка в my_contacts: {e}")
        await message.answer(f"❌ Помилка: {e}\n\nСпробуйте ще раз або зверніться до адміністратора.")

@router.callback_query(F.data.startswith("contact:chat:"))
async def open_chat_with_contact(cb: CallbackQuery, state: FSMContext):
    """Відкриває чат з контактом"""
    await _ensure_tables()
    
    contact_user_id = int(cb.data.split(":")[-1])
    my_user_id = await _get_user_id(cb.from_user.id)
    
    if not my_user_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return
    
    # Створюємо або отримуємо сесію
    try:
        session_id = await _get_or_create_session(my_user_id, contact_user_id, None)
        
        # Відкриваємо чат
        await state.update_data(chat_session_id=session_id)
        await state.set_state(ChatState.chatting)
        await cb.message.answer(
            "💬 Чат відкрито. Пишіть повідомлення.\n"
            "Для виходу натисніть «❌ Вийти з чату».",
            reply_markup=kb_chat_controls()
        )
        await cb.answer()
    except Exception as e:
        logger.error(f"Помилка відкриття чату: {e}")
        await cb.answer("Помилка відкриття чату", show_alert=True)


@router.callback_query(F.data.startswith("chat:start:lot:"))
async def start_chat_from_lot(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    lot_id = int(cb.data.split(":")[-1])

    me_user_id = await _get_user_id(cb.from_user.id)
    if not me_user_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    owner_user_id = await _get_lot_owner_user_id(lot_id)
    if not owner_user_id:
        await cb.answer("Лот не знайдено", show_alert=True)
        return
    if owner_user_id == me_user_id:
        await cb.answer("Це ваш лот 🙂", show_alert=True)
        return

    # Перевіряємо чи є в контактах
    in_contacts, status = await _check_contacts(me_user_id, owner_user_id)
    
    if not in_contacts:
        # Отримуємо інформацію про власника
        owner_info = await _get_user_info(owner_user_id)
        owner_name = owner_info.get("full_name", "Користувач") if owner_info else "Користувач"
        
        # Створюємо клавіатуру для запиту на додавання
        kb = InlineKeyboardBuilder()
        kb.button(
            text="📇 Додати в контакти", 
            callback_data=f"contact:add:{owner_user_id}:lot:{lot_id}"
        )
        kb.button(text="❌ Скасувати", callback_data="contact:cancel")
        kb.adjust(1)
        
        if status == "pending":
            await cb.message.answer(
                f"⏳ Ви вже надіслали запит на додавання в контакти користувачу <b>{owner_name}</b>.\n\n"
                f"Очікуйте підтвердження, після чого зможете писати в особисті повідомлення.",
                reply_markup=kb.as_markup()
            )
        else:
            await cb.message.answer(
                f"📇 Щоб почати листування з <b>{owner_name}</b>, спочатку додайте його в контакти.\n\n"
                f"Після підтвердження ви зможете писати в особисті повідомлення.",
                reply_markup=kb.as_markup()
            )
        await cb.answer()
        return

    # Якщо вже в контактах - створюємо чат
    session_id = await _get_or_create_session(me_user_id, owner_user_id, lot_id)
    await cb.message.answer(f"✅ Чат створено. Відкриваю…", reply_markup=kb_open_chat(session_id))
    await cb.answer()

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
            "SELECT id, user1_id, user2_id, status FROM chat_sessions WHERE id=?",
            (session_id,),
        )
        sess = await cur.fetchone()

    if not sess or sess["status"] != "active":
        await cb.answer("Чат не активний", show_alert=True)
        return
    if user_id not in (sess["user1_id"], sess["user2_id"]):
        await cb.answer("Немає доступу", show_alert=True)
        return

    await state.update_data(chat_session_id=session_id)
    await state.set_state(ChatState.chatting)
    await cb.message.answer("💬 Ви в чаті. Пишіть повідомлення. Для виходу натисніть «❌ Вийти з чату».", reply_markup=kb_chat_controls())
    await cb.answer()

@router.message(ChatState.chatting, F.text == "❌ Вийти з чату")
async def exit_chat(message: Message, state: FSMContext):
    await state.clear()
    # визначаємо адмін чи ні для меню
    is_admin = False
    raw = os.getenv("ADMIN_IDS", "")
    if raw and str(message.from_user.id) in raw:
        is_admin = True
    await message.answer("Вийшли з чату ✅", reply_markup=main_menu(is_admin=is_admin))

@router.message(ChatState.chatting)
async def chat_message(message: Message, state: FSMContext):
    data = await state.get_data()
    session_id = data.get("chat_session_id")
    if not session_id:
        await state.clear()
        await message.answer("Чат не знайдено. Спробуйте ще раз.", reply_markup=main_menu())
        return

    sender_user_id = await _get_user_id(message.from_user.id)
    if not sender_user_id:
        await state.clear()
        await message.answer("Спочатку /start", reply_markup=main_menu())
        return

    text = (message.text or "").strip()
    if not text:
        return

    # Зберігаємо повідомлення
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        
        # Отримуємо інфо про сесію
        sess = await db.execute(
            "SELECT user1_id, user2_id FROM chat_sessions WHERE id=?",
            (session_id,)
        ).fetchone()
        
        if not sess:
            await state.clear()
            await message.answer("Чат не знайдено.", reply_markup=main_menu())
            return
        
        # Визначаємо отримувача
        recipient_user_id = sess["user2_id"] if sess["user1_id"] == sender_user_id else sess["user1_id"]
        
        # Зберігаємо повідомлення в БД
        await db.execute(
            "INSERT INTO chat_messages(session_id, sender_user_id, content) VALUES(?,?,?)",
            (session_id, sender_user_id, text),
        )
        await db.commit()

    # Підтверджуємо відправнику
    await message.answer("✅ Надіслано")
    
    # Пересилаємо отримувачу
    try:
        recipient_telegram_id = await _get_user_telegram_id(recipient_user_id)
        if recipient_telegram_id:
            sender_info = await _get_user_info(sender_user_id)
            sender_name = sender_info.get("full_name", "Користувач") if sender_info else "Користувач"
            
            # Відправляємо повідомлення отримувачу
            await message.bot.send_message(
                recipient_telegram_id,
                f"💬 <b>Нове повідомлення від {sender_name}</b>\n\n"
                f"{text}\n\n"
                f"<i>Для відповіді відкрийте чат через «💬 Мої чати»</i>"
            )
    except Exception as e:
        logger.error(f"Не вдалося надіслати повідомлення отримувачу: {e}")


# ========== ОБРОБНИКИ КОНТАКТІВ ==========

@router.callback_query(F.data.startswith("contact:add:"))
async def add_contact_request(cb: CallbackQuery):
    """Надсилає запит на додавання в контакти"""
    await _ensure_tables()
    
    # Парсимо callback_data: contact:add:{user_id}:lot:{lot_id}
    parts = cb.data.split(":")
    to_user_id = int(parts[2])
    lot_id = int(parts[4]) if len(parts) > 4 else None
    
    from_user_id = await _get_user_id(cb.from_user.id)
    if not from_user_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return
    
    # Додаємо запит (без дублювань)
    created = await _add_contact_request(from_user_id, to_user_id)

    if not created:
        # Запит вже існує (pending/accepted) — не спамимо повідомленнями
        await cb.answer("Запит вже надіслано ✅", show_alert=True)
        try:
            await cb.message.edit_text(
                "⏳ Запит вже був надісланий раніше.\n\n"
                "Очікуйте підтвердження, після чого зможете почати листування."
            )
        except Exception:
            pass
        return

    # Отримуємо telegram_id отримувача для відправки повідомлення
    to_telegram_id = await _get_user_telegram_id(to_user_id)
    from_info = await _get_user_info(from_user_id)
    from_name = from_info.get("full_name", "Користувач") if from_info else "Користувач"
    
    if to_telegram_id:
        try:
            # Відправляємо повідомлення отримувачу
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Прийняти", 
                callback_data=f"contact:accept:{from_user_id}"
            )
            kb.button(
                text="❌ Відхилити", 
                callback_data=f"contact:decline:{from_user_id}"
            )
            kb.adjust(2)
            
            await cb.bot.send_message(
                to_telegram_id,
                f"📬 <b>Новий запит в контакти!</b>\n\n"
                f"<b>{from_name}</b> хоче додати вас у контакти.\n\n"
                f"Після підтвердження ви зможете обмінюватися повідомленнями.",
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            logger.error(f"Не вдалося надіслати повідомлення користувачу {to_telegram_id}: {e}")
    
    await cb.message.edit_text(
        f"✅ Запит надіслано!\n\n"
        f"Очікуйте підтвердження від користувача.\n"
        f"Коли він прийме запит, ви зможете почати листування."
    )
    await cb.answer("Запит надіслано ✅")


@router.callback_query(F.data.startswith("contact:accept:"))
async def accept_contact_request(cb: CallbackQuery):
    """Приймає запит на додавання в контакти"""
    await _ensure_tables()
    
    contact_user_id = int(cb.data.split(":")[2])
    my_user_id = await _get_user_id(cb.from_user.id)
    
    if not my_user_id:
        await cb.answer("Помилка", show_alert=True)
        return
    
    # Приймаємо контакт
    await _accept_contact(my_user_id, contact_user_id)
    
    # Повідомляємо ініціатора
    contact_telegram_id = await _get_user_telegram_id(contact_user_id)
    my_info = await _get_user_info(my_user_id)
    my_name = my_info.get("full_name", "Користувач") if my_info else "Користувач"
    
    if contact_telegram_id:
        try:
            await cb.bot.send_message(
                contact_telegram_id,
                f"✅ <b>{my_name}</b> прийняв ваш запит в контакти!\n\n"
                f"Тепер ви можете писати один одному в особисті повідомлення."
            )
        except Exception as e:
            logger.error(f"Не вдалося надіслати повідомлення: {e}")
    
    contact_info = await _get_user_info(contact_user_id)
    contact_name = contact_info.get("full_name", "Користувач") if contact_info else "Користувач"
    
    await cb.message.edit_text(
        f"✅ Ви прийняли запит від <b>{contact_name}</b>!\n\n"
        f"Тепер ви можете обмінюватися повідомленнями."
    )
    await cb.answer("Контакт додано ✅")


@router.callback_query(F.data.startswith("contact:decline:"))
async def decline_contact_request(cb: CallbackQuery):
    """Відхиляє запит на додавання в контакти"""
    await _ensure_tables()
    
    contact_user_id = int(cb.data.split(":")[2])
    my_user_id = await _get_user_id(cb.from_user.id)
    
    if not my_user_id:
        await cb.answer("Помилка", show_alert=True)
        return
    
    # Видаляємо запит
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM contacts WHERE user_id=? AND contact_user_id=?",
            (contact_user_id, my_user_id)
        )
        await db.commit()
    
    contact_info = await _get_user_info(contact_user_id)
    contact_name = contact_info.get("full_name", "Користувач") if contact_info else "Користувач"
    
    await cb.message.edit_text(f"❌ Ви відхилили запит від <b>{contact_name}</b>.")
    await cb.answer("Запит відхилено")


@router.callback_query(F.data == "contact:cancel")
async def cancel_contact_request(cb: CallbackQuery):
    """Скасовує дію з контактами"""
    await cb.message.edit_text("❌ Скасовано")
    await cb.answer()
