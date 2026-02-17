#!/usr/bin/env python3
"""Validate railway.json and fail fast on merge markers or invalid JSON."""
from __future__ import annotations

import json
from pathlib import Path

p = Path('railway.json')
raw = p.read_text(encoding='utf-8')

for marker in ('<<<<<<<', '=======', '>>>>>>>'):
    if marker in raw:
        raise SystemExit(f"❌ {p} contains unresolved merge marker: {marker}")

try:
    parsed = json.loads(raw)
except json.JSONDecodeError as e:
    raise SystemExit(f"❌ Invalid JSON in {p}: {e}")

if not isinstance(parsed, dict):
    raise SystemExit(f"❌ {p} root must be a JSON object")

if 'deploy' not in parsed or 'startCommand' not in parsed.get('deploy', {}):
    raise SystemExit("❌ Missing deploy.startCommand in railway.json")

print('✅ railway.json is valid and merge-marker free')
