# -*- coding: utf-8 -*-
"""
Database helper для веб-панелі
Використовує ту саму БД що і бот
"""

import sqlite3
from pathlib import Path
from config.settings import DB_PATH


def get_conn() -> sqlite3.Connection:
    """Підключення до БД з row_factory"""
    # Створюємо директорію якщо потрібно
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    """Ініціалізація схеми БД (таблиці settings і web_admins)"""
    conn = get_conn()
    cur = conn.cursor()
    
    # Таблиця settings для налаштувань панелі
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Таблиця web_admins для адміністраторів панелі
    cur.execute("""
        CREATE TABLE IF NOT EXISTS web_admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            is_active INTEGER DEFAULT 1,
            last_login TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    """Отримати значення налаштування"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except sqlite3.OperationalError:
        return default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """Встановити значення налаштування"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()
