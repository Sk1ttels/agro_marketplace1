import os
from dotenv import load_dotenv

# Load .env from project root (current working directory)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db").strip()
DB_FILE = DB_FILE.replace("\\", "/")

ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

WEB_ADMIN_USER = os.getenv("ADMIN_USER", "admin").strip()
WEB_ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123").strip()
FLASK_SECRET  = os.getenv("FLASK_SECRET", "super-secret-key-change-me").strip()
