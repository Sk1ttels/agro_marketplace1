#!/usr/bin/env python3
"""Auto-fix canonical deploy files after bad web conflict resolutions.

This script rewrites Procfile and railway.json to canonical values and
sanitizes simple merge-marker blocks in wsgi.py for known conflict zones.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

EXPECTED_START = "ENABLE_WSGI_BOT_AUTOSTART=0 . /opt/venv/bin/activate && python run_unified.py"


def rewrite_procfile() -> None:
    Path("Procfile").write_text(f"web: {EXPECTED_START}\n", encoding="utf-8")


def rewrite_railway_json() -> None:
    payload = {
        "$schema": "https://railway.app/railway.schema.json",
        "build": {"builder": "NIXPACKS", "nixpacksConfigPath": "nixpacks.toml"},
        "deploy": {"startCommand": EXPECTED_START},
    }
    Path("railway.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_wsgi() -> None:
    p = Path("wsgi.py")
    raw = p.read_text(encoding="utf-8")

    # Resolve common import conflict by forcing full app import.
    raw = re.sub(
        r"from\s+src\.web_panel\.(?:app_sync|app)\s+import\s+create_app",
        "from src.web_panel.app import create_app",
        raw,
    )

    # If generic merge markers slipped in, drop them and keep code lines.
    cleaned = []
    for line in raw.splitlines():
        if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            continue
        cleaned.append(line)
    raw = "\n".join(cleaned) + "\n"

    # Keep default explicit-safe behavior.
    raw = raw.replace(
        "# Default: enabled on Railway only; disabled for local/dev by default.\n    return bool(os.getenv(\"RAILWAY_ENVIRONMENT\") or os.getenv(\"RAILWAY_PROJECT_ID\"))",
        "# Default: disabled to avoid accidental duplicate polling bots.\n    # Enable explicitly with ENABLE_WSGI_BOT_AUTOSTART=1 when needed.\n    return False",
    )

    p.write_text(raw, encoding="utf-8")


def main() -> None:
    rewrite_procfile()
    rewrite_railway_json()
    sanitize_wsgi()
    print("✅ Deploy conflict-prone files normalized: Procfile, railway.json, wsgi.py")


if __name__ == "__main__":
    main()
