from __future__ import annotations

import json
import subprocess
from pathlib import Path

EXPECTED_START = "ENABLE_WSGI_BOT_AUTOSTART=0 . /opt/venv/bin/activate && python run_unified.py"


def ensure_repo_no_markers() -> None:
    """Fail if any tracked text file contains unresolved merge markers."""
    try:
        files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    except Exception as exc:
        raise SystemExit(f"❌ Failed to list git files: {exc}")

    bad_hits: list[tuple[str, int, str]] = []

    for rel in files:
        path = Path(rel)
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            # Skip non-text/binary files
            continue

        for ln, line in enumerate(raw.splitlines(), start=1):
            s = line.strip()
            if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> ") or s == "=======":
                bad_hits.append((rel, ln, line[:40]))

    if bad_hits:
        preview = "\n".join(f"  - {f}:{ln}: {snippet}" for f, ln, snippet in bad_hits[:20])
        raise SystemExit("❌ Found unresolved merge markers in repository files:\n" + preview)



def ensure_no_markers(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> ") or s == "=======":
            raise SystemExit(f"❌ {path} contains unresolved merge marker: {line[:40]}")
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

ensure_repo_no_markers()

print("✅ Deploy files and repository are marker-free and mutually consistent")

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