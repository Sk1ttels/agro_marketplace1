"""WSGI entrypoint for Agro Marketplace web panel (Railway/Gunicorn)."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
from pathlib import Path
import fcntl

codex/add-user-authentication-feature-9ekv34
from src.web_panel.app import create_app

from src.web_panel.app_sync import create_app
main

app = create_app()

_BOT_PROC: subprocess.Popen | None = None
_LOCK_FD = None
_LOCK_PATH = Path("/tmp/agro_marketplace_bot.lock")
_PID_PATH = Path("/tmp/agro_marketplace_bot.pid")


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _autostart_enabled() -> bool:
    flag = os.getenv("ENABLE_WSGI_BOT_AUTOSTART")
    if flag is not None:
        return flag.lower() in {"1", "true", "yes", "on"}

codex/add-user-authentication-feature-9ekv34
    # Default: disabled to avoid accidental duplicate polling bots.
    # Enable explicitly with ENABLE_WSGI_BOT_AUTOSTART=1 when needed.
    return False
  # Default: enabled on Railway only; disabled for local/dev by default.
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
 main


def _acquire_lock() -> bool:
    global _LOCK_FD

    try:
        _LOCK_PATH.touch(exist_ok=True)
        _LOCK_FD = open(_LOCK_PATH, "r+")
        fcntl.flock(_LOCK_FD.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except Exception:
        return False


def _spawn_bot_if_needed() -> None:
    global _BOT_PROC

    if not _autostart_enabled():
        return

    # If previous bot is alive, do not duplicate.
    if _PID_PATH.exists():
        try:
            existing_pid = int(_PID_PATH.read_text().strip())
            if _is_pid_alive(existing_pid):
                return
        except Exception:
            pass

    # Ensure only one Gunicorn process attempts to spawn the bot.
    if not _acquire_lock():
        return

    # Re-check after lock to avoid race.
    if _PID_PATH.exists():
        try:
            existing_pid = int(_PID_PATH.read_text().strip())
            if _is_pid_alive(existing_pid):
                return
        except Exception:
            pass

    _BOT_PROC = subprocess.Popen(
        ["python", "run_bot.py"],
        cwd=Path(__file__).resolve().parent,
        start_new_session=True,
    )
    _PID_PATH.write_text(str(_BOT_PROC.pid))


@atexit.register
def _cleanup_bot_process() -> None:
    global _BOT_PROC
    if _BOT_PROC and _BOT_PROC.poll() is None:
        _BOT_PROC.send_signal(signal.SIGTERM)


_spawn_bot_if_needed()
