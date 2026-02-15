# -*- coding: utf-8 -*-
"""
Авторизація для веб-панелі
"""

from flask_login import UserMixin
from config.settings import ADMIN_USER, ADMIN_PASS


class AdminUser(UserMixin):
    """Клас адміністратора для Flask-Login"""
    
    def __init__(self, username: str):
        self.id = username
        self.username = username
    
    def get_id(self) -> str:
        return self.username


def check_login(username: str, password: str) -> bool:
    """
    Перевірка логіну і пароля
    Спершу перевіряємо з .env, потім можна додати перевірку з БД
    """
    # Перевірка з .env файлу
    if username == ADMIN_USER and password == ADMIN_PASS:
        return True
    
    # TODO: Додати перевірку з таблиці web_admins
    # conn = get_conn()
    # row = conn.execute("SELECT password_hash FROM web_admins WHERE username=? AND is_active=1", (username,)).fetchone()
    # if row:
    #     return check_password_hash(row["password_hash"], password)
    
    return False
