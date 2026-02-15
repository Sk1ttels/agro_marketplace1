"""Старт / реєстрація / профіль / редагування / підписка / адмін-панель
ЗГІДНО З ТЗ: Фермер/Покупець/Логіст, одноразова реєстрація
ПОВНА ФУНКЦІОНАЛЬНІСТЬ БЕЗ ЗАГЛУШОК
"""

from __future__ import annotations

import os
from src.database.migrate import migrate
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

DB_FILE = os.getenv('DB_FILE', './agro_bot.db')

# Run migrations once at import (safe & idempotent)
migrate(os.path.abspath(DB_FILE))
# ✅ Адмін по whitelist
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


class AdminBroadcast(StatesGroup):
    message = State()
    confirm = State()


class AdminBanUser(StatesGroup):
    user_id = State()
    confirm = State()


# ===================== Keyboards =====================

# ТЗ: ролі - Фермер/Покупець/Логіст
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


def kb_main_menu():
    """Головне меню згідно з ТЗ п.5"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="🌾 Маркет")
    kb.button(text="🔁 Зустрічні")
    kb.button(text="🔨 Торг")
    kb.button(text="💬 Мої чати")
    kb.button(text="📈 Ціни")
    kb.button(text="🚚 Логістика")
    kb.button(text="👤 Профіль")
    kb.button(text="⭐ Підписка")
    kb.button(text="🆘 Підтримка")
    kb.adjust(2, 2, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def kb_admin_menu():
    """Меню для адміна з додатковими кнопками"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="🌾 Маркет")
    kb.button(text="🔁 Зустрічні")
    kb.button(text="🔨 Торг")
    kb.button(text="💬 Мої чати")
    kb.button(text="📈 Ціни")
    kb.button(text="🚚 Логістика")
    kb.button(text="👤 Профіль")
    kb.button(text="⭐ Підписка")
    kb.button(text="🆘 Підтримка")
    kb.button(text="🛠 Адмін-панель")
    kb.adjust(2, 2, 2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def kb_roles():
    """ТЗ п.3: ролі користувачів"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="👨‍🌾 Фермер")
    kb.button(text="🧑‍💼 Покупець")
    kb.button(text="🚚 Логіст")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_regions():
    """ТЗ п.4.1: область обов'язково"""
    kb = InlineKeyboardBuilder()
    regions = [
        ("Вінницька", "vinnytska"),
        ("Волинська", "volynska"),
        ("Дніпропетровська", "dnipropetrovska"),
        ("Донецька", "donetska"),
        ("Житомирська", "zhytomyrska"),
        ("Закарпатська", "zakarpatska"),
        ("Запорізька", "zaporizka"),
        ("Івано-Франківська", "ivano_frankivska"),
        ("Київська", "kyivska"),
        ("Кіровоградська", "kirovohradska"),
        ("Луганська", "luhanska"),
        ("Львівська", "lvivska"),
        ("Миколаївська", "mykolaivska"),
        ("Одеська", "odeska"),
        ("Полтавська", "poltavska"),
        ("Рівненська", "rivnenska"),
        ("Сумська", "sumska"),
        ("Тернопільська", "ternopilska"),
        ("Харківська", "kharkivska"),
        ("Херсонська", "khersonska"),
        ("Хмельницька", "khmelnytska"),
        ("Черкаська", "cherkaska"),
        ("Чернівецька", "chernivetska"),
        ("Чернігівська", "chernihivska"),
        ("м. Київ", "kyiv_city"),
        ("✍️ Інша", "custom"),
    ]
    for name, code in regions:
        kb.button(text=name, callback_data=f"reg:region:{code}")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def kb_skip_phone():
    """Телефон опційно"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="⏭ Пропустити")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_skip_company():
    """Назва компанії опційно"""
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


def kb_admin_panel():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="👥 Користувачі", callback_data="admin:users:0")
    kb.button(text="📢 Розсилка", callback_data="admin:broadcast")
    kb.button(text="⛔ Бан/Розбан", callback_data="admin:ban")
    kb.button(text="❌ Закрити", callback_data="admin:close")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def kb_users_navigation(page: int, total_pages: int):
    kb = InlineKeyboardBuilder()

    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"admin:users:{page-1}")
    if page < total_pages - 1:
        kb.button(text="➡️ Далі", callback_data=f"admin:users:{page+1}")

    kb.button(text="🔙 До меню", callback_data="admin:close")
    kb.adjust(2, 1)
    return kb.as_markup()


def kb_broadcast_confirm():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Відправити", callback_data="admin:broadcast:confirm")
    kb.button(text="❌ Скасувати", callback_data="admin:broadcast:cancel")
    kb.adjust(2)
    return kb.as_markup()


def kb_ban_confirm():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Підтвердити", callback_data="admin:ban:confirm")
    kb.button(text="❌ Скасувати", callback_data="admin:ban:cancel")
    kb.adjust(2)
    return kb.as_markup()


# ===================== DB helpers =====================

async def ensure_user(telegram_id: int):
    """Створює запис користувача якщо немає"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, role, region, is_banned, created_at)
            VALUES (?, 'guest', 'unknown', 0, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id,),
        )
        # Автоматично призначаємо роль адміна з whitelist
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
    """Оновлює поле користувача"""
    if field not in {"role", "region", "phone", "company"}:
        raise ValueError("Bad field")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE telegram_id=?", (value, telegram_id))
        await db.commit()


