from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_lots_kb(lot_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="❌ Закрити",
        callback_data=f"admin:lot:close:{lot_id}"
    )
    return kb.as_markup()
