# -*- coding: utf-8 -*-
"""Авторизація для веб-панелі"""

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
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
    Перевірка логіну і пароля.
    Підтримує як plain-text (з .env), так і хешовані паролі.
    """
    if username != ADMIN_USER:
        return False

    # Якщо пароль з .env починається з "pbkdf2:" або "scrypt:" — він хешований
    if ADMIN_PASS and (ADMIN_PASS.startswith("pbkdf2:") or ADMIN_PASS.startswith("scrypt:")):
        return check_password_hash(ADMIN_PASS, password)

    # Plain-text порівняння (для .env з простим паролем)
    return password == ADMIN_PASS
