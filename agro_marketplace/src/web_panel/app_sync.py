# -*- coding: utf-8 -*-
"""Agro Marketplace — Admin Web Panel (Synchronized Version)

✅ One DB for bot + web (reads DB_FILE from .env via config.settings)
✅ Modern UI (sidebar + cards)
✅ Users: search, ban/unban with sync
✅ Lots: list + close/activate with sync
✅ Settings: key/value stored in SQLite with sync
✅ Real-time synchronization with Telegram bot

Run (from project root):
    python -m src.web_panel.app

Open:
    http://127.0.0.1:5000
"""

from __future__ import annotations
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config.settings import FLASK_SECRET, ADMIN_USER, ADMIN_PASS
from .db import (
    get_conn,
    init_schema,
    get_setting,
    set_setting,
)

from .auth import AdminUser, check_login
from bot.services.sync_service import FileBasedSync

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str((Path(__file__).parent / "templates").resolve()),
        static_folder=str((Path(__file__).parent / "static").resolve()),
    )
    app.secret_key = FLASK_SECRET

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return AdminUser(user_id)

    # Ensure required tables exist (settings/web_admins)
    init_schema()

    @app.get("/")
    def root():
        return redirect(url_for("dashboard"))

    # -------- Auth --------
    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if check_login(username, password):
            login_user(AdminUser(username))
            return redirect(url_for("dashboard"))
        flash("Невірний логін або пароль", "danger")
        return redirect(url_for("login"))

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # -------- Dashboard --------
    @app.get("/dashboard")
    @login_required
    def dashboard():
        conn = get_conn()
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] if _has_table(conn, "users") else 0
        lots = conn.execute("SELECT COUNT(*) AS c FROM lots").fetchone()["c"] if _has_table(conn, "lots") else 0
        banned = (
            conn.execute("SELECT COUNT(*) AS c FROM users WHERE is_banned=1").fetchone()["c"]
            if _has_table(conn, "users") and _has_col(conn, "users", "is_banned")
            else 0
        )
        
        # Get recent activity stats
        active_lots = conn.execute(
            "SELECT COUNT(*) AS c FROM lots WHERE status='active'"
        ).fetchone()["c"] if _has_table(conn, "lots") else 0
        
        total_offers = conn.execute(
            "SELECT COUNT(*) AS c FROM offers"
        ).fetchone()["c"] if _has_table(conn, "offers") else 0
        
        conn.close()
        return render_template(
            "dashboard.html", 
            users=users, 
            lots=lots, 
            banned=banned,
            active_lots=active_lots,
            total_offers=total_offers
        )

    # -------- Users --------
    @app.get("/users")
    @login_required
    def users_page():
        q = request.args.get("q", "").strip()
        conn = get_conn()
        if not _has_table(conn, "users"):
            conn.close()
            return render_template("users.html", rows=[], q=q)

        # try best-effort search fields
        cols = _table_cols(conn, "users")
        where = []
        params = []
        if q:
            if "telegram_id" in cols:
                where.append("CAST(telegram_id AS TEXT) LIKE ?")
                params.append(f"%{q}%")
            if "phone" in cols:
                where.append("COALESCE(phone,'') LIKE ?")
                params.append(f"%{q}%")
            if "company" in cols:
                where.append("COALESCE(company,'') LIKE ?")
                params.append(f"%{q}%")

        sql = "SELECT * FROM users"
        if where:
            sql += " WHERE " + " OR ".join(where)
        sql += " ORDER BY id DESC LIMIT 300"

        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        return render_template("users.html", rows=rows, q=q)

    @app.post("/users/<int:user_id>/ban")
    @login_required
    def user_ban(user_id: int):
        conn = get_conn()
        if _has_table(conn, "users") and _has_col(conn, "users", "is_banned"):
            # Get telegram_id before ban
            user = conn.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,)).fetchone()
            telegram_id = user["telegram_id"] if user else None
            
            # Ban user
            conn.execute("UPDATE users SET is_banned=1 WHERE id=?", (user_id,))
            conn.commit()
            
            # Emit sync event
            if telegram_id:
                FileBasedSync.write_event('user_banned', {
                    'user_id': user_id,
                    'telegram_id': telegram_id
                })
            
        conn.close()
        flash("Користувача забанено ✅", "success")
        return redirect(url_for("users_page"))

    @app.post("/users/<int:user_id>/unban")
    @login_required
    def user_unban(user_id: int):
        conn = get_conn()
        if _has_table(conn, "users") and _has_col(conn, "users", "is_banned"):
            # Get telegram_id before unban
            user = conn.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,)).fetchone()
            telegram_id = user["telegram_id"] if user else None
            
            # Unban user
            conn.execute("UPDATE users SET is_banned=0 WHERE id=?", (user_id,))
            conn.commit()
            
            # Emit sync event
            if telegram_id:
                FileBasedSync.write_event('user_unbanned', {
                    'user_id': user_id,
                    'telegram_id': telegram_id
                })
            
        conn.close()
        flash("Користувача розбанено ✅", "success")
        return redirect(url_for("users_page"))

    # -------- Lots --------
    @app.get("/lots")
    @login_required
    def lots_page():
        status = request.args.get("status", "").strip()
        conn = get_conn()
        if not _has_table(conn, "lots"):
            conn.close()
            return render_template("lots.html", rows=[], status=status)

        cols = _table_cols(conn, "lots")
        
        # Join with users to get owner info
        sql = """
            SELECT lots.*, users.telegram_id as owner_telegram_id, users.phone as owner_phone
            FROM lots
            LEFT JOIN users ON lots.owner_user_id = users.id
        """
        params = []
        if status and "status" in cols:
            sql += " WHERE lots.status=?"
            params.append(status)
        sql += " ORDER BY lots.id DESC LIMIT 500"

        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        return render_template("lots.html", rows=rows, status=status, cols=cols)

    @app.post("/lots/<int:lot_id>/set_status")
    @login_required
    def lot_set_status(lot_id: int):
        new_status = request.form.get("status", "").strip()
        conn = get_conn()
        if _has_table(conn, "lots") and _has_col(conn, "lots", "status"):
            # Get lot owner's telegram_id
            lot = conn.execute("""
                SELECT users.telegram_id 
                FROM lots 
                JOIN users ON lots.owner_user_id = users.id 
                WHERE lots.id=?
            """, (lot_id,)).fetchone()
            
            owner_telegram_id = lot["telegram_id"] if lot else None
            
            # Update status
            conn.execute("UPDATE lots SET status=? WHERE id=?", (new_status, lot_id))
            conn.commit()
            
            # Emit sync event
            if owner_telegram_id:
                FileBasedSync.write_event('lot_status_changed', {
                    'lot_id': lot_id,
                    'new_status': new_status,
                    'owner_telegram_id': owner_telegram_id
                })
            
        conn.close()
        flash("Статус лота оновлено ✅", "success")
        return redirect(url_for("lots_page"))

    # -------- Settings --------
    @app.get("/settings")
    @login_required
    def settings_page():
        s = {
            "platform_name": get_setting("platform_name", "Agro Marketplace"),
            "currency": get_setting("currency", "UAH"),
            "min_price": get_setting("min_price", "0"),
            "max_price": get_setting("max_price", "999999"),
            "example_amount": get_setting("example_amount", "25т"),
            "auto_moderation": get_setting("auto_moderation", "0"),
        }
        return render_template("settings.html", s=s)

    @app.post("/settings/save")
    @login_required
    def settings_save():
        settings_changed = {}
        
        # Save each setting and track changes
        for key in ["platform_name", "currency", "min_price", "max_price", "example_amount"]:
            old_value = get_setting(key, "")
            new_value = request.form.get(key, "")
            if old_value != new_value:
                set_setting(key, new_value)
                settings_changed[key] = new_value
        
        # Auto moderation
        auto_mod_new = "1" if request.form.get("auto_moderation") else "0"
        auto_mod_old = get_setting("auto_moderation", "0")
        if auto_mod_new != auto_mod_old:
            set_setting("auto_moderation", auto_mod_new)
            settings_changed["auto_moderation"] = auto_mod_new
        
        # Emit sync event for changed settings
        if settings_changed:
            FileBasedSync.write_event('settings_changed', {
                'changed': settings_changed
            })
        
        flash("Налаштування збережено ✅", "success")
        return redirect(url_for("settings_page"))

    # -------- Sync Status --------
    @app.get("/sync")
    @login_required
    def sync_page():
        """Page to monitor synchronization status"""
        try:
            events = FileBasedSync.read_unprocessed_events()
            processed_count = 0
            
            sync_file = FileBasedSync.SYNC_FILE
            if sync_file.exists():
                import json
                with open(sync_file, 'r') as f:
                    all_events = json.load(f)
                    processed_count = sum(1 for e in all_events if e.get('processed', False))
            
            return render_template(
                "sync.html", 
                unprocessed_events=events,
                total_processed=processed_count
            )
        except Exception as e:
            flash(f"Помилка завантаження синхронізації: {e}", "danger")
            return render_template("sync.html", unprocessed_events=[], total_processed=0)

    return app


# -------- helpers --------
def _has_table(conn, table: str) -> bool:
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(r)


def _table_cols(conn, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _has_col(conn, table: str, col: str) -> bool:
    return col in _table_cols(conn, table)


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
