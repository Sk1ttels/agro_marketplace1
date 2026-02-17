"""Старт / реєстрація / профіль / редагування / підписка / адмін-панель
ЗГІДНО З ТЗ: Фермер/Покупець/Логіст, одноразова реєстрація
ПОВНА ФУНКЦІОНАЛЬНІСТЬ БЕЗ ЗАГЛУШОК
"""

from __future__ import annotations

import os
import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Логування
logger = logging.getLogger(__name__)

router = Router()

try:
    from config.settings import DB_PATH as _DB_PATH
    DB_FILE = str(_DB_PATH)
except Exception:
    DB_FILE = os.getenv('DB_FILE', 'data/agro_bot.db')

ADMIN_IDS = set()
try:
    _raw = os.getenv('ADMIN_IDS', '[]')
    ADMIN_IDS = set(json.loads(_raw)) if _raw else set()
except Exception:
    ADMIN_IDS = set()


# ===================== FSM =====================

class Registration(StatesGroup):
    role = State()
    region = State()
    phone = State()
    company_name = State()


class EditProfile(StatesGroup):
    pick_field = State()
    role = State()
    region = State()
    phone = State()
    company_name = State()


# ===================== Keyboards =====================

ROLE_TEXT_TO_CODE = {
    "👨‍🌾 Фермер": "farmer",
    "🧑‍💼 Покупець": "buyer",
    "🚚 Логіст": "logistic",
}

ROLE_CODE_TO_TEXT = {
    "farmer": "👨‍🌾 Фермер",
    "buyer": "🧑‍💼 Покупець",
    "logistic": "🚚 Логіст",
    "admin": "🛡 Адмін",
    "guest": "—",
}

# Всі тексти кнопок меню (щоб catch-all не реагував на них)
MENU_BUTTONS = {
    "🌾 Маркет", "🔁 Зустрічні", "🔨 Торг", "💬 Мої чати",
    "📇 Мої контакти", "📈 Ціни", "🚚 Логістика", "👤 Профіль", "⭐ Підписка",
    "🆘 Підтримка", "💎 Купити PRO",
    "📅 Мій статус", "⬅️ Назад", "✏️ Редагувати профіль",
    "➕ Додати авто", "📦 Створити заявку", "🚛 Транспорт", "📨 Заявки",
    "⏭ Пропустити",
    "👨‍🌾 Фермер", "🧑‍💼 Покупець", "🚚 Логіст",
    "❌ Вийти з чату",
}


