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

## Merge-conflict resolution defaults (important)

If GitHub shows conflicts in `wsgi.py`, `Procfile`, or `railway.json`, keep these values:

- `wsgi.py`:
  - import full app: `from src.web_panel.app import create_app`
  - default WSGI bot autostart disabled (`return False`), and enable only explicitly with `ENABLE_WSGI_BOT_AUTOSTART=1`.
- `Procfile`:
  - `web: ENABLE_WSGI_BOT_AUTOSTART=0 . /opt/venv/bin/activate && python run_unified.py`
- `railway.json`:
  - `"startCommand": "ENABLE_WSGI_BOT_AUTOSTART=0 . /opt/venv/bin/activate && python run_unified.py"`

This combination prevents duplicate Telegram polling instances (`TelegramConflictError`) and keeps web routes (`/contacts`, `/advertisements`) served by the full panel app.
### Quick conflict fix command
If GitHub shows conflicts in `Procfile`, `railway.json`, or `wsgi.py`, run:

```bash
python scripts/fix_deploy_conflicts.py
python scripts/validate_railway_json.py
```

Then commit and push. This removes accidental `<<<<<<< ======= >>>>>>>` markers and restores canonical startup config.