"""
Обробник підписок для Telegram бота
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.bot.keyboards.main import main_menu
import aiosqlite
from datetime import datetime, timedelta
import json

router = Router()
DB_FILE = "agro_bot.db"

# Плани підписок (синхронізовано з веб-панеллю)
SUBSCRIPTION_PLANS = {
    'free': {
        'name': 'Безкоштовний',
        'emoji': '📦',
        'price': 0,
        'max_lots': 5,
        'max_photos': 3,
        'features': [
            '✅ До 5 активних лотів',
            '✅ До 3 фото на лот',
            '✅ Базовий чат',
            '❌ Без аналітики',
            '❌ Стандартна підтримка'
        ]
    },
    'basic': {
        'name': 'Базовий',
        'emoji': '⭐',
        'price': 199,
        'max_lots': 20,
        'max_photos': 10,
        'features': [
            '✅ До 20 активних лотів',
            '✅ До 10 фото на лот',
            '✅ Розширений чат',
            '✅ Базова аналітика',
            '❌ Стандартна підтримка'
        ]
    },
    'premium': {
        'name': 'Преміум',
        'emoji': '💎',
        'price': 499,
        'max_lots': 100,
        'max_photos': 20,
        'features': [
            '✅ До 100 активних лотів',
            '✅ До 20 фото на лот',
            '✅ Пріоритетний чат',
            '✅ Повна аналітика',
            '✅ Пріоритетна підтримка'
        ]
    },
    'business': {
        'name': 'Бізнес',
        'emoji': '👑',
        'price': 1499,
        'max_lots': -1,  # Необмежено
        'max_photos': 50,
        'features': [
            '✅ Необмежено лотів',
            '✅ До 50 фото на лот',
            '✅ VIP чат',
            '✅ Розширена аналітика',
            '✅ VIP підтримка 24/7',
            '✅ Персональний менеджер'
        ]
    }
}

# FSM States
class SubscriptionState(StatesGroup):
    choosing_plan = State()
    confirming_payment = State()

# ==================== HELPERS ====================

async def get_user_subscription(telegram_id: int):
    """Отримати підписку користувача"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Спочатку отримуємо user_id
        user = await db.execute(
            'SELECT id FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        user_row = await user.fetchone()
        if not user_row:
            return None

        user_id = user_row[0]

        # Отримуємо активну підписку
        cursor = await db.execute('''
                                  SELECT * FROM user_subscriptions
                                  WHERE user_id = ? AND is_active = 1
                                  ORDER BY id DESC LIMIT 1
                                  ''', (user_id,))
        subscription = await cursor.fetchone()

        if subscription:
            # Перевірка терміну дії
            if subscription[3]:  # expires_at
                expires = datetime.fromisoformat(subscription[3])
                if expires < datetime.now():
                    # Підписка закінчилась
                    await db.execute(
                        'UPDATE user_subscriptions SET is_active = 0 WHERE id = ?',
                        (subscription[0],)
                    )
                    await db.commit()
                    # Створюємо безкоштовну
                    return await create_free_subscription(user_id, db)

            return {
                'id': subscription[0],
                'user_id': subscription[1],
                'plan': subscription[2],
                'started_at': subscription[3],
                'expires_at': subscription[4],
                'is_active': subscription[5]
            }
        else:
            # Створюємо безкоштовну підписку
            return await create_free_subscription(user_id, db)

async def create_free_subscription(user_id: int, db):
    """Створити безкоштовну підписку"""
    cursor = await db.execute('''
                              INSERT INTO user_subscriptions (user_id, plan, is_active)
                              VALUES (?, 'free', 1)
                              ''', (user_id,))
    await db.commit()

    return {
        'id': cursor.lastrowid,
        'user_id': user_id,
        'plan': 'free',
        'started_at': datetime.now().isoformat(),
        'expires_at': None,
        'is_active': True
    }

async def check_lot_limit(telegram_id: int) -> tuple[bool, int, int]:
    """
    Перевірити ліміт лотів
    Повертає: (можна_створити, поточна_кількість, максимум)
    """
    subscription = await get_user_subscription(telegram_id)
    if not subscription:
        return False, 0, 0

    plan = SUBSCRIPTION_PLANS.get(subscription['plan'], SUBSCRIPTION_PLANS['free'])
    max_lots = plan['max_lots']

    async with aiosqlite.connect(DB_FILE) as db:
        user = await db.execute(
            'SELECT id FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        user_row = await user.fetchone()
        if not user_row:
            return False, 0, 0

        current = await db.execute(
            'SELECT COUNT(*) FROM lots WHERE owner_user_id = ? AND status = "active"',
            (user_row[0],)
        )
        current_count = (await current.fetchone())[0]

    if max_lots == -1:  # Необмежено
        return True, current_count, -1

    return current_count < max_lots, current_count, max_lots

# ==================== KEYBOARDS ====================

def get_subscription_menu_kb():
    """Головне меню підписок"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Моя підписка", callback_data="sub:current")],
        [InlineKeyboardButton(text="⭐ Переглянути плани", callback_data="sub:plans")],
        [InlineKeyboardButton(text="💳 Купити підписку", callback_data="sub:buy")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    return kb

def get_plans_keyboard():
    """Клавіатура з планами"""
    buttons = []
    for plan_key, plan_info in SUBSCRIPTION_PLANS.items():
        if plan_key != 'free':  # Не показуємо безкоштовний
            price_text = f"{plan_info['price']} грн/міс" if plan_info['price'] > 0 else "Безкоштовно"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{plan_info['emoji']} {plan_info['name']} - {price_text}",
                    callback_data=f"sub:select:{plan_key}"
                )
            ])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sub:menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_confirm_kb(plan_key: str):
    """Клавіатура підтвердження оплати"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатити", callback_data=f"sub:pay:{plan_key}")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="sub:plans")]
    ])
    return kb