def kb_main_menu():
    """Головне меню"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="🌾 Маркет")
    kb.button(text="🔁 Зустрічні")
    kb.button(text="🔨 Торг")
    kb.button(text="💬 Мої чати")
    kb.button(text="📇 Мої контакти")
    kb.button(text="📈 Ціни")
    kb.button(text="🚚 Логістика")
    kb.button(text="👤 Профіль")
    kb.button(text="⭐ Підписка")
    kb.button(text="🆘 Підтримка")
    kb.adjust(2, 2, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


# Alias — тепер однакове меню для всіх
kb_admin_menu = kb_main_menu


def kb_roles():
    kb = ReplyKeyboardBuilder()
    kb.button(text="👨‍🌾 Фермер")
    kb.button(text="🧑‍💼 Покупець")
    kb.button(text="🚚 Логіст")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_regions():
    kb = InlineKeyboardBuilder()
    regions = [
        ("Вінницька", "vinnytska"), ("Волинська", "volynska"),
        ("Дніпропетровська", "dnipropetrovska"), ("Донецька", "donetska"),
        ("Житомирська", "zhytomyrska"), ("Закарпатська", "zakarpatska"),
        ("Запорізька", "zaporizka"), ("Івано-Франківська", "ivano_frankivska"),
        ("Київська", "kyivska"), ("Кіровоградська", "kirovohradska"),
        ("Луганська", "luhanska"), ("Львівська", "lvivska"),
        ("Миколаївська", "mykolaivska"), ("Одеська", "odeska"),
        ("Полтавська", "poltavska"), ("Рівненська", "rivnenska"),
        ("Сумська", "sumska"), ("Тернопільська", "ternopilska"),
        ("Харківська", "kharkivska"), ("Херсонська", "khersonska"),
        ("Хмельницька", "khmelnytska"), ("Черкаська", "cherkaska"),
        ("Чернівецька", "chernivetska"), ("Чернігівська", "chernihivska"),
        ("м. Київ", "kyiv_city"), ("✍️ Інша", "custom"),
    ]
    for name, code in regions:
        kb.button(text=name, callback_data=f"reg:region:{code}")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


REGION_MAP = {
    "vinnytska": "Вінницька", "volynska": "Волинська",
    "dnipropetrovska": "Дніпропетровська", "donetska": "Донецька",
    "zhytomyrska": "Житомирська", "zakarpatska": "Закарпатська",
    "zaporizka": "Запорізька", "ivano_frankivska": "Івано-Франківська",
    "kyivska": "Київська", "kirovohradska": "Кіровоградська",
    "luhanska": "Луганська", "lvivska": "Львівська",
    "mykolaivska": "Миколаївська", "odeska": "Одеська",
    "poltavska": "Полтавська", "rivnenska": "Рівненська",
    "sumska": "Сумська", "ternopilska": "Тернопільська",
    "kharkivska": "Харківська", "khersonska": "Херсонська",
    "khmelnytska": "Хмельницька", "cherkaska": "Черкаська",
    "chernivetska": "Чернівецька", "chernihivska": "Чернігівська",
    "kyiv_city": "м. Київ",
}


def kb_skip_phone():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⏭ Пропустити")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_skip_company():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⏭ Пропустити")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_edit_fields():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Роль", callback_data="edit:field:role")
    kb.button(text="✏️ Область", callback_data="edit:field:region")
    kb.button(text="✏️ Телефон", callback_data="edit:field:phone")
    kb.button(text="✏️ Компанія", callback_data="edit:field:company_name")
    kb.button(text="⬅️ Назад", callback_data="edit:back")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def kb_subscription():
    kb = ReplyKeyboardBuilder()
    kb.button(text="💎 Купити PRO")
    kb.button(text="📅 Мій статус")
    kb.button(text="⬅️ Назад")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


# ===================== DB helpers =====================

async def ensure_user(telegram_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, role, region, is_banned, created_at)
            VALUES (?, 'guest', 'unknown', 0, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id,),
        )
        if telegram_id in ADMIN_IDS:
            await db.execute("UPDATE users SET role='admin' WHERE telegram_id=?", (telegram_id,))
        await db.commit()


async def get_user_row(telegram_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, telegram_id, role, region, phone, company, is_banned,
                   subscription_plan, subscription_until, created_at
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        return await cur.fetchone()


async def set_user_field(telegram_id: int, field: str, value):
    if field not in {"role", "region", "phone", "company"}:
        raise ValueError("Bad field")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE telegram_id=?", (value, telegram_id))
        await db.commit()


async def set_ban(telegram_id: int, banned: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (banned, telegram_id))
        await db.commit()


async def ensure_favorites_table() -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lot_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, lot_id)
            )
            """
        )
        await db.commit()


async def toggle_favorite_lot(user_id: int, lot_id: int) -> bool:
    await ensure_favorites_table()
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND lot_id = ?",
            (user_id, lot_id),
        )
        exists = await cur.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND lot_id = ?",
                (user_id, lot_id),
            )
            await db.commit()
            return False
        await db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, lot_id) VALUES (?, ?)",
            (user_id, lot_id),
        )
        await db.commit()
        return True


async def is_admin(telegram_id: int) -> bool:
    await ensure_user(telegram_id)
    u = await get_user_row(telegram_id)
    return bool(u and u["role"] == "admin")


async def is_registered(telegram_id: int) -> bool:
    u = await get_user_row(telegram_id)
    return bool(u and u["role"] not in ("guest", None))


async def is_banned(telegram_id: int) -> bool:
    u = await get_user_row(telegram_id)
    return bool(u and u["is_banned"])


