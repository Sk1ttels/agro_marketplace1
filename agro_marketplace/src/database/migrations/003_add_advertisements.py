"""
Міграція для додавання таблиць реклами
"""

def migrate(conn):
    """Додає таблиці для системи реклами"""
    
    # Таблиця реклами
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advertisements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            button_text TEXT,
            button_url TEXT,
            is_active INTEGER DEFAULT 1,
            show_frequency INTEGER DEFAULT 3,
            views_count INTEGER DEFAULT 0,
            clicks_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблиця перегляду реклами
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advertisement_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            clicked INTEGER DEFAULT 0,
            FOREIGN KEY (ad_id) REFERENCES advertisements(id)
        )
    """)
    
    # Індекси
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ad_active 
        ON advertisements(is_active)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ad_views_user 
        ON advertisement_views(user_id, ad_id)
    """)
    
    conn.commit()
    print("✅ Таблиці реклами створено")

if __name__ == "__main__":
    import sqlite3
    from pathlib import Path
    
    db_path = Path(__file__).parent.parent.parent / "data" / "agro_bot.db"
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