# ==================== HANDLERS ====================

@router.message(F.text.in_(["⭐ Підписка", "⭐ Підписка / PRO"]))
async def subscription_menu(message: Message):
    """Меню підписок"""
    await message.answer(
        "⭐ <b>Підписки Агромаркет</b>\n\n"
        "Оберіть дію:",
        reply_markup=get_subscription_menu_kb()
    )

@router.callback_query(F.data == "sub:menu")
async def callback_subscription_menu(call: CallbackQuery):
    """Повернення в меню підписок"""
    await call.message.edit_text(
        "⭐ <b>Підписки Агромаркет</b>\n\n"
        "Оберіть дію:",
        reply_markup=get_subscription_menu_kb()
    )
    await call.answer()

@router.callback_query(F.data == "sub:current")
async def show_current_subscription(call: CallbackQuery):
    """Показати поточну підписку"""
    subscription = await get_user_subscription(call.from_user.id)

    if not subscription:
        await call.answer("Помилка отримання підписки", show_alert=True)
        return

    plan = SUBSCRIPTION_PLANS.get(subscription['plan'], SUBSCRIPTION_PLANS['free'])

    # Перевірка лімітів
    can_create, current_lots, max_lots = await check_lot_limit(call.from_user.id)

    text = f"{plan['emoji']} <b>Ваша підписка: {plan['name']}</b>\n\n"

    # Інформація про ліміти
    text += "📊 <b>Використання:</b>\n"
    if max_lots == -1:
        text += f"Лоти: {current_lots} / Необмежено\n"
    else:
        text += f"Лоти: {current_lots} / {max_lots}\n"

    # Термін дії
    if subscription.get('expires_at'):
        expires = datetime.fromisoformat(subscription['expires_at'])
        days_left = (expires - datetime.now()).days
        text += f"\n⏰ Діє до: {expires.strftime('%d.%m.%Y')}\n"
        text += f"Залишилось: {days_left} днів\n"
    else:
        text += "\n♾ Безстроково\n"

    # Можливості
    text += "\n🎁 <b>Можливості:</b>\n"
    for feature in plan['features']:
        text += f"{feature}\n"

    if subscription['plan'] == 'free':
        text += "\n💡 Оновіть підписку для додаткових можливостей!"

    await call.message.edit_text(
        text,
        reply_markup=get_subscription_menu_kb()
    )
    await call.answer()

