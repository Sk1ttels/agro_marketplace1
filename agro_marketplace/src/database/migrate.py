# -*- coding: utf-8 -*-
"""
Виправлена міграція для Agro Marketplace
Вирішує проблему з UNIQUE constraint
"""
import sqlite3
import os
from typing import List, Tuple, Dict


# Колонки для users (БЕЗ UNIQUE для telegram_id при ALTER TABLE)
USER_COLUMNS_CREATE: List[Tuple[str, str]] = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("telegram_id", "INTEGER UNIQUE"),
    ("username", "TEXT"),
    ("full_name", "TEXT"),
    ("phone", "TEXT"),
    ("role", "TEXT DEFAULT 'user'"),
    ("region", "TEXT"),
    ("company", "TEXT"),
    ("subscription_plan", "TEXT DEFAULT 'free'"),
    ("subscription_until", "TEXT"),
    ("is_banned", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
]

# Колонки для додавання (БЕЗ UNIQUE)
USER_COLUMNS_ALTER: List[Tuple[str, str]] = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("telegram_id", "INTEGER"),  # БЕЗ UNIQUE!
    ("username", "TEXT"),
    ("full_name", "TEXT"),
    ("phone", "TEXT"),
    ("role", "TEXT DEFAULT 'user'"),
    ("region", "TEXT"),
    ("company", "TEXT"),
    ("subscription_plan", "TEXT DEFAULT 'free'"),
    ("subscription_until", "TEXT"),
    ("is_banned", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
]

WEB_ADMINS_COLUMNS: List[Tuple[str, str]] = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("username", "TEXT UNIQUE NOT NULL"),
    ("password_hash", "TEXT NOT NULL"),
    ("email", "TEXT"),
    ("is_active", "INTEGER DEFAULT 1"),
    ("last_login", "TEXT"),
    ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
]

LOTS_COLUMNS: List[Tuple[str, str]] = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("owner_user_id", "INTEGER NOT NULL"),
    ("type", "TEXT NOT NULL"),
    ("crop", "TEXT NOT NULL"),
    ("volume", "REAL NOT NULL"),
    ("price", "REAL"),
    ("region", "TEXT NOT NULL"),
    ("status", "TEXT DEFAULT 'active'"),
    ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
]

SETTINGS_COLUMNS: List[Tuple[str, str]] = [
    ("key", "TEXT PRIMARY KEY"),
    ("value", "TEXT NOT NULL"),
]


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    """Перевіряє чи існує таблиця"""
    cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _table_info(cur: sqlite3.Cursor, table: str) -> Dict[str, str]:
    """Отримує інформацію про колонки таблиці"""
    try:
        cur.execute(f"PRAGMA table_info({table})")
        return {row[1]: row[2] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        return {}


def _ensure_table(cur: sqlite3.Cursor, table: str, cols: List[Tuple[str, str]]) -> None:
    """Створює таблицю якщо її немає"""
    cols_sql = ",\n        ".join([f"{name} {ddl}" for name, ddl in cols])
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {table} (
        {cols_sql}
    )
    """)


def _ensure_columns(cur: sqlite3.Cursor, table: str, cols: List[Tuple[str, str]]) -> int:
    """Додає відсутні колонки. Повертає кількість доданих колонок"""
    existing = _table_info(cur, table)
    added = 0

    for name, ddl in cols:
        if name in existing:
            continue

        try:
            # SQLite не підтримує UNIQUE в ALTER TABLE ADD COLUMN
            # Видаляємо UNIQUE з DDL
            ddl_clean = ddl.replace("UNIQUE", "").replace("NOT NULL", "").strip()

            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_clean}")
            added += 1
            print(f"  ✅ Додано колонку {table}.{name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                print(f"  ⚠️  Не вдалося додати {table}.{name}: {e}")

    return added


def _fix_telegram_id_unique(cur: sqlite3.Cursor) -> None:
    """Виправляє telegram_id - робить його унікальним через створення індексу"""
    try:
        # Створюємо унікальний індекс якщо його немає
        cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id
                        ON users(telegram_id)
                    """)
        print("  ✅ Створено унікальний індекс для telegram_id")
    except sqlite3.IntegrityError:
        print("  ⚠️  Є дублікати telegram_id, видаляємо старі записи...")
        # Видаляємо дублікати, залишаємо найновіший
        cur.execute("""
                    DELETE FROM users
                    WHERE id NOT IN (
                        SELECT MAX(id)
                        FROM users
                        GROUP BY telegram_id
                    )
                    """)
        # Пробуємо знову
        cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id
                        ON users(telegram_id)
                    """)
        print("  ✅ Дублікати видалено, індекс створено")


def migrate(db_path: str, verbose: bool = True) -> None:
    """
    Виконує міграцію бази даних

    Args:
        db_path: Шлях до файлу бази даних
        verbose: Виводити детальну інформацію
    """
    # Створюємо директорію якщо потрібно
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    if verbose:
        print(f"🔧 Міграція БД: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        total_added = 0

        # Таблиця users
        if verbose:
            print("\n📋 Таблиця users:")

        if not _table_exists(cur, "users"):
            # Таблиці немає - створюємо з UNIQUE
            _ensure_table(cur, "users", USER_COLUMNS_CREATE)
            print("  ✅ Створено нову таблицю users")
        else:
            # Таблиця є - додаємо колонки БЕЗ UNIQUE
            total_added += _ensure_columns(cur, "users", USER_COLUMNS_ALTER)
            # Виправляємо telegram_id через індекс
            _fix_telegram_id_unique(cur)

        # Таблиця web_admins
        if verbose:
            print("\n📋 Таблиця web_admins:")
        _ensure_table(cur, "web_admins", WEB_ADMINS_COLUMNS)
        total_added += _ensure_columns(cur, "web_admins", WEB_ADMINS_COLUMNS)

        # Таблиця lots
        if verbose:
            print("\n📋 Таблиця lots:")
        _ensure_table(cur, "lots", LOTS_COLUMNS)
        total_added += _ensure_columns(cur, "lots", LOTS_COLUMNS)

        # Таблиця settings
        if verbose:
            print("\n📋 Таблиця settings:")
        _ensure_table(cur, "settings", SETTINGS_COLUMNS)

        conn.commit()

        if verbose:
            print(f"\n✅ Міграція завершена! Додано {total_added} колонок")

    except Exception as e:
        print(f"❌ Помилка міграції: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Якщо запускається окремо - використати agro_bot.db
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/agro_bot.db"

    print("="*60)
    print("🌾 Agro Marketplace - Міграція БД (ВИПРАВЛЕНА)")
    print("="*60)

    migrate(db_path, verbose=True)

    print("\n🚀 Готово! Тепер можна запускати бота та веб-панель")
