#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Runner for Agro Marketplace
Запускає веб-панель і бота в одному Railway сервісі.
"""

import asyncio
import logging
import multiprocessing as mp
import os
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

web_process: mp.Process | None = None
bot_process: mp.Process | None = None


def terminate_process(proc: mp.Process | None, name: str) -> None:
    """Акуратно завершує дочірній процес."""
    if not proc or not proc.is_alive():
        return

    logger.info("🛑 Зупинка %s...", name)
    proc.terminate()
    proc.join(timeout=10)
    if proc.is_alive():
        logger.warning("⚠️ %s не завершився вчасно, kill", name)
        proc.kill()


def signal_handler(signum, frame):
    """Обробка сигналів для graceful shutdown."""
    logger.info("Отримано сигнал %s, зупиняємо сервіси...", signum)
    terminate_process(bot_process, "Bot")
    terminate_process(web_process, "Web")
    sys.exit(0)


def run_web_server():
    """Запуск веб-сервера (Gunicorn)."""
    try:
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
    """Запуск Telegram-бота через основний entrypoint."""
    try:
        from run_bot import main as bot_main

        logger.info("🤖 Запуск Telegram бота...")
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено")
    except Exception:
        logger.exception("❌ Критична помилка бота")
        sys.exit(1)


def main() -> int:
    global web_process, bot_process

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("🌾 Agro Marketplace - Unified Launcher")
    logger.info("=" * 60)

    web_process = mp.Process(target=run_web_server, name="WebServer", daemon=False)
    bot_process = mp.Process(target=run_bot_server, name="BotServer", daemon=False)

    web_process.start()
    time.sleep(2)
    bot_process.start()

    logger.info("✅ Веб та бот запущені")

    try:
        while True:
            if not web_process.is_alive():
                logger.error("❌ Web процес завершився (code=%s)", web_process.exitcode)
                terminate_process(bot_process, "Bot")
                return 1

            if not bot_process.is_alive():
                logger.error("❌ Bot процес завершився (code=%s)", bot_process.exitcode)
                terminate_process(web_process, "Web")
                return 1

            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("⏹ Отримано Ctrl+C")
        return 0
    finally:
        terminate_process(bot_process, "Bot")
        terminate_process(web_process, "Web")


if __name__ == "__main__":
    raise SystemExit(main())
