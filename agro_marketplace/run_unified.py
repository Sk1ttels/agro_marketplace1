#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified Runner for Agro Marketplace (Railway)."""

import asyncio
import logging
import multiprocessing as mp
import os
import signal
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

web_process: mp.Process | None = None
bot_process: mp.Process | None = None
STOP_REQUESTED = False
BOT_RESTART_DELAY = int(os.getenv("BOT_RESTART_DELAY", "5"))


def terminate_process(proc: mp.Process | None, name: str) -> None:
    if not proc or not proc.is_alive():
        return
    logger.info("🛑 Зупинка %s...", name)
    proc.terminate()
    proc.join(timeout=10)
    if proc.is_alive():
        logger.warning("⚠️ %s не завершився вчасно, kill", name)
        proc.kill()


def signal_handler(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    logger.info("Отримано сигнал %s, зупиняємо сервіси...", signum)
    terminate_process(bot_process, "Bot")
    terminate_process(web_process, "Web")
    sys.exit(0)


def run_web_server():
    try:
        # Prevent duplicated bot startup when WSGI app is imported under unified mode.
        os.environ["ENABLE_WSGI_BOT_AUTOSTART"] = "0"

        import gunicorn.app.base

        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        from wsgi import app

        options = {
            "bind": f"0.0.0.0:{os.environ.get('PORT', 8080)}",
            "workers": 1,
            "worker_class": "sync",
            "timeout": 120,
            "keepalive": 5,
            "preload_app": True,
        }
        logger.info("🌐 Запуск веб-сервера на порту %s", os.environ.get("PORT", 8080))
        StandaloneApplication(app, options).run()
    except Exception:
        logger.exception("❌ Помилка веб-сервера")
        sys.exit(1)


def run_bot_server():
    try:
        from run_bot import main as bot_main

        logger.info("🤖 Запуск Telegram бота...")
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено")
    except Exception:
        logger.exception("❌ Критична помилка бота")
        sys.exit(1)


def start_web() -> mp.Process:
    proc = mp.Process(target=run_web_server, name="WebServer", daemon=False)
    proc.start()
    logger.info("✅ Web process started (pid=%s)", proc.pid)
    return proc


def start_bot() -> mp.Process:
    proc = mp.Process(target=run_bot_server, name="BotServer", daemon=False)
    proc.start()
    logger.info("✅ Bot process started (pid=%s)", proc.pid)
    return proc


def main() -> int:
    global web_process, bot_process
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("🌾 Agro Marketplace - Unified Launcher")
    logger.info("=" * 60)

    web_process = start_web()
    time.sleep(2)
    bot_process = start_bot()

    try:
        while not STOP_REQUESTED:
            if not web_process.is_alive():
                logger.error("❌ Web процес завершився (code=%s)", web_process.exitcode)
                terminate_process(bot_process, "Bot")
                return 1

            if not bot_process.is_alive():
                logger.error("⚠️ Bot процес завершився (code=%s), пробую перезапуск через %sс", bot_process.exitcode, BOT_RESTART_DELAY)
                time.sleep(BOT_RESTART_DELAY)
                bot_process = start_bot()

            time.sleep(2)
    finally:
        terminate_process(bot_process, "Bot")
        terminate_process(web_process, "Web")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
