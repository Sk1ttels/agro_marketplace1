from __future__ import annotations
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def main_menu(is_admin: bool = False):
    """Єдине меню для всіх — адмін-панель видалена"""
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
