#!/usr/bin/env python3
"""Validate deploy-critical files and fail fast on merge markers/invalid config."""
from __future__ import annotations

import json
from pathlib import Path

MERGE_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
EXPECTED_START = "ENABLE_WSGI_BOT_AUTOSTART=0 . /opt/venv/bin/activate && python run_unified.py"


def ensure_no_markers(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    for marker in MERGE_MARKERS:
        if marker in raw:
            raise SystemExit(f"❌ {path} contains unresolved merge marker: {marker}")
    return raw


# 1) railway.json syntax + start command
railway_path = Path("railway.json")
railway_raw = ensure_no_markers(railway_path)

try:
    railway = json.loads(railway_raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"❌ Invalid JSON in {railway_path}: {exc}")

if not isinstance(railway, dict):
    raise SystemExit(f"❌ {railway_path} root must be a JSON object")

start = ((railway.get("deploy") or {}).get("startCommand") or "").strip()
if not start:
    raise SystemExit("❌ Missing deploy.startCommand in railway.json")
if start != EXPECTED_START:
    raise SystemExit(
        "❌ Unexpected deploy.startCommand in railway.json. "
        f"Expected: {EXPECTED_START!r}, got: {start!r}"
    )

# 2) Procfile start command parity
procfile_path = Path("Procfile")
procfile_raw = ensure_no_markers(procfile_path).strip()
expected_proc = f"web: {EXPECTED_START}"
if procfile_raw != expected_proc:
    raise SystemExit(
        "❌ Procfile does not match expected Railway start command. "
        f"Expected: {expected_proc!r}, got: {procfile_raw!r}"
    )

# 3) wsgi.py critical defaults
wsgi_path = Path("wsgi.py")
wsgi_raw = ensure_no_markers(wsgi_path)
if "from src.web_panel.app import create_app" not in wsgi_raw:
    raise SystemExit("❌ wsgi.py must import full app: from src.web_panel.app import create_app")
if "return False" not in wsgi_raw:
    raise SystemExit("❌ wsgi.py should keep WSGI bot autostart disabled by default (return False)")

print("✅ Deploy files are valid, marker-free, and mutually consistent")
