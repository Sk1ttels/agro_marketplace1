# Railway Quickstart (2 services)

This repo contains a Telegram bot (worker) and a Flask web panel (web).

## 1) Create TWO services from the same GitHub repo

### A) Web service (Web Panel)
- Install: `pip install -r requirements.txt`
- Start: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`
- Variables (at minimum):
  - `BOT_TOKEN`
  - `ADMIN_IDS`
  - `DB_FILE` (default: `data/agro_bot.db`)
  - `FLASK_SECRET`
  - `ADMIN_USER`
  - `ADMIN_PASS`

### B) Worker service (Telegram bot)
- Install: `pip install -r requirements.txt`
- Start: `python run_bot.py`
- Variables:
  - `BOT_TOKEN`
  - `ADMIN_IDS`
  - `DB_FILE`

## Notes
- Railway provides `PORT` automatically for the web service.
- SQLite file lives inside the container filesystem. If you redeploy, the DB may reset unless you use a volume.


## Single-service mode (one Railway service for bot + web)

If you want Railway to run **both** the Flask site and Telegram bot in one container, use:

- Start: `python run_unified.py`
- In this repo it is already configured in `railway.json` as:
  - `. /opt/venv/bin/activate && python run_unified.py`

This mode is simpler to deploy, but if one process crashes the whole service restarts.
- `run_unified.py` запускає web через `wsgi:app` і бота через `run_bot.py`, тож працюють всі основні middleware/handlers.