@router.callback_query(F.data == "sub:plans")
async def show_plans(call: CallbackQuery):
    """Показати всі плани"""
    text = "⭐ <b>Доступні плани підписок</b>\n\n"
    text += "Оберіть план для детального перегляду:\n"

    await call.message.edit_text(
        text,
        reply_markup=get_plans_keyboard()
    )
    await call.answer()

@router.callback_query(F.data.startswith("sub:select:"))
async def select_plan(call: CallbackQuery, state: FSMContext):
    """Детальний перегляд плану"""
    plan_key = call.data.split(":", 2)[2]
    plan = SUBSCRIPTION_PLANS.get(plan_key)

    if not plan:
        await call.answer("План не знайдено", show_alert=True)
        return

    text = f"{plan['emoji']} <b>{plan['name']}</b>\n\n"
    text += f"💰 Ціна: <b>{plan['price']} грн/місяць</b>\n\n"
    text += "🎁 <b>Що включено:</b>\n"
    for feature in plan['features']:
        text += f"{feature}\n"

    text += f"\n📦 Лотів: "
    if plan['max_lots'] == -1:
        text += "Необмежено\n"
    else:
        text += f"{plan['max_lots']}\n"

    text += f"🖼 Фото на лот: {plan['max_photos']}\n"

    await call.message.edit_text(
        text,
        reply_markup=get_payment_confirm_kb(plan_key)
    )
    await call.answer()

@router.callback_query(F.data.startswith("sub:pay:"))
async def process_payment(call: CallbackQuery):
    """Обробка оплати"""
    plan_key = call.data.split(":", 2)[2]
    plan = SUBSCRIPTION_PLANS.get(plan_key)

    if not plan:
        await call.answer("План не знайдено", show_alert=True)
        return

    # TODO: Тут має бути інтеграція з платіжною системою
    # Наразі показуємо інструкції

    text = f"💳 <b>Оплата підписки {plan['name']}</b>\n\n"
    text += f"Сума: <b>{plan['price']} грн</b>\n\n"
    text += "📝 <b>Інструкція з оплати:</b>\n\n"
    text += "1. Перейдіть за посиланням нижче\n"
    text += "2. Оплатіть рахунок\n"
    text += "3. Підписка активується автоматично\n\n"
    text += "🔗 Посилання для оплати: [генерується]\n\n"
    text += "⏰ Рахунок дійсний 24 години"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатити", url="https://example.com/pay")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="sub:plans")]
    ])

    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

    # Створюємо запис про платіж
    async with aiosqlite.connect(DB_FILE) as db:
        user = await db.execute(
            'SELECT id FROM users WHERE telegram_id = ?',
            (call.from_user.id,)
        )
        user_row = await user.fetchone()
        if user_row:
            await db.execute('''
                             INSERT INTO payments (user_id, amount, currency, status, payment_method)
                             VALUES (?, ?, 'UAH', 'pending', 'online')
                             ''', (user_row[0], plan['price']))
            await db.commit()

@router.callback_query(F.data == "sub:buy")
async def buy_subscription(call: CallbackQuery):
    """Швидка купівля підписки"""
    await show_plans(call)

# Функція для перевірки перед створенням лоту
async def check_can_create_lot(telegram_id: int) -> tuple[bool, str]:
    """
    Перевірити чи може користувач створити лот
    Повертає: (можна, повідомлення)
    """
    can_create, current, maximum = await check_lot_limit(telegram_id)

    if can_create:
        return True, "OK"

    subscription = await get_user_subscription(telegram_id)
    plan = SUBSCRIPTION_PLANS.get(subscription['plan'], SUBSCRIPTION_PLANS['free'])

    message = (
        f"⚠️ Ви досягли ліміту лотів для плану '{plan['name']}'\n\n"
        f"Поточних лотів: {current} / {maximum}\n\n"
        f"Для створення більше лотів оновіть підписку:"
    )

    return False, message