async def set_ban(telegram_id: int, banned: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (banned, telegram_id))
        await db.commit()


async def is_admin(telegram_id: int) -> bool:
    await ensure_user(telegram_id)
    u = await get_user_row(telegram_id)
    return bool(u and u["role"] == "admin")


async def is_registered(telegram_id: int) -> bool:
    """Користувач вважається зареєстрованим, якщо має роль відмінну від guest"""
    u = await get_user_row(telegram_id)
    return bool(u and u["role"] not in ("guest", None))


async def is_banned(telegram_id: int) -> bool:
    u = await get_user_row(telegram_id)
    return bool(u and u["is_banned"])


def profile_text(u) -> str:
    """Текст профілю користувача"""
    if not u:
        return "❌ Помилка завантаження профілю"

    role_label = ROLE_CODE_TO_TEXT.get(u["role"], "—")
    phone = u["phone"] or "—"
    company = u["company"] or "—"
    region = u["region"] if u["region"] != "unknown" else "—"

    plan = u["subscription_plan"] or "free"
    until = u["subscription_until"] or "—"

    text = (
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

    return text


def kb_profile():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редагувати", callback_data="profile:edit")
    kb.button(text="⭐ Підписка", callback_data="profile:sub")
    kb.adjust(1)
    return kb.as_markup()



async def show_profile(message: Message, telegram_id: int):
    """Показує профіль користувача"""
    u = await get_user_row(telegram_id)
    if not u:
        await message.answer("❌ Користувача не знайдено. Спробуйте /start")
        return

    await message.answer(
        profile_text(u),
        reply_markup=kb_profile()
    )


# ===================== REGISTRATION FLOW =====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Старт бота"""
    await ensure_user(message.from_user.id)

    if await is_banned(message.from_user.id):
        await message.answer("⛔ Ваш акаунт заблоковано")
        return

    if await is_registered(message.from_user.id):
        # Вже зареєстрований
        u = await get_user_row(message.from_user.id)
        markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
        await message.answer(
            f"👋 Вітаємо знову, <b>{message.from_user.first_name}</b>!\n\n"
            "Оберіть розділ:",
            reply_markup=markup
        )
    else:
        # Реєстрація
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
        await message.answer("❌ Оберіть роль з клавіатури:", reply_markup=kb_roles())
        return

    await set_user_field(message.from_user.id, "role", role_code)
    await state.set_state(Registration.region)

    logger.info(f"Користувач {message.from_user.id} обрав роль: {role_code}")

    await message.answer(
        "📍 Оберіть вашу область:",
        reply_markup=kb_regions()
    )


@router.callback_query(F.data.startswith("reg:region:"))
async def reg_region_callback(cb: CallbackQuery, state: FSMContext):
    region_code = cb.data.split(":")[-1]

    await cb.answer()

    if region_code == "custom":
        await cb.message.answer(
            "✍️ Введіть назву вашої області:",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Стандартний регіон
    region_map = {
        "vinnytska": "Вінницька",
        "volynska": "Волинська",
        "dnipropetrovska": "Дніпропетровська",
        "donetska": "Донецька",
        "zhytomyrska": "Житомирська",
        "zakarpatska": "Закарпатська",
        "zaporizka": "Запорізька",
        "ivano_frankivska": "Івано-Франківська",
        "kyivska": "Київська",
        "kirovohradska": "Кіровоградська",
        "luhanska": "Луганська",
        "lvivska": "Львівська",
        "mykolaivska": "Миколаївська",
        "odeska": "Одеська",
        "poltavska": "Полтавська",
        "rivnenska": "Рівненська",
        "sumska": "Сумська",
        "ternopilska": "Тернопільська",
        "kharkivska": "Харківська",
        "khersonska": "Херсонська",
        "khmelnytska": "Хмельницька",
        "cherkaska": "Черкаська",
        "chernivetska": "Чернівецька",
        "chernihivska": "Чернігівська",
        "kyiv_city": "м. Київ",
    }

    region_name = region_map.get(region_code, region_code)
    await set_user_field(cb.from_user.id, "region", region_name)
    await state.set_state(Registration.phone)

    logger.info(f"Користувач {cb.from_user.id} обрав область: {region_name}")

    await cb.message.answer(
        "📞 Введіть ваш телефон (або пропустіть):",
        reply_markup=kb_skip_phone()
    )


@router.message(Registration.region)
async def reg_custom_region(message: Message, state: FSMContext):
    region = (message.text or "").strip()

    if len(region) < 2 or len(region) > 60:
        await message.answer("❌ Назва області має бути від 2 до 60 символів")
        return

    await set_user_field(message.from_user.id, "region", region)
    await state.set_state(Registration.phone)

    logger.info(f"Користувач {message.from_user.id} ввів область: {region}")

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
        # Базова валідація телефону
        phone = re.sub(r'[^\d+]', '', phone)
        if phone and len(phone) < 10:
            await message.answer("❌ Некоректний номер телефону. Спробуйте ще раз або пропустіть:")
            return

    await set_user_field(message.from_user.id, "phone", phone)
    await state.set_state(Registration.company_name)

    logger.info(f"Користувач {message.from_user.id} ввів телефон")

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

    logger.info(f"✅ Користувач {message.from_user.id} завершив реєстрацію")

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()

    await message.answer(
        "✅ <b>Реєстрація завершена!</b>\n\n"
        "Ви можете почати роботу з платформою.",
        reply_markup=markup
    )


# ===================== MAIN MENU HANDLERS =====================

@router.message(F.text == "👤 Профіль")
async def show_my_profile(message: Message):
    logger.info(f"👤 Користувач {message.from_user.id} відкрив профіль")
    await show_profile(message, message.from_user.id)



@router.callback_query(F.data == "profile:sub")
async def open_subscription_from_profile(cb: CallbackQuery):
    """Відкрити меню підписок з профілю"""
    # Імпорт локально — щоб уникнути циклічних імпортів
    from src.bot.handlers.subscriptions import get_subscription_menu_kb

    await cb.message.answer(
        "⭐ <b>Підписка</b>\n\nОберіть дію:",
        reply_markup=get_subscription_menu_kb()
    )
    await cb.answer()


@router.callback_query(F.data == "profile:edit")
async def edit_profile_from_profile(cb: CallbackQuery, state: FSMContext):
    """Запуск редагування профілю з inline-кнопки у профілі."""
    logger.info(f"✏️ Користувач {cb.from_user.id} відкрив редагування профілю (inline)")
    await cb.answer()
    await state.clear()
    await cb.message.answer(
        "✏️ <b>Редагування профілю</b>\n\n"
        "Оберіть поле для редагування:",
        reply_markup=kb_edit_fields(),
    )


@router.message(F.text == "✏️ Редагувати профіль")
async def edit_profile_start(message: Message, state: FSMContext):
    logger.info(f"✏️ Користувач {message.from_user.id} відкрив редагування профілю")
    await state.clear()
    await message.answer(
        "✏️ <b>Редагування профілю</b>\n\n"
        "Оберіть поле для редагування:",
        reply_markup=kb_edit_fields()
    )


@router.callback_query(F.data.startswith("edit:field:"))
async def edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[-1]

    logger.info(f"✏️ Користувач {cb.from_user.id} редагує поле: {field}")

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
    u = await get_user_row(cb.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
    await cb.message.answer("⬅️ Повернення до меню", reply_markup=markup)


@router.message(EditProfile.role)
async def edit_role_handler(message: Message, state: FSMContext):
    role_text = (message.text or "").strip()
    role_code = ROLE_TEXT_TO_CODE.get(role_text)

    if not role_code:
        await message.answer("❌ Оберіть роль з клавіатури:", reply_markup=kb_roles())
        return

    await set_user_field(message.from_user.id, "role", role_code)
    await state.clear()

    logger.info(f"✅ Користувач {message.from_user.id} змінив роль на {role_code}")

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
    await message.answer("✅ Роль оновлено!", reply_markup=markup)


@router.message(EditProfile.region)
async def edit_region_handler(message: Message, state: FSMContext):
    region = (message.text or "").strip()
    await set_user_field(message.from_user.id, "region", region)
    await state.clear()

    logger.info(f"✅ Користувач {message.from_user.id} змінив область на {region}")

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
    await message.answer("✅ Область оновлено!", reply_markup=markup)


@router.message(EditProfile.phone)
async def edit_phone_handler(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if phone == "⏭ Пропустити":
        phone = None
    await set_user_field(message.from_user.id, "phone", phone)
    await state.clear()

    logger.info(f"✅ Користувач {message.from_user.id} оновив телефон")

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
    await message.answer("✅ Телефон оновлено!", reply_markup=markup)


@router.message(EditProfile.company_name)
async def edit_company_handler(message: Message, state: FSMContext):
    company = (message.text or "").strip()
    if company == "⏭ Пропустити":
        company = None
    await set_user_field(message.from_user.id, "company", company)
    await state.clear()

    logger.info(f"✅ Користувач {message.from_user.id} оновив компанію")

    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u["role"] == "admin" else kb_main_menu()
    await message.answer("✅ Компанію оновлено!", reply_markup=markup)


# ===================== SUBSCRIPTION =====================

@router.message(F.text == "⭐ Підписка")
async def subscription_menu(message: Message):
    logger.info(f"⭐ Користувач {message.from_user.id} відкрив підписку")
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
    logger.info(f"💎 Користувач {message.from_user.id} купує PRO")
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
    logger.info(f"📅 Користувач {message.from_user.id} перевіряє статус")
    u = await get_user_row(message.from_user.id)

    plan = u["subscription_plan"] or "free"
    until = u["subscription_until"] or "—"

    await message.answer(
        f"📅 <b>Ваш статус</b>\n\n"
        f"План: <b>{plan.upper()}</b>\n"
        f"Активно до: <b>{until}</b>",
        reply_markup=kb_subscription()
    )


@router.message(F.text == "⬅️ Назад")
async def back_to_menu(message: Message):
    u = await get_user_row(message.from_user.id)
    markup = kb_admin_menu() if u and u["role"] == "admin" else kb_main_menu()
    await message.answer("⬅️ Головне меню", reply_markup=markup)


# ===================== SUPPORT =====================

@router.message(F.text == "🆘 Підтримка")
async def support(message: Message):
    logger.info(f"🆘 Користувач {message.from_user.id} відкрив підтримку")
    await message.answer(
        "🆘 <b>Підтримка</b>\n\n"
        "📞 Контакти підтримки:\n"
        "• Telegram: @agro_support\n"
        "• Email: support@agro.market\n"
        "• Телефон: +380 (XX) XXX-XX-XX\n\n"
        "⏰ Час роботи: Пн-Пт 9:00-18:00\n\n"
        "💬 Або напишіть ваше питання тут, і ми відповімо найближчим часом:"
    )


# ===================== ADMIN PANEL =====================

@router.message(F.text == "🛠 Адмін-панель")
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ заборонено")
        return

    logger.info(f"🛠 Адмін {message.from_user.id} відкрив панель")

    await message.answer(
        "🛠 <b>Адмін-панель</b>\n\n"
        "Оберіть дію:",
        reply_markup=kb_admin_panel()
    )


@router.callback_query(F.data == "admin:stats")
async def admin_stats(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ заборонено", show_alert=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        banned = (await (await db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")).fetchone())[0]
        farmers = (await (await db.execute("SELECT COUNT(*) FROM users WHERE role='farmer'")).fetchone())[0]
        buyers = (await (await db.execute("SELECT COUNT(*) FROM users WHERE role='buyer'")).fetchone())[0]
        logists = (await (await db.execute("SELECT COUNT(*) FROM users WHERE role='logistic'")).fetchone())[0]

        lots = (await (await db.execute("SELECT COUNT(*) FROM lots")).fetchone())[0]
        active_lots = (await (await db.execute("SELECT COUNT(*) FROM lots WHERE status='active'")).fetchone())[0]

    await cb.answer()
    await cb.message.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Всього користувачів: <b>{total}</b>\n"
        f"⛔ Забанено: <b>{banned}</b>\n\n"
        f"👨‍🌾 Фермери: <b>{farmers}</b>\n"
        f"🧑‍💼 Покупці: <b>{buyers}</b>\n"
        f"🚚 Логісти: <b>{logists}</b>\n\n"
        f"📦 Всього лотів: <b>{lots}</b>\n"
        f"✅ Активних: <b>{active_lots}</b>",
        reply_markup=kb_admin_panel()
    )


@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ заборонено", show_alert=True)
        return

    page = int(cb.data.split(":")[-1])
    per_page = 10
    offset = page * per_page

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        total = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        total_pages = (total + per_page - 1) // per_page

        cur = await db.execute(
            """
            SELECT telegram_id, role, region, phone, company, is_banned, created_at
            FROM users
            ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
            (per_page, offset)
        )
        users = await cur.fetchall()

    if not users:
        await cb.answer("Користувачів не знайдено", show_alert=True)
        return

    text = f"👥 <b>Користувачі</b> (сторінка {page + 1}/{total_pages})\n\n"

    for u in users:
        role = ROLE_CODE_TO_TEXT.get(u["role"], u["role"])
        status = "⛔ Забанений" if u["is_banned"] else "✅ Активний"
        text += (
            f"━━━━━━━━━━━━━━\n"
            f"🆔 <code>{u['telegram_id']}</code>\n"
            f"🎭 {role}\n"
            f"📍 {u['region']}\n"
            f"📊 {status}\n"
        )

    await cb.answer()
    await cb.message.edit_text(
        text,
        reply_markup=kb_users_navigation(page, total_pages)
    )


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ заборонено", show_alert=True)
        return

    await cb.answer()
    await state.set_state(AdminBroadcast.message)
    await cb.message.answer(
        "📢 <b>Розсилка</b>\n\n"
        "Введіть текст повідомлення для розсилки всім користувачам:"
    )


@router.message(AdminBroadcast.message)
async def admin_broadcast_message(message: Message, state: FSMContext):
    text = message.text or message.caption or ""

    if len(text) < 3:
        await message.answer("❌ Повідомлення занадто коротке")
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(AdminBroadcast.confirm)

    await message.answer(
        f"📢 <b>Підтвердження розсилки</b>\n\n"
        f"Текст:\n{text}\n\n"
        f"Надіслати всім користувачам?",
        reply_markup=kb_broadcast_confirm()
    )


@router.callback_query(F.data == "admin:broadcast:confirm")
async def admin_broadcast_confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text", "")

    await cb.answer("Розсилка розпочата...", show_alert=True)
    await state.clear()

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT telegram_id FROM users WHERE is_banned=0")
        users = await cur.fetchall()

    sent = 0
    failed = 0

    for user in users:
        try:
            await cb.bot.send_message(user[0], f"📢 <b>Повідомлення від адміністрації:</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    await cb.message.answer(
        f"✅ <b>Розсилка завершена</b>\n\n"
        f"Надіслано: {sent}\n"
        f"Помилок: {failed}",
        reply_markup=kb_admin_menu()
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def admin_broadcast_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Розсилка скасована")
    await cb.message.edit_text("❌ Розсилка скасована")


@router.callback_query(F.data == "admin:ban")
async def admin_ban_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ заборонено", show_alert=True)
        return

    await cb.answer()
    await state.set_state(AdminBanUser.user_id)
    await cb.message.answer(
        "⛔ <b>Бан/Розбан користувача</b>\n\n"
        "Введіть Telegram ID користувача:"
    )


@router.message(AdminBanUser.user_id)
async def admin_ban_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некоректний ID. Введіть число:")
        return

    u = await get_user_row(user_id)
    if not u:
        await message.answer("❌ Користувача не знайдено")
        await state.clear()
        return

    await state.update_data(ban_user_id=user_id)
    await state.set_state(AdminBanUser.confirm)

    status = "ЗАБАНЕНИЙ" if u["is_banned"] else "АКТИВНИЙ"
    action = "розбанити" if u["is_banned"] else "забанити"

    await message.answer(
        f"👤 <b>Користувач</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🎭 Роль: {ROLE_CODE_TO_TEXT.get(u['role'], u['role'])}\n"
        f"📊 Статус: {status}\n\n"
        f"Підтвердити дію: <b>{action}</b>?",
        reply_markup=kb_ban_confirm()
    )


@router.callback_query(F.data == "admin:ban:confirm")
async def admin_ban_confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("ban_user_id")

    if not user_id:
        await cb.answer("Помилка", show_alert=True)
        await state.clear()
        return

    u = await get_user_row(user_id)
    new_status = 0 if u["is_banned"] else 1

    await set_ban(user_id, new_status)
    await state.clear()

    action = "розбанений" if new_status == 0 else "забанений"

    await cb.answer(f"Користувач {action}", show_alert=True)
    await cb.message.edit_text(f"✅ Користувач <code>{user_id}</code> {action}")


@router.callback_query(F.data == "admin:ban:cancel")
async def admin_ban_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Скасовано")
    await cb.message.edit_text("❌ Операцію скасовано")


@router.callback_query(F.data == "admin:close")
async def admin_close(cb: CallbackQuery):
    await cb.answer()
    await cb.message.delete()


# ===================== CATCH-ALL =====================

@router.message(F.text == "🔁 Зустрічні")
async def counteroffers(message: Message):
    """Зустрічні пропозиції - повна функціональність"""
    logger.info(f"🔁 Користувач {message.from_user.id} відкрив зустрічні")

    u = await get_user_row(message.from_user.id)
    user_id = u["id"]

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Шукаємо зустрічні пропозиції (купуємо те, що хтось продає і навпаки)
        cur = await db.execute(
            """
            SELECT l.*, u.company
            FROM lots l
                     JOIN users u ON l.owner_user_id = u.id
            WHERE l.status = 'active'
              AND l.owner_user_id != ?
            AND EXISTS (
                SELECT 1 FROM lots my_lot
                WHERE my_lot.owner_user_id = ?
                AND my_lot.status = 'active'
                AND my_lot.type != l.type
                AND my_lot.crop = l.crop
            )
            ORDER BY l.created_at DESC
                LIMIT 10
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


@router.message(F.text == "🔨 Торг")
async def trade(message: Message):
    """Торг/пропозиції - повна функціональність"""
    logger.info(f"🔨 Користувач {message.from_user.id} відкрив торг")

    u = await get_user_row(message.from_user.id)
    user_id = u["id"]

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Отримуємо всі пропозиції по лотах користувача
        cur = await db.execute(
            """
            SELECT co.*, l.crop, l.type, l.price as lot_price,
                   u.company as sender_company
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
                     JOIN users u ON co.sender_user_id = u.id
            WHERE l.owner_user_id = ?
              AND co.status = 'pending'
            ORDER BY co.created_at DESC
            """,
            (user_id,)
        )
        offers = await cur.fetchall()

    if not offers:
        await message.answer(
            "🔨 <b>Торг</b>\n\n"
            "Наразі немає активних пропозицій.\n\n"
            "💡 Ваші лоти отримують пропозиції автоматично!"
        )
        return

    await message.answer(f"🔨 <b>Активних пропозицій: {len(offers)}</b>")

    for offer in offers:
        lot_type = "Продаж" if offer["type"] == "sell" else "Купівля"
        text = (
            f"📋 <b>{lot_type}: {offer['crop']}</b>\n"
            f"💰 Ваша ціна: {offer['lot_price']} грн/т\n"
            f"💵 Пропозиція: {offer['offered_price']} грн/т\n"
            f"🏢 Від: {offer['sender_company'] or 'Приватна особа'}\n"
            f"💬 {offer['message'] or '—'}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Прийняти", callback_data=f"offer:accept:{offer['id']}")
        kb.button(text="❌ Відхилити", callback_data=f"offer:reject:{offer['id']}")
        kb.button(text="💬 Написати", callback_data=f"chat:start:lot:{offer['lot_id']}")
        kb.adjust(2, 1)

        await message.answer(text, reply_markup=kb.as_markup())


@router.message(F.text == "💬 Мої чати")
async def my_chats(message: Message):
    """Мої чати - повна функціональність"""
    logger.info(f"💬 Користувач {message.from_user.id} відкрив чати")

    u = await get_user_row(message.from_user.id)
    user_id = u["id"]

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT cs.*,
                   u1.company as user1_company,
                   u2.company as user2_company,
                   l.crop, l.type
            FROM chat_sessions cs
                     LEFT JOIN users u1 ON cs.user1_id = u1.id
                     LEFT JOIN users u2 ON cs.user2_id = u2.id
                     LEFT JOIN lots l ON cs.lot_id = l.id
            WHERE (cs.user1_id = ? OR cs.user2_id = ?)
              AND cs.status = 'active'
            ORDER BY cs.updated_at DESC
            """,
            (user_id, user_id)
        )
        chats = await cur.fetchall()

    if not chats:
        await message.answer(
            "💬 <b>Мої чати</b>\n\n"
            "У вас поки немає активних чатів.\n\n"
            "💡 Почніть діалог з картки лота!"
        )
        return

    await message.answer(f"💬 <b>Активних чатів: {len(chats)}</b>")

    for chat in chats:
        other_company = chat['user2_company'] if chat['user1_id'] == user_id else chat['user1_company']
        lot_info = f"{chat['type']}: {chat['crop']}" if chat['crop'] else "Загальний чат"

        text = (
            f"💬 <b>Чат</b>\n"
            f"👤 З: {other_company or 'Користувач'}\n"
            f"📋 Лот: {lot_info}\n"
            f"🕒 Оновлено: {chat['updated_at'] or chat['created_at']}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="💬 Відкрити", callback_data=f"chat:open:{chat['id']}")
        kb.adjust(1)

        await message.answer(text, reply_markup=kb.as_markup())


@router.message(F.text == "📈 Ціни")
async def prices(message: Message):
    """Ціни та аналітика - повна функціональність"""
    logger.info(f"📈 Користувач {message.from_user.id} відкрив ціни")

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Аналітика цін по культурах
        cur = await db.execute(
            """
            SELECT crop,
                   COUNT(*) as count,
                   AVG(CAST(price AS REAL)) as avg_price,
                   MIN(CAST(price AS REAL)) as min_price,
                   MAX(CAST(price AS REAL)) as max_price
            FROM lots
            WHERE status = 'active'
              AND price IS NOT NULL
              AND price != ''
            GROUP BY crop
            ORDER BY count DESC
                LIMIT 10
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