# -*- coding: utf-8 -*-
"""Database helper для веб-панелі. Використовує ту саму БД що і бот."""

import sqlite3
from pathlib import Path
from config.settings import DB_PATH


def get_conn() -> sqlite3.Connection:
    """Підключення до БД з row_factory"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # безпечно для multi-process
    return conn


def init_schema() -> None:
    """Ініціалізація схеми БД (таблиці settings, web_admins, advertisements)"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS web_admins (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email         TEXT,
            is_active     INTEGER DEFAULT 1,
            last_login    TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS advertisements (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            type           TEXT NOT NULL DEFAULT 'text',
            content        TEXT NOT NULL,
            image_url      TEXT,
            button_text    TEXT,
            button_url     TEXT,
            is_active      INTEGER DEFAULT 1,
            show_frequency INTEGER DEFAULT 3,
            views_count    INTEGER DEFAULT 0,
            clicks_count   INTEGER DEFAULT 0,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS advertisement_views (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id      INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            viewed_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            clicked    INTEGER DEFAULT 0,
            FOREIGN KEY (ad_id) REFERENCES advertisements(id)
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
