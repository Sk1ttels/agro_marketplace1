# -*- coding: utf-8 -*-
"""
Bot settings (no pydantic) to avoid dependency/version issues.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import List

def _parse_int_list(raw: str) -> List[int]:
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out

@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    ADMIN_IDS: List[int]
    DB_FILE: str
    # Optional SQLAlchemy URL if you want it later
    DATABASE_URL: str

def load() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_ids = _parse_int_list(os.getenv("ADMIN_IDS", ""))
    db_file = os.getenv("DB_FILE", "data/agro_bot.db")
    db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{os.path.abspath(db_file)}")
    return Settings(BOT_TOKEN=bot_token, ADMIN_IDS=admin_ids, DB_FILE=db_file, DATABASE_URL=db_url)

settings = load()
