"""🧮 Калькулятор для лотів (сума/комісія/доставка)
Мета: швидко порахувати підсумкову суму угоди.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from src.bot.keyboards.main import main_menu

router = Router()

# ---------------- FSM ----------------

class LotCalc(StatesGroup):
    menu = State()
    price = State()
    qty = State()
    commission = State()
    delivery = State()

# ---------------- Keyboards ----------------

def kb_calc_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧮 Лот: сума/комісія/доставка")
    kb.button(text="⬅️ Назад")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)

def kb_inline_yes_no(prefix: str):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Так", callback_data=f"{prefix}:yes")
    b.button(text="❌ Ні", callback_data=f"{prefix}:no")
    b.adjust(2)
    return b.as_markup()

def kb_inline_back_to_menu():
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ До калькуляторів", callback_data="calc:back")
    return b.as_markup()

# ---------------- Helpers ----------------

def _parse_number(s: str) -> float | None:
    s = (s or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def _fmt_money(v: float) -> str:
    # 2 знаки, але без зайвих нулів
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    if s.endswith(",00"):
        s = s[:-3]
    return s

# ---------------- Handlers ----------------

@router.message(F.text == "🧮 Калькулятори")
async def calculators_root(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LotCalc.menu)
    await message.answer(
        "🧮 <b>Калькулятори</b>\n"
        "Оберіть потрібний варіант 👇",
        reply_markup=kb_calc_menu()
    )

@router.message(LotCalc.menu, F.text == "🧮 Лот: сума/комісія/доставка")
async def lot_calc_start(message: Message, state: FSMContext):
    await state.update_data(_calc_type="lot")
    await state.set_state(LotCalc.price)
    await message.answer(
        "Введіть <b>ціну за одиницю</b> (наприклад: <code>12500</code> або <code>12 500,50</code>):",
    )

@router.message(LotCalc.menu, F.text == "⬅️ Назад")
async def back_to_main_from_calc(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Головне меню 👇", reply_markup=main_menu(role="user"))

@router.message(LotCalc.price)
async def lot_calc_price(message: Message, state: FSMContext):
    price = _parse_number(message.text)
    if price is None or price <= 0:
        await message.answer("❌ Не бачу число. Введіть ціну ще раз (приклад: <code>12500</code>).")
        return
    await state.update_data(price=price)
    await state.set_state(LotCalc.qty)
    await message.answer("Тепер введіть <b>кількість</b> (наприклад: <code>10</code>):")

@router.message(LotCalc.qty)
async def lot_calc_qty(message: Message, state: FSMContext):
    qty = _parse_number(message.text)
    if qty is None or qty <= 0:
        await message.answer("❌ Не бачу число. Введіть кількість ще раз (приклад: <code>10</code>).")
        return
    await state.update_data(qty=qty)
    await state.set_state(LotCalc.commission)
    await message.answer(
        "Додати <b>комісію маркетплейсу</b>? (у відсотках, напр. 1.5)\n"
        "Натисніть кнопку:",
        reply_markup=kb_inline_yes_no("calc:commission")
    )

@router.callback_query(LotCalc.commission, F.data.startswith("calc:commission:"))
async def lot_calc_commission_choice(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":")[-1]
    await cb.answer()
    if choice == "no":
        await state.update_data(commission_pct=0.0)
        await state.set_state(LotCalc.delivery)
        await cb.message.answer(
            "Додати <b>доставку</b>? (сума у грн)\nНатисніть кнопку:",
            reply_markup=kb_inline_yes_no("calc:delivery")
        )
        return

    # yes
    await cb.message.answer("Введіть відсоток комісії (наприклад: <code>1.5</code>):")
    # залишаємо стан LotCalc.commission, але очікуємо message
    await state.update_data(_await_commission=True)

@router.message(LotCalc.commission)
async def lot_calc_commission_value(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_await_commission"):
        # якщо користувач просто щось написав не в тему — повторимо варіант
        await message.answer("Оберіть: додати комісію чи ні 👇", reply_markup=kb_inline_yes_no("calc:commission"))
        return

    pct = _parse_number(message.text)
    if pct is None or pct < 0 or pct > 100:
        await message.answer("❌ Введіть число від 0 до 100 (приклад: <code>1.5</code>).")
        return

    await state.update_data(commission_pct=pct, _await_commission=False)
    await state.set_state(LotCalc.delivery)
    await message.answer(
        "Додати <b>доставку</b>? (сума у грн)\nНатисніть кнопку:",
        reply_markup=kb_inline_yes_no("calc:delivery")
    )

@router.callback_query(LotCalc.delivery, F.data.startswith("calc:delivery:"))
async def lot_calc_delivery_choice(cb: CallbackQuery, state: FSMContext):
    choice = cb.data.split(":")[-1]
    await cb.answer()
    if choice == "no":
        await state.update_data(delivery=0.0)
        await _send_result(cb.message, state)
        return

    await cb.message.answer("Введіть суму доставки у грн (наприклад: <code>800</code>):")
    await state.update_data(_await_delivery=True)

@router.message(LotCalc.delivery)
async def lot_calc_delivery_value(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_await_delivery"):
        await message.answer("Оберіть: додати доставку чи ні 👇", reply_markup=kb_inline_yes_no("calc:delivery"))
        return

    delivery = _parse_number(message.text)
    if delivery is None or delivery < 0:
        await message.answer("❌ Введіть число (приклад: <code>800</code>).")
        return

    await state.update_data(delivery=delivery, _await_delivery=False)
    await _send_result(message, state)

async def _send_result(msg_obj, state: FSMContext):
    data = await state.get_data()
    price = float(data.get("price", 0.0))
    qty = float(data.get("qty", 0.0))
    commission_pct = float(data.get("commission_pct", 0.0))
    delivery = float(data.get("delivery", 0.0))

    subtotal = price * qty
    commission = subtotal * (commission_pct / 100.0)
    total = subtotal + commission + delivery

    text = (
        "🧮 <b>Результат</b>\n"
        f"• Ціна: <b>{_fmt_money(price)}</b> грн/од.\n"
        f"• Кількість: <b>{qty:g}</b>\n"
        f"• Сума: <b>{_fmt_money(subtotal)}</b> грн\n"
        f"• Комісія: <b>{commission_pct:g}%</b> → <b>{_fmt_money(commission)}</b> грн\n"
        f"• Доставка: <b>{_fmt_money(delivery)}</b> грн\n"
        f"— — —\n"
        f"✅ <b>Всього: {_fmt_money(total)} грн</b>\n\n"
        "Можна порахувати ще раз 👇"
    )

    # msg_obj може бути Message або CallbackQuery.message
    await msg_obj.answer(text, reply_markup=kb_inline_back_to_menu())
    await state.set_state(LotCalc.menu)

@router.callback_query(F.data == "calc:back")
async def calc_back(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(LotCalc.menu)
    await cb.message.answer("🧮 Оберіть калькулятор 👇", reply_markup=kb_calc_menu())
