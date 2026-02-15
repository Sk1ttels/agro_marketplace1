"""WSGI entrypoint for Agro Marketplace web panel (Railway/Gunicorn)."""

from src.web_panel.app_sync import create_app

app = create_app()