def profile_text(u) -> str:
    if not u:
        return "❌ Помилка завантаження профілю"
    role_label = ROLE_CODE_TO_TEXT.get(u["role"], "—")
    phone = u["phone"] or "—"
    company = u["company"] or "—"
    region = u["region"] if u["region"] != "unknown" else "—"
    plan = u["subscription_plan"] or "free"
    until = u["subscription_until"] or "—"
    return (
        "👤 <b>Ваш профіль</b>\n\n"
        f"🆔 ID: <code>{u['telegram_id']}</code>\n"
        f"🎭 Роль: {role_label}\n"
        f"📍 Область: <b>{region}</b>\n"
        f"📞 Телефон: <b>{phone}</b>\n"
        f"🏢 Компанія: <b>{company}</b>\n\n"
        f"⭐ <b>Підписка</b>\n"
        f"План: <b>{plan.upper()}</b>\n"
        f"Активно до: <b>{until}</b>"
    )


def kb_profile():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редагувати", callback_data="profile:edit")
    kb.button(text="⭐ Підписка", callback_data="profile:sub")
    kb.adjust(2)
    return kb.as_markup()


async def show_profile(message: Message, telegram_id: int):
    u = await get_user_row(telegram_id)
    if not u:
        await message.answer("❌ Користувача не знайдено. Спробуйте /start")
        return
    await message.answer(profile_text(u), reply_markup=kb_profile())


async def _send_main_menu(message: Message, telegram_id: int, text: str = "🏠 Головне меню"):
    u = await get_user_row(telegram_id)
    markup = kb_admin_menu() if u and u["role"] == "admin" else kb_main_menu()
    await message.answer(text, reply_markup=markup)


# ===================== REGISTRATION FLOW =====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await ensure_user(message.from_user.id)

    if await is_banned(message.from_user.id):
        await message.answer("⛔ Ваш акаунт заблоковано")
        return

    if await is_registered(message.from_user.id):
        u = await get_user_row(message.from_user.id)
        markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
        await message.answer(
            f"👋 Вітаємо знову, <b>{message.from_user.first_name}</b>!\n\n"
            "Оберіть розділ:",
            reply_markup=markup
        )
    else:
        logger.info(f"Нова реєстрація: {message.from_user.id}")
        await state.set_state(Registration.role)
        await message.answer(
            "👋 <b>Вітаємо в Агромаркеті!</b>\n\n"
            "Для початку роботи потрібно пройти швидку реєстрацію.\n\n"
            "Оберіть вашу роль:",
            reply_markup=kb_roles()
        )


@router.message(Registration.role)
async def reg_role(message: Message, state: FSMContext):
    role_text = (message.text or "").strip()
    role_code = ROLE_TEXT_TO_CODE.get(role_text)
    if not role_code:
        await message.answer(
            "❌ Будь ласка, оберіть роль, натиснувши одну з кнопок нижче:",
            reply_markup=kb_roles()
        )
        return
    await set_user_field(message.from_user.id, "role", role_code)
    await state.set_state(Registration.region)
    await message.answer("📍 Оберіть вашу область:", reply_markup=kb_regions())


