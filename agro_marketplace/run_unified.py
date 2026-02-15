#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Runner for Agro Marketplace
Запускає веб-панель і бота в одному процесі
"""

import asyncio
import logging
import multiprocessing as mp
import os
import sys
import signal
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

web_process = None

def signal_handler(signum, frame):
    """Обробка сигналів для graceful shutdown"""
    logger.info("🛑 Отримано сигнал завершення, зупиняємо сервіси...")
    if web_process and web_process.is_alive():
        web_process.terminate()
        web_process.join(timeout=5)
        if web_process.is_alive():
            web_process.kill()
    sys.exit(0)

def run_web_server():
    """Запуск веб-сервера"""
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
            'bind': f'0.0.0.0:{os.environ.get("PORT", 8080)}',
            'workers': 1,
            'worker_class': 'sync',
            'timeout': 120,
            'keepalive': 5,
            'preload_app': True,
        }
        
        logger.info(f"🌐 Запуск веб-сервера на порту {os.environ.get('PORT', 8080)}")
        StandaloneApplication(app, options).run()
        
    except Exception as e:
        logger.error(f"❌ Помилка веб-сервера: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def run_bot_async():
    """Запуск бота асинхронно"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.bot_sync import main as bot_main
        
        logger.info("🤖 Запуск Telegram бота...")
        await bot_main()
        
    except Exception as e:
        logger.error(f"❌ Помилка бота: {e}")
        import traceback
        traceback.print_exc()
        raise

def run_bot():
    """Обгортка для запуску асинхронного бота"""
    try:
        asyncio.run(run_bot_async())
    except KeyboardInterrupt:
        logger.info("⏹ Бот зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Критична помилка бота: {e}")
        raise

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("="*60)
    logger.info("🌾 Agro Marketplace - Unified Launcher v2.0")
    logger.info("="*60)
    
    web_process = mp.Process(target=run_web_server, name="WebServer")
    web_process.daemon = False
    web_process.start()
    
    import time
    time.sleep(3)
    logger.info("✅ Веб-сервер запущено")
    
    try:
        logger.info("🚀 Запуск основного процесу бота...")
        run_bot()
    except KeyboardInterrupt:
        logger.info("⏹ Отримано сигнал зупинки...")
    finally:
        logger.info("🧹 Очищення ресурсів...")
        if web_process and web_process.is_alive():
            web_process.terminate()
            web_process.join(timeout=5)
            if web_process.is_alive():
                logger.warning("⚠️ Примусове завершення веб-процесу")
                web_process.kill()
        logger.info("✅ Завершення роботи")
