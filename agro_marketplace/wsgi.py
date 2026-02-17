"""WSGI entrypoint for Agro Marketplace web panel."""

from __future__ import annotations
import os
import atexit
import signal
import subprocess
from pathlib import Path

from src.web_panel.app import create_app

app = create_app()

_BOT_PROC: subprocess.Popen | None = None


def _autostart_enabled() -> bool:
    flag = os.getenv("ENABLE_WSGI_BOT_AUTOSTART")
    if flag is not None:
        return flag.lower() in {"1", "true", "yes", "on"}
    return False


def _spawn_bot_if_needed() -> None:
    global _BOT_PROC
    if not _autostart_enabled():
        return
    _BOT_PROC = subprocess.Popen(
        ["python", "run_bot.py"],
        cwd=Path(__file__).resolve().parent,
        start_new_session=True,
    )


@atexit.register
def _cleanup_bot_process() -> None:
    global _BOT_PROC
    if _BOT_PROC and _BOT_PROC.poll() is None:
        _BOT_PROC.send_signal(signal.SIGTERM)


_spawn_bot_if_needed()
