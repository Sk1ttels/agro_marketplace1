# -*- coding: utf-8 -*-
"""
Конфігураційні налаштування для Agro Marketplace Bot
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Завантаження .env файлу з кореня проекту
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=env_path)

# Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print('⚠️ BOT_TOKEN не задано (web-панель може працювати, бот — ні)')
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',') if id.strip().isdigit()]

# ============ ВИПРАВЛЕННЯ БД - СИНХРОНІЗАЦІЯ ============
# База даних - ЄДИНА для бота і веб-панелі
DB_FILE = os.getenv('DB_FILE', 'data/agro_bot.db')

# Створюємо правильний шлях
if os.path.isabs(DB_FILE):
    # Абсолютний шлях (Railway: /app/data/agro_bot.db)
    DB_PATH = Path(DB_FILE)
else:
    # Відносний шлях - відносно PROJECT_ROOT
    DB_PATH = PROJECT_ROOT / DB_FILE

# КРИТИЧНО: Створюємо директорію data/ якщо не існує
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Логування для діагностики
print(f"✅ БД буде використовуватись: {DB_PATH}")
print(f"✅ БД існує: {DB_PATH.exists()}")
print(f"✅ Розмір БД: {DB_PATH.stat().st_size if DB_PATH.exists() else 0} bytes")
# =======================================================

# Flask Web Panel
FLASK_SECRET = os.getenv('FLASK_SECRET', 'super-secret-key-change-me')
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin123')

# Логування
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
# SQLAlchemy-compatible settings object (for engine.py)
class _Settings:
    @property
    def DATABASE_URL(self):
        return f"sqlite+aiosqlite:///{DB_PATH}"

settings = _Settings()

# DATABASE_URL alias
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
