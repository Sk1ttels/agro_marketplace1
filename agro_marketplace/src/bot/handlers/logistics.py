"""Логістика: транспорт і заявки на перевезення (MVP).

Працює з aiogram 3.x + aiosqlite.
Фікси:
- '-' у коментарі більше не ламає флоу
- created_at/updated_at завжди заповнюються (щоб не падало на NOT NULL)
- виправлені відступи та блоки async with
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import aiosqlite
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


router = Router()
DB_FILE = "agro_bot.db"

# --- Довідник областей (шаблон) ---
OBLASTS = [
    "Вінницька", "Волинська", "Дніпропетровська", "Донецька", "Житомирська",
    "Закарпатська", "Запорізька", "Івано-Франківська", "Київська", "Кіровоградська",
    "Луганська", "Львівська", "Миколаївська", "Одеська", "Полтавська", "Рівненська",
    "Сумська", "Тернопільська", "Харківська", "Херсонська", "Хмельницька", "Черкаська",
    "Чернівецька", "Чернігівська",
]

def kb_oblasts() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for o in OBLASTS:
        kb.button(text=o)
    kb.button(text="⬅️ Назад")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)



class CreateVehicle(StatesGroup):
    body_type = State()
    capacity = State()
    count_units = State()
    base_region = State()  # область (з шаблону)
    base_city = State()    # населений пункт
    comment = State()


class CreateShipment(StatesGroup):
    cargo_type = State()
    volume = State()
    from_region = State()  # область (з шаблону)
    from_city = State()    # населений пункт
    to_region = State()    # область (з шаблону)
    to_city = State()      # населений пункт
    comment = State()


def kb_logistics_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚚 Логістика")
    kb.button(text="➕ Додати авто")
    kb.button(text="📦 Створити заявку")
    kb.button(text="🚛 Транспорт")
    kb.button(text="📨 Заявки")
    kb.button(text="⬅️ Назад")
    kb.adjust(2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def kb_vehicle_type():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌾 Зерновоз", callback_data="veh:type:grain")
    kb.button(text="🪨 Самоскид", callback_data="veh:type:tipper")
    kb.button(text="🧵 Тент", callback_data="veh:type:tarp")
    kb.adjust(2, 1)
    return kb.as_markup()


async def _ensure_tables():
    """Створює таблиці, якщо їх ще немає.

    ВАЖЛИВО: якщо у твоїй БД updated_at зроблено NOT NULL без DEFAULT,
    то це НЕ виправляється CREATE TABLE. Тому ми в коді завжди передаємо updated_at в INSERT/UPDATE.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                    owner_user_id INTEGER NOT NULL,
                                                    body_type TEXT NOT NULL,
                                                    capacity_tons REAL NOT NULL,
                                                    count_units INTEGER NOT NULL DEFAULT 1,
                                                    base_region TEXT NOT NULL,
                                                    work_regions TEXT,
                                                    status TEXT NOT NULL DEFAULT 'available',
                                                    available_from TEXT,
                                                    comment TEXT,
                                                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                                                    updated_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shipments (
                                                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                     creator_user_id INTEGER NOT NULL,
                                                     cargo_type TEXT NOT NULL,
                                                     volume_tons REAL NOT NULL,
                                                     from_region TEXT NOT NULL,
                                                     from_location TEXT,
                                                     to_region TEXT NOT NULL,
                                                     to_location TEXT,
                                                     date_from TEXT,
                                                     date_to TEXT,
                                                     required_body_types TEXT,
                                                     comment TEXT,
                                                     status TEXT NOT NULL DEFAULT 'active',
                                                     created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                                                     updated_at TEXT
            )
            """
        )
        await db.commit()

async def _ensure_chat_tables():
    """Таблиці анонімного чату (використовує app/handlers/chat.py)."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                         user1_id INTEGER NOT NULL,
                                                         user2_id INTEGER NOT NULL,
                                                         lot_id INTEGER,
                                                         offer_id INTEGER,
                                                         status TEXT NOT NULL DEFAULT 'active',
                                                         created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                                                         updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                         session_id INTEGER NOT NULL,
                                                         sender_user_id INTEGER NOT NULL,
                                                         message_type TEXT NOT NULL,
                                                         content TEXT NOT NULL,
                                                         created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_requests (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            session_id INTEGER NOT NULL,
                                                            requester_user_id INTEGER NOT NULL,
                                                            status TEXT NOT NULL DEFAULT 'pending',
                                                            created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


def kb_open_chat(session_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Відкрити чат", callback_data=f"chat:open:{session_id}")
    kb.adjust(1)
    return kb.as_markup()


async def _get_user_id_by_tg(tg_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (tg_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else None


async def _get_tg_by_user_id(user_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else None


async def _get_shipment_creator(shipment_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT creator_user_id FROM shipments WHERE id=?", (shipment_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else None


async def _get_or_create_chat_session(u1: int, u2: int, shipment_id: int) -> int:
    """Створюємо чат між двома користувачами по заявці (shipment_id пишемо в offer_id)."""
    a, b = (u1, u2) if u1 < u2 else (u2, u1)
    now = datetime.now().isoformat(timespec="seconds")

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            """
            SELECT id FROM chat_sessions
            WHERE status='active'
              AND user1_id=? AND user2_id=?
              AND offer_id=?
              AND lot_id IS NULL
            ORDER BY id DESC
                LIMIT 1
            """,
            (a, b, int(shipment_id)),
        )
        row = await cur.fetchone()
        if row:
            return int(row[0])

        cur = await db.execute(
            """
            INSERT INTO chat_sessions (user1_id, user2_id, lot_id, offer_id, status, created_at, updated_at)
            VALUES (?, ?, NULL, ?, 'active', ?, ?)
            """,
            (a, b, int(shipment_id), now, now),
        )
        await db.commit()
        return int(cur.lastrowid)


@router.callback_query(F.data.startswith("log:chat:ship:"))
async def start_chat_from_shipment(cb: CallbackQuery):
    """Кнопка '💬 Звʼязатися' під заявкою/транспортом."""
    await _ensure_chat_tables()

    try:
        shipment_id = int(cb.data.split(":")[-1])
    except Exception:
        await cb.answer("Помилка ID", show_alert=True)
        return

    me_user_id = await _get_user_id_by_tg(cb.from_user.id)
    if not me_user_id:
        await cb.answer("Спочатку /start", show_alert=True)
        return

    owner_user_id = await _get_shipment_creator(shipment_id)
    if not owner_user_id:
        await cb.answer("Заявку не знайдено", show_alert=True)
        return
    if int(owner_user_id) == int(me_user_id):
        await cb.answer("Це ваша заявка", show_alert=True)
        return

    session_id = await _get_or_create_chat_session(me_user_id, owner_user_id, shipment_id)

    # Відповідаємо тому, хто натиснув
    await cb.message.answer(
        f"💬 Створено чат по заявці <code>{shipment_id}</code>\nНатисніть, щоб відкрити:",
        reply_markup=kb_open_chat(session_id),
    )

    # Сповіщаємо автора заявки
    owner_tg = await _get_tg_by_user_id(owner_user_id)
    if owner_tg:
        await cb.bot.send_message(
            owner_tg,
            f"💬 Хтось хоче звʼязатися по вашій заявці <code>{shipment_id}</code>.\nНатисніть, щоб відкрити чат:",
            reply_markup=kb_open_chat(session_id),
        )

    await cb.answer("Чат створено ✅")

def kb_shipment_chat(shipment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Звʼязатися", callback_data=f"log:chat:ship:{shipment_id}")
    return kb.as_markup()



async def _get_user_id(telegram_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else None


def _vehicle_text(row: aiosqlite.Row) -> str:
    bt = {"grain": "🌾 Зерновоз", "tipper": "🪨 Самоскид", "tarp": "🧵 Тент"}.get(row["body_type"], row["body_type"])
    return (
        f"🚛 <b>{bt}</b> • 🆔 <code>{row['id']}</code>\n"
        f"⚖️ Вантажопідйомність: <b>{row['capacity_tons']} т</b> • К-сть: <b>{row['count_units']}</b>\n"
        f"📍 База: <b>{row['base_region']}</b>\n"
        f"📝 {row['comment'] or '—'}\n"
    )


def _shipment_text(row: aiosqlite.Row) -> str:
    return (
        f"📦 <b>Заявка</b> • 🆔 <code>{row['id']}</code>\n"
        f"🚚 Вантаж: <b>{row['cargo_type']}</b> • {row['volume_tons']} т\n"
        f"📍 {row['from_region']} → {row['to_region']}\n"
        f"📝 {row['comment'] or '—'}\n"
    )


def _clean_optional_text(txt: str) -> Optional[str]:
    t = (txt or "").strip()
    if t == "-" or t == "—":
        return None


async def _get_telegram_id_by_user_id(user_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT telegram_id FROM users WHERE id=?", (int(user_id),))
        row = await cur.fetchone()
        if not row:
            return None
        try:
            return int(row["telegram_id"])
        except Exception:
            return None
    return t if t else None


@router.message(F.text == "🚚 Логістика")
async def logistics_menu(message: Message):
    await _ensure_tables()
    await message.answer("🚚 <b>Логістика</b>", reply_markup=kb_logistics_menu())


@router.message(F.text == "➕ Додати авто")
async def add_vehicle(message: Message, state: FSMContext):
    await _ensure_tables()
    await state.clear()
    await state.set_state(CreateVehicle.body_type)
    await message.answer("Оберіть тип кузова:", reply_markup=kb_vehicle_type())


@router.callback_query(F.data.startswith("veh:type:"))
async def pick_vehicle_type(cb: CallbackQuery, state: FSMContext):
    body = cb.data.split(":")[-1]
    await state.update_data(body_type=body)
    await state.set_state(CreateVehicle.capacity)
    await cb.message.edit_text("Введіть вантажопідйомність (т):")
    await cb.answer()


@router.message(CreateVehicle.capacity)
async def vehicle_capacity(message: Message, state: FSMContext):
    raw = (message.text or "").replace(",", ".").strip()
    try:
        cap = float(raw)
        if cap <= 0:
            raise ValueError
    except Exception:
        await message.answer("Некоректно. Приклад: 22.5")
        return

    await state.update_data(capacity_tons=cap)
    await state.set_state(CreateVehicle.count_units)
    await message.answer("Скільки авто? (1,2,3...)")


@router.message(CreateVehicle.count_units)
async def vehicle_count(message: Message, state: FSMContext):
    try:
        cnt = int((message.text or "").strip())
        if cnt <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введіть ціле число більше 0")
        return

    await state.update_data(count_units=cnt)
    await state.set_state(CreateVehicle.base_region)
    await message.answer("Оберіть базову область:", reply_markup=kb_oblasts())


@router.message(CreateVehicle.base_region)
async def vehicle_base_region(message: Message, state: FSMContext):
    region = (message.text or "").strip()

    if region == "⬅️ Назад":
        await state.clear()
        await message.answer("🚚 Логістика", reply_markup=kb_logistics_menu())
        return

    if region not in OBLASTS:
        await message.answer("Оберіть область кнопкою нижче 👇", reply_markup=kb_oblasts())
        return

    await state.update_data(base_region=region)
    await state.set_state(CreateVehicle.base_city)
    await message.answer("Введіть населений пункт (місто/село):", reply_markup=ReplyKeyboardRemove())


@router.message(CreateVehicle.base_city)
async def vehicle_base_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if len(city) < 2 or len(city) > 60:
        await message.answer("2–60 символів")
        return

    await state.update_data(base_city=city)
    await state.set_state(CreateVehicle.comment)
    await message.answer("Коментар (або '-' щоб пропустити):")


@router.message(CreateVehicle.comment)
async def vehicle_finish(message: Message, state: FSMContext):
    comment = _clean_optional_text(message.text or "")
    data = await state.get_data()

    user_id = await _get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("Спочатку /start", reply_markup=kb_logistics_menu())
        await state.clear()
        return

    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO vehicles (
                owner_user_id, body_type, capacity_tons, count_units, base_region,
                work_regions, status, comment, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'available', ?, ?, ?)
            """,
            (
                user_id,
                data.get("body_type"),
                float(data.get("capacity_tons")),
                int(data.get("count_units")),
                data.get("base_region"),
                json.dumps([data.get("base_region")], ensure_ascii=False),
                comment,
                now,
                now,
            ),
        )
        await db.commit()

    await state.clear()
    await message.answer("✅ Авто додано", reply_markup=kb_logistics_menu())


@router.message(F.text == "📦 Створити заявку")
async def shipment_start(message: Message, state: FSMContext):
    await _ensure_tables()
    await state.clear()
    await state.set_state(CreateShipment.cargo_type)
    await message.answer("Введіть тип вантажу (наприклад: пшениця):", reply_markup=kb_logistics_menu())


@router.message(CreateShipment.cargo_type)
async def shipment_cargo(message: Message, state: FSMContext):
    cargo = (message.text or "").strip()
    if len(cargo) < 2 or len(cargo) > 50:
        await message.answer("2–50 символів")
        return

    await state.update_data(cargo_type=cargo)
    await state.set_state(CreateShipment.volume)
    await message.answer("Вкажіть обсяг (т):")


@router.message(CreateShipment.volume)
async def shipment_volume(message: Message, state: FSMContext):
    raw = (message.text or "").replace(",", ".").strip()
    try:
        vol = float(raw)
        if vol <= 0:
            raise ValueError
    except Exception:
        await message.answer("Некоректно. Приклад: 18 або 18.5")
        return

    await state.update_data(volume_tons=vol)
    await state.set_state(CreateShipment.from_region)
    await message.answer("Оберіть область відправлення:", reply_markup=kb_oblasts())


@router.message(CreateShipment.from_region)
async def shipment_from_region(message: Message, state: FSMContext):
    region = (message.text or "").strip()

    if region == "⬅️ Назад":
        await state.clear()
        await message.answer("🚚 Логістика", reply_markup=kb_logistics_menu())
        return

    if region not in OBLASTS:
        await message.answer("Оберіть область кнопкою нижче 👇", reply_markup=kb_oblasts())
        return

    await state.update_data(from_region=region)
    await state.set_state(CreateShipment.from_city)
    await message.answer("Введіть населений пункт (звідки):", reply_markup=ReplyKeyboardRemove())


@router.message(CreateShipment.from_city)
async def shipment_from_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if len(city) < 2 or len(city) > 60:
        await message.answer("2–60 символів")
        return

    await state.update_data(from_location=city)
    await state.set_state(CreateShipment.to_region)
    await message.answer("Оберіть область призначення:", reply_markup=kb_oblasts())


@router.message(CreateShipment.to_region)
async def shipment_to_region(message: Message, state: FSMContext):
    region = (message.text or "").strip()

    if region == "⬅️ Назад":
        # повертаємось до вибору області відправлення
        await state.set_state(CreateShipment.from_region)
        await message.answer("Оберіть область відправлення:", reply_markup=kb_oblasts())
        return

    if region not in OBLASTS:
        await message.answer("Оберіть область кнопкою нижче 👇", reply_markup=kb_oblasts())
        return

    await state.update_data(to_region=region)
    await state.set_state(CreateShipment.to_city)
    await message.answer("Введіть населений пункт (куди):", reply_markup=ReplyKeyboardRemove())


@router.message(CreateShipment.to_city)
async def shipment_to_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if len(city) < 2 or len(city) > 60:
        await message.answer("2–60 символів")
        return

    await state.update_data(to_location=city)
    await state.set_state(CreateShipment.comment)
    await message.answer("Коментар (або '-' щоб пропустити):")



@router.message(CreateShipment.comment)
async def shipment_finish(message: Message, state: FSMContext):
    comment = _clean_optional_text(message.text or "")
    data = await state.get_data()

    user_id = await _get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("Спочатку /start", reply_markup=kb_logistics_menu())
        await state.clear()
        return

    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO shipments (
                creator_user_id, cargo_type, volume_tons, from_region, from_location, to_region, to_location,
                comment, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                user_id,
                data.get("cargo_type"),
                float(data.get("volume_tons")),
                data.get("from_region"),
                data.get("from_location"),
                data.get("to_region"),
                data.get("to_location"),
                comment,
                now,
                now,
            ),
        )
        await db.commit()

    await state.clear()
    await message.answer("✅ Заявку створено", reply_markup=kb_logistics_menu())


@router.message(F.text == "🚛 Транспорт")
async def list_vehicles(message: Message):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM vehicles WHERE status='available' ORDER BY id DESC LIMIT 20"
        )
        rows = await cur.fetchall()

    if not rows:
        await message.answer("Поки немає доступного транспорту.", reply_markup=kb_logistics_menu())
        return

    await message.answer("🚛 <b>Доступний транспорт</b> (20):", reply_markup=kb_logistics_menu())
    for r in rows[:10]:
        await message.answer(_vehicle_text(r), reply_markup=kb_logistics_menu())


@router.message(F.text == "📨 Заявки")
async def list_shipments(message: Message):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM shipments WHERE status='active' ORDER BY id DESC LIMIT 20"
        )
        rows = await cur.fetchall()

    if not rows:
        await message.answer("Поки немає активних заявок.", reply_markup=kb_logistics_menu())
        return

    await message.answer("📨 <b>Активні заявки</b> (20):", reply_markup=kb_logistics_menu())
    me_uid = await _get_user_id(message.from_user.id)
    for r in rows[:10]:
        mk = kb_shipment_chat(int(r["id"])) if (me_uid and int(r["creator_user_id"]) != int(me_uid)) else None
        await message.answer(_shipment_text(r), reply_markup=mk)