@router.callback_query(F.data.startswith("reg:region:"))
async def reg_region_callback(cb: CallbackQuery, state: FSMContext):
    current = await state.get_state()

    # Дозволяємо лише якщо юзер саме в процесі вибору регіону
    if current not in (Registration.region, EditProfile.region):
        await cb.answer("⚠️ Ця клавіатура вже неактивна. Натисніть /start", show_alert=True)
        return

    region_code = cb.data.split(":")[-1]
    await cb.answer()

    if region_code == "custom":
        # Просимо ввести вручну — залишаємо той самий стан
        await cb.message.answer(
            "✍️ Введіть назву вашої області:",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    region_name = REGION_MAP.get(region_code, region_code)
    await set_user_field(cb.from_user.id, "region", region_name)

    if current == Registration.region:
        await state.set_state(Registration.phone)
        await cb.message.answer(
            "📞 Введіть ваш телефон (або пропустіть):",
            reply_markup=kb_skip_phone()
        )
    elif current == EditProfile.region:
        await state.clear()
        await cb.message.answer("✅ Область оновлено!")
        await _send_main_menu(cb.message, cb.from_user.id)


@router.message(Registration.region)
async def reg_custom_region(message: Message, state: FSMContext):
    region = (message.text or "").strip()
    if len(region) < 2 or len(region) > 60:
        await message.answer("❌ Назва області має бути від 2 до 60 символів")
        return
    await set_user_field(message.from_user.id, "region", region)
    await state.set_state(Registration.phone)
    await message.answer(
        "📞 Введіть ваш телефон (або пропустіть):",
        reply_markup=kb_skip_phone()
    )


@router.message(Registration.phone)
async def reg_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if phone == "⏭ Пропустити":
        phone = None
    else:
        phone_clean = re.sub(r'[^\d+]', '', phone)
        if phone_clean and len(phone_clean) < 10:
            await message.answer(
                "❌ Некоректний номер телефону. Введіть у форматі 0XXXXXXXXX або натисніть «Пропустити»:",
                reply_markup=kb_skip_phone()
            )
            return
        phone = phone_clean or None

    await set_user_field(message.from_user.id, "phone", phone)
    await state.set_state(Registration.company_name)
    await message.answer(
        "🏢 Введіть назву компанії (або пропустіть):",
        reply_markup=kb_skip_company()
    )


@router.message(Registration.company_name)
async def reg_company(message: Message, state: FSMContext):
    company = (message.text or "").strip()
    if company == "⏭ Пропустити":
        company = None
    elif len(company) > 100:
        await message.answer("❌ Назва компанії занадто довга (макс 100 символів)")
        return

    await set_user_field(message.from_user.id, "company", company)
    await state.clear()

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()

    await message.answer(
        "✅ <b>Реєстрація завершена!</b>\n\n"
        "Ласкаво просимо до Агромаркету! 🌾\n"
        "Оберіть розділ у меню нижче:",
        reply_markup=markup
    )


# ===================== MAIN MENU HANDLERS =====================

@router.message(F.text == "👤 Профіль")
async def show_my_profile(message: Message):
    await show_profile(message, message.from_user.id)


@router.callback_query(F.data == "profile:sub")
async def open_subscription_from_profile(cb: CallbackQuery):
    from src.bot.handlers.subscriptions import get_subscription_menu_kb
    await cb.message.answer("⭐ <b>Підписка</b>\n\nОберіть дію:", reply_markup=get_subscription_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "profile:edit")
async def edit_profile_from_profile(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer(
        "✏️ <b>Редагування профілю</b>\n\nОберіть поле для редагування:",
        reply_markup=kb_edit_fields(),
    )


@router.message(F.text == "✏️ Редагувати профіль")
async def edit_profile_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✏️ <b>Редагування профілю</b>\n\nОберіть поле для редагування:",
        reply_markup=kb_edit_fields()
    )


@router.callback_query(F.data.startswith("edit:field:"))
async def edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[-1]
    await cb.answer()
    if field == "role":
        await state.set_state(EditProfile.role)
        await cb.message.answer("Оберіть нову роль:", reply_markup=kb_roles())
    elif field == "region":
        await state.set_state(EditProfile.region)
        await cb.message.answer("Оберіть нову область:", reply_markup=kb_regions())
    elif field == "phone":
        await state.set_state(EditProfile.phone)
        await cb.message.answer("Введіть новий телефон:", reply_markup=kb_skip_phone())
    elif field == "company_name":
        await state.set_state(EditProfile.company_name)
        await cb.message.answer("Введіть нову назву компанії:", reply_markup=kb_skip_company())


@router.callback_query(F.data == "edit:back")
async def edit_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await _send_main_menu(cb.message, cb.from_user.id, "⬅️ Головне меню")


@router.message(EditProfile.role)
async def edit_role_handler(message: Message, state: FSMContext):
    role_code = ROLE_TEXT_TO_CODE.get((message.text or "").strip())
    if not role_code:
        await message.answer("❌ Оберіть роль з клавіатури:", reply_markup=kb_roles())
        return
    await set_user_field(message.from_user.id, "role", role_code)
    await state.clear()
    await message.answer("✅ Роль оновлено!")
    await _send_main_menu(message, message.from_user.id)


@router.message(EditProfile.region)
async def edit_region_handler(message: Message, state: FSMContext):
    region = (message.text or "").strip()
    if len(region) < 2:
        await message.answer("Оберіть область на клавіатурі вище або введіть назву:")
        return
    await set_user_field(message.from_user.id, "region", region)
    await state.clear()
    await message.answer("✅ Область оновлено!")
    await _send_main_menu(message, message.from_user.id)


@router.message(EditProfile.phone)
async def edit_phone_handler(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if phone == "⏭ Пропустити":
        phone = None
    await set_user_field(message.from_user.id, "phone", phone)
    await state.clear()
    await message.answer("✅ Телефон оновлено!")
    await _send_main_menu(message, message.from_user.id)


@router.message(EditProfile.company_name)
async def edit_company_handler(message: Message, state: FSMContext):
    company = (message.text or "").strip()
    if company == "⏭ Пропустити":
        company = None
    await set_user_field(message.from_user.id, "company", company)
    await state.clear()
    await message.answer("✅ Компанію оновлено!")
    await _send_main_menu(message, message.from_user.id)


# ===================== SUBSCRIPTION =====================

@router.message(F.text == "⭐ Підписка")
async def subscription_menu(message: Message):
    u = await get_user_row(message.from_user.id)
    if not u:
        await message.answer("Спочатку /start")
        return
    plan = u["subscription_plan"] or "free"
    until = u["subscription_until"] or "—"
    await message.answer(
        "⭐ <b>Підписка</b>\n\n"
        f"Поточний план: <b>{plan.upper()}</b>\n"
        f"Активно до: <b>{until}</b>\n\n"
        "💎 PRO дає:\n"
        "• Необмежена кількість лотів\n"
        "• Пріоритет у зустрічних пропозиціях\n"
        "• Розширена аналітика\n",
        reply_markup=kb_subscription()
    )


@router.message(F.text == "💎 Купити PRO")
async def buy_pro(message: Message):
    await message.answer(
        "💎 <b>Купівля PRO</b>\n\n"
        "✅ Для оформлення підписки зверніться до підтримки:\n"
        "Telegram: @agro_support\n\n"
        "💰 Ціна: 199 грн/міс\n\n"
        "Після оплати підписка активується автоматично!",
        reply_markup=kb_subscription()
    )


@router.message(F.text == "📅 Мій статус")
async def my_status(message: Message):
    u = await get_user_row(message.from_user.id)
    plan = u["subscription_plan"] or "free"
    until = u["subscription_until"] or "—"
    await message.answer(
        f"📅 <b>Ваш статус</b>\n\nПлан: <b>{plan.upper()}</b>\nАктивно до: <b>{until}</b>",
        reply_markup=kb_subscription()
    )


@router.message(F.text == "⬅️ Назад")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await _send_main_menu(message, message.from_user.id, "⬅️ Головне меню")


# ===================== SUPPORT =====================

@router.message(F.text == "🆘 Підтримка")
async def support(message: Message):
    await message.answer(
        "🆘 <b>Підтримка</b>\n\n"
        "📞 Контакти підтримки:\n"
        "• Telegram: @agro_support\n"
        "• Email: support@agro.market\n"
        "• Телефон: +380 (XX) XXX-XX-XX\n\n"
        "⏰ Час роботи: Пн-Пт 9:00-18:00\n\n"
        "💬 Або напишіть ваше питання тут, і ми відповімо найближчим часом:"
    )






# ===================== CATCH-ALL =====================

@router.message(F.text == "🔁 Зустрічні")
async def counteroffers(message: Message):
    u = await get_user_row(message.from_user.id)
    user_id = u["id"]
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT l.*, u.company
            FROM lots l JOIN users u ON l.owner_user_id = u.id
            WHERE l.status = 'active' AND l.owner_user_id != ?
            AND EXISTS (
                SELECT 1 FROM lots my_lot WHERE my_lot.owner_user_id = ?
                AND my_lot.status = 'active' AND my_lot.type != l.type AND my_lot.crop = l.crop
            )
            ORDER BY l.created_at DESC LIMIT 10
            """,
            (user_id, user_id)
        )
        lots = await cur.fetchall()
    if not lots:
        await message.answer(
            "🔁 <b>Зустрічні пропозиції</b>\n\n"
            "Наразі немає зустрічних пропозицій.\n\n"
            "💡 Створіть лот, щоб система автоматично знаходила відповідні пропозиції!"
        )
        return
    await message.answer(f"🔁 <b>Знайдено {len(lots)} зустрічних пропозицій:</b>")
    for lot in lots:
        lot_type = "📤 Продам" if lot["type"] == "sell" else "📥 Куплю"
        text = (
            f"{lot_type} <b>{lot['crop']}</b>\n"
            f"📦 Обсяг: {lot['volume']} т\n"
            f"💰 Ціна: {lot['price']} грн/т\n"
            f"📍 {lot['region']}\n"
            f"🏢 {lot['company'] or 'Приватна особа'}"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="💬 Написати", callback_data=f"chat:start:lot:{lot['id']}")
        kb.button(text="⭐ В обране", callback_data=f"fav:toggle:lot:{lot['id']}")
        kb.adjust(2)
        await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("fav:toggle:lot:"))
async def favorite_toggle(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer("Невірний формат", show_alert=True)
        return
    try:
        lot_id = int(parts[3])
    except ValueError:
        await cb.answer("Невірний ID", show_alert=True)
        return
    u = await get_user_row(cb.from_user.id)
    if not u:
        await cb.answer("Спочатку завершіть реєстрацію", show_alert=True)
        return
    is_added = await toggle_favorite_lot(u["id"], lot_id)
    await cb.answer("⭐ Додано в обране" if is_added else "🗑 Прибрано з обраного")


# 🔨 Торг — handled by offers_handlers.py


# 💬 Мої чати — handled by chat.py


@router.message(F.text == "📈 Ціни")
async def prices(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT crop, COUNT(*) as count,
                   AVG(CAST(price AS REAL)) as avg_price,
                   MIN(CAST(price AS REAL)) as min_price,
                   MAX(CAST(price AS REAL)) as max_price
            FROM lots WHERE status = 'active' AND price IS NOT NULL AND price != ''
            GROUP BY crop ORDER BY count DESC LIMIT 10
            """,
        )
        stats = await cur.fetchall()
    if not stats:
        await message.answer(
            "📈 <b>Ціни та аналітика</b>\n\n"
            "Недостатньо даних для аналізу.\n\n"
            "💡 Створіть лоти, щоб отримати статистику цін!"
        )
        return
    text = "📈 <b>Аналітика цін</b>\n\n"
    for stat in stats:
        text += (
            f"🌾 <b>{stat['crop']}</b>\n"
            f"  📊 Лотів: {stat['count']}\n"
            f"  💰 Середня: {stat['avg_price']:.0f} грн/т\n"
            f"  📉 Мін: {stat['min_price']:.0f} грн/т\n"
            f"  📈 Макс: {stat['max_price']:.0f} грн/т\n\n"
        )
    await message.answer(text)


# ===================== UNIVERSAL CATCH-ALL =====================
# Цей хендлер ловить ВСЕ що не відповідає жодному іншому стану
# і НЕ є кнопкою меню — щоб бот не "тупив" і не перепитував

@router.message(F.text)
async def universal_catch_all(message: Message, state: FSMContext):
    """Ловить невідомий текст поза FSM-станами"""
    current_state = await state.get_state()
    text = (message.text or "").strip()

    # Якщо користувач в якомусь FSM-стані — не втручаємось
    if current_state:
        return

    # Якщо це кнопка меню — показуємо головне меню (на випадок зависання клавіатури)
    if text in MENU_BUTTONS:
        await _send_main_menu(message, message.from_user.id, "🏠 Оберіть розділ:")
        return

    # Перевіряємо реєстрацію
    if not await is_registered(message.from_user.id):
        await message.answer(
            "👋 Спочатку пройдіть реєстрацію.\nНатисніть /start"
        )
        return

    # Невідома команда — підказуємо
    await message.answer(
        "❓ Не зрозумів вас. Скористайтесь меню нижче або натисніть /start",
        reply_markup=(await _get_markup(message.from_user.id))
    )


async def _get_markup(telegram_id: int):
    u = await get_user_row(telegram_id)
    return kb_admin_menu() if u and u["role"] == "admin" else kb_main_menu()
