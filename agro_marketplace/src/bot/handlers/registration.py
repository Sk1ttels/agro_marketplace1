"""Registration flow: role -> district -> company_number -> company_name -> done"""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import aiosqlite

DB_FILE = "agro_bot.db"
router = Router()

# ---------- FSM ----------
class Reg(StatesGroup):
    role = State()
    district = State()
    company_number = State()
    company_name = State()

# ---------- Keyboards ----------
ROLE_MAP = {
    "admin": "👑 Адмін",
    "operator": "🧑‍💻 Оператор",
    "recipient": "📦 Отримувач",
}

DISTRICT_PRESETS = [
    "Київський", "Львівський", "Одеський", "Харківський",
]

def roles_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text=ROLE_MAP["admin"], callback_data="reg:role:admin")
    kb.button(text=ROLE_MAP["operator"], callback_data="reg:role:operator")
    kb.button(text=ROLE_MAP["recipient"], callback_data="reg:role:recipient")
    kb.adjust(1)
    return kb.as_markup()

def districts_kb():
    kb = InlineKeyboardBuilder()
    for d in DISTRICT_PRESETS:
        kb.button(text=f"📍 {d}", callback_data=f"reg:district:{d}")
    kb.button(text="✍️ Вписати свій район", callback_data="reg:district:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def main_menu_kb(is_registered: bool):
    kb = ReplyKeyboardBuilder()
    kb.button(text="👤 Профіль")
    kb.button(text="⭐ Підписка")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# ---------- DB helpers ----------
async def ensure_user(telegram_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, role, region, is_banned, created_at)
            VALUES (?, 'guest', '', 0, datetime('now'))
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id,),
        )
        await db.commit()

async def get_user_row(telegram_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, telegram_id, role, region, company, company_number FROM users WHERE telegram_id=?",
            (telegram_id,),
        )
        return await cur.fetchone()

async def set_user_fields(telegram_id: int, **fields):
    if not fields:
        return
    cols = []
    vals = []
    for k, v in fields.items():
        cols.append(f"{k}=?")
        vals.append(v)
    vals.append(telegram_id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f"UPDATE users SET {', '.join(cols)} WHERE telegram_id=?", vals)
        await db.commit()

def profile_text(row):
    # row: id, telegram_id, role, region, company, company_number
    _, tg, role, district, company_name, company_number = row
    role_label = {
        "admin": ROLE_MAP["admin"],
        "operator": ROLE_MAP["operator"],
        "recipient": ROLE_MAP["recipient"],
    }.get(role, "—")
    return (
        "👤 <b>Ваш профіль</b>\n\n"
        f"🆔 Telegram ID: <code>{tg}</code>\n"
        f"🎭 Роль: {role_label}\n"
        f"📍 Район: <b>{district or '—'}</b>\n"
        f"🏷 Номер компанії: <b>{company_number or '—'}</b>\n"
        f"🏢 Компанія: <b>{company_name or '—'}</b>\n"
    )

def is_registered(row) -> bool:
    if not row:
        return False
    _id, _tg, role, district, company_name, company_number = row
    return role not in (None, "guest", "") and bool(district) and bool(company_number) and bool(company_name)

# ---------- Flow ----------
async def start_registration(message: Message, state: FSMContext):
    await state.set_state(Reg.role)
    await message.answer("Оберіть вашу роль:", reply_markup=roles_kb())

async def continue_flow(message: Message, state: FSMContext):
    row = await get_user_row(message.from_user.id)
    if row and is_registered(row):
        await state.clear()
        await message.answer(profile_text(row), reply_markup=main_menu_kb(True), parse_mode="HTML")
        return

    # Determine next missing step
    if not row or row[2] in (None, "guest", ""):
        await state.set_state(Reg.role)
        await message.answer("Оберіть вашу роль:", reply_markup=roles_kb())
        return
    if not row[3]:
        await state.set_state(Reg.district)
        await message.answer("Оберіть район:", reply_markup=districts_kb())
        return
    if not row[5]:
        await state.set_state(Reg.company_number)
        await message.answer("Введіть номер компанії (можна цифри/букви):", reply_markup=ReplyKeyboardRemove())
        return
    if not row[4]:
        await state.set_state(Reg.company_name)
        await message.answer("Введіть назву компанії:", reply_markup=ReplyKeyboardRemove())
        return

    await state.clear()
    await message.answer(profile_text(row), reply_markup=main_menu_kb(True), parse_mode="HTML")

# ---------- Handlers ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await ensure_user(message.from_user.id)
    await continue_flow(message, state)

@router.message(F.text == "👤 Профіль")
async def profile(message: Message, state: FSMContext):
    await ensure_user(message.from_user.id)
    await continue_flow(message, state)

@router.callback_query(F.data.startswith("reg:role:"))
async def pick_role(cb: CallbackQuery, state: FSMContext):
    role = cb.data.split(":", 2)[2]
    await ensure_user(cb.from_user.id)
    await set_user_fields(cb.from_user.id, role=role)
    await cb.answer("Роль збережено")
    await state.set_state(Reg.district)
    await cb.message.edit_text("Оберіть район:", reply_markup=districts_kb())

@router.callback_query(F.data.startswith("reg:district:"))
async def pick_district(cb: CallbackQuery, state: FSMContext):
    value = cb.data.split(":", 2)[2]
    await ensure_user(cb.from_user.id)
    if value == "custom":
        await state.set_state(Reg.district)
        await cb.message.edit_text("Впишіть ваш район/область текстом:")
        await cb.answer()
        return
    await set_user_fields(cb.from_user.id, region=value)  # region column used as district
    await cb.answer("Район збережено")
    await state.set_state(Reg.company_number)
    await cb.message.edit_text("Введіть номер компанії (можна цифри/букви):")

@router.message(Reg.district)
async def district_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2 or len(text) > 60:
        await message.answer("Район має бути 2–60 символів. Спробуйте ще раз:")
        return
    await set_user_fields(message.from_user.id, region=text)
    await state.set_state(Reg.company_number)
    await message.answer("Введіть номер компанії (можна цифри/букви):")

@router.message(Reg.company_number)
async def company_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2 or len(text) > 30:
        await message.answer("Номер компанії має бути 2–30 символів. Спробуйте ще раз:")
        return
    await set_user_fields(message.from_user.id, company_number=text)
    await state.set_state(Reg.company_name)
    await message.answer("Введіть назву компанії:")

@router.message(Reg.company_name)
async def company_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2 or len(text) > 80:
        await message.answer("Назва компанії має бути 2–80 символів. Спробуйте ще раз:")
        return
    await set_user_fields(message.from_user.id, company=text)
    row = await get_user_row(message.from_user.id)
    await state.clear()
    await message.answer("✅ Реєстрація завершена!\n\n" + profile_text(row), reply_markup=main_menu_kb(True), parse_mode="HTML")
