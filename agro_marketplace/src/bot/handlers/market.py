"""AgroMarket handlers (fixed)

Fixes included:
- No stray top-level awaits (previous file broke with 'await outside function')
- Safe NOT NULL defaults for lots: volume_tons, quality_json, views_count
- Schema compatibility: volume vs volume_tons, quality_json optional
- Back to main: sqlite Row safe (no .get)
- Calculator menu NOT included here (handled in start/main menus elsewhere)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import aiosqlite
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()

DB_FILE = os.getenv("DB_FILE", "agro_bot.db")


# ---------- DB helpers ----------

async def _lots_columns(db: aiosqlite.Connection) -> set[str]:
    cur = await db.execute("PRAGMA table_info(lots)")
    rows = await cur.fetchall()
    return {r[1] for r in rows}


async def _ensure_tables():
    """Create lots table + soft-migrations for older DBs."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS lots (
                                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                owner_user_id INTEGER NOT NULL,
                                                type TEXT NOT NULL,
                                                crop TEXT NOT NULL,
                                                volume_tons REAL NOT NULL DEFAULT 0,
                                                volume REAL,
                                                region TEXT NOT NULL,
                                                location TEXT,
                                                price REAL,
                                                comment TEXT,
                                                quality_json TEXT NOT NULL DEFAULT '{}',
                                                views_count INTEGER NOT NULL DEFAULT 0,
                                                status TEXT NOT NULL DEFAULT 'active',
                                                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                                                updated_at TEXT
            )
            """
        )
        cols = await _lots_columns(db)
        if "volume_tons" not in cols:
            await db.execute("ALTER TABLE lots ADD COLUMN volume_tons REAL DEFAULT 0")
        if "quality_json" not in cols:
            await db.execute("ALTER TABLE lots ADD COLUMN quality_json TEXT DEFAULT '{}'")
        if "views_count" not in cols:
            await db.execute("ALTER TABLE lots ADD COLUMN views_count INTEGER DEFAULT 0")
        await db.commit()


async def get_user_id(telegram_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return row[0] if row else None


def _get_lot_volume(lot) -> float:
    try:
        if hasattr(lot, "keys") and "volume_tons" in lot.keys():
            return float(lot["volume_tons"] or 0)
        if hasattr(lot, "keys") and "volume" in lot.keys():
            return float(lot["volume"] or 0)
        return 0.0
    except Exception:
        return 0.0


# ---------- FSM ----------

class CreateLot(StatesGroup):
    lot_type = State()
    crop = State()
    region = State()
    location = State()
    volume = State()
    price = State()
    comment = State()


# ---------- Constants ----------

REGIONS = [
    "Вінницька","Волинська","Дніпропетровська","Донецька","Житомирська","Закарпатська","Запорізька",
    "Івано-Франківська","Київська","Кіровоградська","Луганська","Львівська","Миколаївська","Одеська",
    "Полтавська","Рівненська","Сумська","Тернопільська","Харківська","Херсонська","Хмельницька",
    "Черкаська","Чернівецька","Чернігівська","м. Київ","Інша",
]

CROPS = [
    ("Пшениця 1кл", "wheat_1"),
    ("Пшениця 2кл", "wheat_2"),
    ("Пшениця 3кл", "wheat_3"),
    ("Пшениця 4кл", "wheat_4"),
    ("Кукурудза", "corn"),
    ("Соняшник", "sunflower"),
    ("Ячмінь", "barley"),
    ("Соя", "soy"),
    ("Горох", "pea"),
    ("Ріпак", "rape"),
    ("Овес", "oat"),
    ("Жито", "rye"),
    ("Інші", "other"),
]

LOCATIONS = [("Елеватор", "elevator"), ("Господарство", "farm")]


# ---------- Keyboards ----------

def kb_market_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="📋 Створити")
    kb.button(text="📂 Мої заявки")
    kb.button(text="💰 Біржові пропозиції")
    kb.button(text="⬅️ Головне меню")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def kb_lot_type():
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Продаж", callback_data="lot:type:sell")
    kb.button(text="📥 Купівля", callback_data="lot:type:buy")
    kb.adjust(2)
    return kb.as_markup()


def kb_crops():
    kb = ReplyKeyboardBuilder()
    for crop_name, _ in CROPS:
        kb.button(text=crop_name)
    kb.button(text="⬅️ Назад")
    kb.adjust(2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def kb_regions():
    kb = ReplyKeyboardBuilder()
    for region in REGIONS:
        kb.button(text=region)
    kb.button(text="⬅️ Назад")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def kb_locations():
    kb = ReplyKeyboardBuilder()
    for loc_name, _ in LOCATIONS:
        kb.button(text=loc_name)
    kb.button(text="⬅️ Назад")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


def kb_skip():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⏭ Пропустити")
    kb.button(text="⬅️ Назад")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def kb_lot_actions(lot_id: int, is_owner: bool):
    kb = InlineKeyboardBuilder()
    if is_owner:
        kb.button(text="❌ Зняти", callback_data=f"lot:delete:{lot_id}")
    else:
        kb.button(text="💬 Написати", callback_data=f"chat:start:lot:{lot_id}")
        kb.button(text="💰 Запропонувати ціну", callback_data=f"offer:make:{lot_id}")
    kb.adjust(2)
    return kb.as_markup()


# ---------- Text formatting ----------

def format_lot_text(lot: dict) -> str:
    lot_type = "📤 Продаж" if lot["type"] == "sell" else "📥 Купівля"
    vol = _get_lot_volume(lot)
    vol_str = f"{int(vol)}т" if vol == int(vol) else f"{vol:.1f}т"
    text = (
        f"{lot_type}\n"
        f"🌾 <b>{lot['crop']}</b>\n"
        f"📦 Обсяг: <b>{vol_str}</b>\n"
        f"📍 {lot['region']}\n"
    )
    if lot.get("location"):
        text += f"📍 Місце: {lot['location']}\n"
    if lot.get("price"):
        try:
            p = float(lot["price"])
            p_str = f"{int(p)}" if p == int(p) else f"{p:.2f}"
        except Exception:
            p_str = str(lot["price"])
        text += f"💰 Ціна: <b>{p_str} грн/т</b>\n"
    else:
        text += "💰 Ціна: <b>Договірна</b>\n"
    if lot.get("comment"):
        text += f"\n💬 {lot['comment']}\n"
    text += f"\n🆔 Заявка №{lot['id']}"
    return text


# ---------- Handlers ----------

@router.message(F.text == "🌾 Маркет")
async def market_menu(message: Message, state: FSMContext):
    await _ensure_tables()
    await state.clear()
    await message.answer("🌾 <b>AgroMarket</b>\n\nОберіть дію:", reply_markup=kb_market_menu())


@router.message(F.text == "📋 Створити")
async def create_lot_start(message: Message, state: FSMContext):
    await _ensure_tables()
    user_id = await get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("❌ Спочатку пройдіть реєстрацію /start")
        return
    await state.set_state(CreateLot.lot_type)
    await message.answer("Оберіть тип заявки:", reply_markup=kb_lot_type())


@router.callback_query(F.data.startswith("lot:type:"))
async def lot_type_selected(cb: CallbackQuery, state: FSMContext):
    lot_type = cb.data.split(":")[-1]
    await state.update_data(lot_type=lot_type)
    await state.set_state(CreateLot.crop)
    await cb.answer()
    await cb.message.answer("Оберіть культуру", reply_markup=kb_crops())


@router.message(CreateLot.crop)
async def lot_crop_selected(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.lot_type)
        await message.answer("Оберіть тип заявки:", reply_markup=kb_lot_type())
        return
    crop = message.text.strip()
    if crop not in [c[0] for c in CROPS]:
        await message.answer("❌ Оберіть культуру з клавіатури")
        return
    await state.update_data(crop=crop)
    await state.set_state(CreateLot.region)
    await message.answer("Оберіть область", reply_markup=kb_regions())


@router.message(CreateLot.region)
async def lot_region_selected(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.crop)
        await message.answer("Оберіть культуру", reply_markup=kb_crops())
        return
    region = message.text.strip()
    if region not in REGIONS:
        await message.answer("❌ Оберіть область з клавіатури")
        return
    await state.update_data(region=region)
    await state.set_state(CreateLot.location)
    await message.answer("Оберіть місце знаходження товару", reply_markup=kb_locations())


@router.message(CreateLot.location)
async def lot_location_selected(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.region)
        await message.answer("Оберіть область", reply_markup=kb_regions())
        return
    location = message.text.strip()
    if location not in [l[0] for l in LOCATIONS]:
        await message.answer("❌ Оберіть місце з клавіатури")
        return
    await state.update_data(location=location)
    await state.set_state(CreateLot.volume)
    await message.answer("Введіть обсяг (у тоннах) або «⏭ Пропустити» (буде 0)", reply_markup=kb_skip())


@router.message(CreateLot.volume)
async def lot_volume_entered(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.location)
        await message.answer("Оберіть місце", reply_markup=kb_locations())
        return
    if message.text == "⏭ Пропустити":
        volume = 0.0
    else:
        try:
            volume = float(message.text.replace(",", ".").replace("т", "").strip())
            if volume < 0:
                raise ValueError
        except Exception:
            await message.answer("❌ Введіть коректний обсяг. Приклад: 25")
            return
    await state.update_data(volume=volume, volume_tons=volume)
    await state.set_state(CreateLot.price)
    await message.answer("Введіть ціну (грн/т) або «⏭ Пропустити» (договірна)", reply_markup=kb_skip())


@router.message(CreateLot.price)
async def lot_price_entered(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.volume)
        await message.answer("Введіть обсяг:", reply_markup=kb_skip())
        return
    if message.text == "⏭ Пропустити":
        price = None
    else:
        try:
            price = float(message.text.replace(",", ".").replace(" ", "").strip())
            if price <= 0:
                raise ValueError
        except Exception:
            await message.answer("❌ Введіть коректну ціну. Приклад: 8500")
            return
    await state.update_data(price=price)
    await state.set_state(CreateLot.comment)
    await message.answer("Додайте коментар або «⏭ Пропустити»", reply_markup=kb_skip())


@router.message(CreateLot.comment)
async def lot_comment_entered(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(CreateLot.price)
        await message.answer("Введіть ціну:", reply_markup=kb_skip())
        return

    await _ensure_tables()
    comment = None if message.text == "⏭ Пропустити" else message.text.strip()

    data = await state.get_data()
    user_id = await get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("❌ Помилка: користувач не знайдений. Зробіть /start")
        return

    # SAFE defaults for NOT NULL columns
    volume_tons = data.get("volume_tons")
    if volume_tons is None:
        volume_tons = data.get("volume") or 0
    try:
        volume_tons = float(volume_tons)
    except Exception:
        volume_tons = 0.0

    quality_json = data.get("quality_json")
    if quality_json in (None, "", "null"):
        quality_json = json.dumps({}, ensure_ascii=False)
    if isinstance(quality_json, (dict, list)):
        quality_json = json.dumps(quality_json, ensure_ascii=False)

    async with aiosqlite.connect(DB_FILE) as db:
        cols = await _lots_columns(db)
        volume_col = "volume_tons" if "volume_tons" in cols else "volume"
        has_quality = "quality_json" in cols
        has_views = "views_count" in cols

        insert_cols = ["owner_user_id", "type", "crop", volume_col]
        params = [user_id, data.get("lot_type"), data.get("crop"), volume_tons]

        if has_quality:
            insert_cols.append("quality_json")
            params.append(quality_json)
        if has_views:
            insert_cols.append("views_count")
            params.append(0)

        insert_cols += ["region", "location", "price", "comment"]

        params += [data.get("region"), data.get("location"), data.get("price"), comment]

        placeholders = ", ".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO lots ({', '.join(insert_cols)}, status, created_at) VALUES ({placeholders}, 'active', datetime('now'))"
        await db.execute(sql, tuple(params))

        cur = await db.execute("SELECT last_insert_rowid()")
        row = await cur.fetchone()
        lot_id = row[0] if row else None
        await db.commit()

    await state.clear()
    await message.answer(f"✅ Заявку створено! № <code>{lot_id}</code>", reply_markup=kb_market_menu())


@router.message(F.text == "📂 Мої заявки")
async def my_lots(message: Message):
    await _ensure_tables()
    user_id = await get_user_id(message.from_user.id)
    if not user_id:
        await message.answer("❌ Помилка")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM lots WHERE owner_user_id=? AND status='active' ORDER BY created_at DESC",
            (user_id,)
        )
        lots = await cur.fetchall()

    if not lots:
        await message.answer("У вас немає активних заявок", reply_markup=kb_market_menu())
        return

    await message.answer(f"📂 Ваші заявки: {len(lots)}")
    for lot in lots:
        await message.answer(format_lot_text(dict(lot)), reply_markup=kb_lot_actions(lot['id'], True))


@router.message(F.text == "💰 Біржові пропозиції")
async def exchange_offers(message: Message):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM lots WHERE status='active' ORDER BY created_at DESC LIMIT 20")
        lots = await cur.fetchall()

    if not lots:
        await message.answer("Наразі немає активних пропозицій", reply_markup=kb_market_menu())
        return

    user_id = await get_user_id(message.from_user.id)
    await message.answer(f"💰 Пропозиції: {len(lots)}")
    for lot in lots:
        is_owner = (lot["owner_user_id"] == user_id)
        await message.answer(format_lot_text(dict(lot)), reply_markup=kb_lot_actions(lot["id"], is_owner))


@router.callback_query(F.data.startswith("lot:delete:"))
async def delete_lot(cb: CallbackQuery):
    await _ensure_tables()
    lot_id = int(cb.data.split(":")[-1])
    user_id = await get_user_id(cb.from_user.id)

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT owner_user_id FROM lots WHERE id=?", (lot_id,))
        row = await cur.fetchone()
        if not row or row[0] != user_id:
            await cb.answer("❌ Це не ваша заявка", show_alert=True)
            return
        await db.execute("UPDATE lots SET status='deleted' WHERE id=?", (lot_id,))
        await db.commit()

    await cb.answer("✅ Знято", show_alert=True)


@router.message(F.text == "⬅️ Головне меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    from src.bot.handlers.start import kb_main_menu, get_user_row, kb_admin_menu

    u = await get_user_row(message.from_user.id)
    is_admin = False
    try:
        if u and hasattr(u, "keys") and "role" in u.keys():
            is_admin = (u["role"] == "admin")
        elif isinstance(u, dict):
            is_admin = (u.get("role") == "admin")
    except Exception:
        is_admin = False

    await message.answer("⬅️ Головне меню", reply_markup=kb_admin_menu() if is_admin else kb_main_menu())
