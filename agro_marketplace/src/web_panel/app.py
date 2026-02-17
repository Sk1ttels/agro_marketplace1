# -*- coding: utf-8 -*-
"""
Agro Marketplace — Admin Web Panel
✅ Виправлено: дублікат context_processor
✅ Виправлено: init_schema() без параметрів
✅ Виправлено: всі роути з правильним закриттям з'єднань
✅ Додано: /api/ping, /api/db-check
"""

import csv
import datetime
import logging
from io import StringIO
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, Response,
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user,
)

from config.settings import FLASK_SECRET, ADMIN_USER, ADMIN_PASS, DB_PATH
from .db import get_conn, init_schema, get_setting, set_setting
from .auth import AdminUser, check_login

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Створення Flask додатку"""
    app = Flask(
        __name__,
        template_folder=str((Path(__file__).parent / "templates").resolve()),
        static_folder=str((Path(__file__).parent / "static").resolve()),
    )
    app.secret_key = FLASK_SECRET

    # Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message = "Будь ласка, увійдіть для доступу до цієї сторінки."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return AdminUser(user_id)

    # Ініціалізація схеми БД
    try:
        init_schema()
        logger.info("✅ DB schema initialized")
    except Exception as e:
        logger.error("DB init failed: %s", e)

    # Єдиний context_processor з дефолтними значеннями
    @app.context_processor
    def inject_defaults():
        return {
            "stats": {"users": 0, "lots": 0, "active_lots": 0, "banned": 0},
            "weekly_data": {
                "labels": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
                "new_users": [0, 0, 0, 0, 0, 0, 0],
                "new_lots":  [0, 0, 0, 0, 0, 0, 0],
            },
            "recent_lots": [],
        }

    # ============ ROUTES ============

    @app.get("/")
    def root():
        return redirect(url_for("dashboard"))

    # -------- Авторизація --------
    @app.get("/login")
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if check_login(username, password):
            login_user(AdminUser(username))
            flash("Успішний вхід! 👋", "success")
            return redirect(url_for("dashboard"))
        flash("Невірний логін або пароль ❌", "danger")
        return redirect(url_for("login"))

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Ви вийшли з системи", "info")
        return redirect(url_for("login"))

    # -------- Dashboard --------
    @app.get("/dashboard")
    @login_required
    def dashboard():
        conn = get_conn()
        try:
            stats = {"users": 0, "lots": 0, "active_lots": 0, "banned": 0}

            if _has_table(conn, "users"):
                try:
                    stats["users"] = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
                    if _has_col(conn, "users", "is_banned"):
                        stats["banned"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM users WHERE is_banned=1"
                        ).fetchone()["c"]
                except Exception:
                    pass

            if _has_table(conn, "lots"):
                try:
                    stats["lots"] = conn.execute("SELECT COUNT(*) AS c FROM lots").fetchone()["c"]
                    cols = _table_cols(conn, "lots")
                    if "status" in cols:
                        stats["active_lots"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE status IN ('active','open','published')"
                        ).fetchone()["c"]
                    elif "is_active" in cols:
                        stats["active_lots"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE is_active=1"
                        ).fetchone()["c"]
                except Exception:
                    pass

            # Тижнева статистика
            weekly_data = {
                "labels": [],
                "new_users": [0] * 7,
                "new_lots":  [0] * 7,
            }
            for i in range(6, -1, -1):
                d = datetime.datetime.now() - datetime.timedelta(days=i)
                weekly_data["labels"].append(["Пн","Вт","Ср","Чт","Пт","Сб","Нд"][d.weekday()])

            if _has_table(conn, "users") and _has_col(conn, "users", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            "SELECT COUNT(*) AS c FROM users WHERE date(created_at)=date('now','-'||?||' days')",
                            (i,)
                        ).fetchone()
                        weekly_data["new_users"][6 - i] = row["c"] if row else 0
                except Exception:
                    pass

            if _has_table(conn, "lots") and _has_col(conn, "lots", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE date(created_at)=date('now','-'||?||' days')",
                            (i,)
                        ).fetchone()
                        weekly_data["new_lots"][6 - i] = row["c"] if row else 0
                except Exception:
                    pass

            recent_lots = []
            if _has_table(conn, "lots"):
                try:
                    recent_lots = conn.execute("SELECT * FROM lots ORDER BY id DESC LIMIT 4").fetchall()
                except Exception:
                    pass

            return render_template(
                "dashboard.html",
                stats=stats,
                weekly_data=weekly_data,
                recent_lots=recent_lots,
            )
        finally:
            conn.close()

    # -------- Користувачі --------
    @app.get("/users")
    @login_required
    def users_page():
        q = request.args.get("q", "").strip()
        conn = get_conn()
        try:
            if not _has_table(conn, "users"):
                return render_template("users.html", rows=[], q=q)

            cols = _table_cols(conn, "users")
            where, params = [], []

            if q:
                search = []
                if "telegram_id" in cols:
                    search.append("CAST(telegram_id AS TEXT) LIKE ?")
                    params.append(f"%{q}%")
                if "username" in cols:
                    search.append("LOWER(COALESCE(username,'')) LIKE LOWER(?)")
                    params.append(f"%{q}%")
                if "full_name" in cols:
                    search.append("LOWER(COALESCE(full_name,'')) LIKE LOWER(?)")
                    params.append(f"%{q}%")
                if search:
                    where.append(f"({' OR '.join(search)})")

            sql = "SELECT * FROM users"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY id DESC LIMIT 300"

            rows = conn.execute(sql, tuple(params)).fetchall()
            return render_template("users.html", rows=rows, q=q)
        finally:
            conn.close()

    @app.get("/users/export")
    @login_required
    def users_export():
        conn = get_conn()
        try:
            if not _has_table(conn, "users"):
                flash("Таблиця користувачів не знайдена", "danger")
                return redirect(url_for("users_page"))
            users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        finally:
            conn.close()

        output = StringIO()
        if users:
            writer = csv.DictWriter(output, fieldnames=list(users[0].keys()))
            writer.writeheader()
            for u in users:
                writer.writerow(dict(u))
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=users_export.csv",
                     "Content-Type": "text/csv; charset=utf-8"},
        )

    @app.get("/users/<int:user_id>")
    @login_required
    def user_detail(user_id: int):
        conn = get_conn()
        try:
            if not _has_table(conn, "users"):
                flash("Таблиця користувачів не знайдена", "danger")
                return redirect(url_for("users_page"))
            user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                flash(f"Користувач #{user_id} не знайдений", "danger")
                return redirect(url_for("users_page"))
            lots = []
            if _has_table(conn, "lots"):
                lots = conn.execute(
                    "SELECT * FROM lots WHERE owner_user_id=? ORDER BY id DESC LIMIT 50",
                    (user_id,)
                ).fetchall()
        finally:
            conn.close()
        return render_template("user_detail.html", user=user, lots=lots)

    @app.post("/users/<int:user_id>/ban")
    @login_required
    def user_ban(user_id: int):
        conn = get_conn()
        try:
            if _has_table(conn, "users") and _has_col(conn, "users", "is_banned"):
                conn.execute("UPDATE users SET is_banned=1 WHERE id=?", (user_id,))
                conn.commit()
                flash("Користувача забанено ✅", "success")
            else:
                flash("Неможливо забанити: поле is_banned не знайдено ❌", "danger")
        except Exception as e:
            logger.error("Error banning user %s: %s", user_id, e)
            flash(f"Помилка: {e}", "danger")
            conn.rollback()
        finally:
            conn.close()
        return redirect(url_for("users_page"))

    @app.post("/users/<int:user_id>/unban")
    @login_required
    def user_unban(user_id: int):
        conn = get_conn()
        try:
            if _has_table(conn, "users") and _has_col(conn, "users", "is_banned"):
                conn.execute("UPDATE users SET is_banned=0 WHERE id=?", (user_id,))
                conn.commit()
                flash("Користувача розбанено ✅", "success")
            else:
                flash("Неможливо розбанити: поле is_banned не знайдено ❌", "danger")
        except Exception as e:
            logger.error("Error unbanning user %s: %s", user_id, e)
            flash(f"Помилка: {e}", "danger")
            conn.rollback()
        finally:
            conn.close()
        return redirect(url_for("users_page"))

    # -------- Лоти --------
    @app.get("/lots")
    @login_required
    def lots_page():
        status_filter = request.args.get("status", "").strip()
        conn = get_conn()
        try:
            if not _has_table(conn, "lots"):
                return render_template("lots.html", rows=[], status=status_filter, cols=[])
            cols = _table_cols(conn, "lots")
            sql = "SELECT * FROM lots"
            params = []
            if status_filter and "status" in cols:
                sql += " WHERE status=?"
                params.append(status_filter)
            sql += " ORDER BY id DESC LIMIT 500"
            rows = conn.execute(sql, tuple(params)).fetchall()
            return render_template("lots.html", rows=rows, status=status_filter, cols=cols)
        finally:
            conn.close()

    @app.get("/lots/export")
    @login_required
    def lots_export():
        conn = get_conn()
        try:
            if not _has_table(conn, "lots"):
                flash("Таблиця лотів не знайдена", "danger")
                return redirect(url_for("lots_page"))
            lots = conn.execute("SELECT * FROM lots ORDER BY id DESC").fetchall()
        finally:
            conn.close()
        if not lots:
            flash("Немає лотів для експорту", "warning")
            return redirect(url_for("lots_page"))
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=list(lots[0].keys()))
        writer.writeheader()
        for lot in lots:
            writer.writerow(dict(lot))
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=lots_export.csv"},
        )

    @app.get("/lots/<int:lot_id>")
    @login_required
    def lot_detail(lot_id: int):
        conn = get_conn()
        try:
            if not _has_table(conn, "lots"):
                flash("Таблиця лотів не знайдена", "danger")
                return redirect(url_for("lots_page"))
            lot = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
            if not lot:
                flash(f"Лот #{lot_id} не знайдений", "danger")
                return redirect(url_for("lots_page"))
            owner = None
            if _has_table(conn, "users") and lot["owner_user_id"]:
                owner = conn.execute(
                    "SELECT * FROM users WHERE id=?", (lot["owner_user_id"],)
                ).fetchone()
        finally:
            conn.close()
        return render_template("lot_detail.html", lot=lot, owner=owner)

    @app.post("/lots/<int:lot_id>/set_status")
    @login_required
    def lot_set_status(lot_id: int):
        new_status = request.form.get("status", "").strip()
        conn = get_conn()
        try:
            if _has_table(conn, "lots") and _has_col(conn, "lots", "status"):
                conn.execute("UPDATE lots SET status=? WHERE id=?", (new_status, lot_id))
                conn.commit()
                flash(f"Статус лота #{lot_id} змінено на '{new_status}' ✅", "success")
            else:
                flash("Неможливо змінити статус ❌", "danger")
        finally:
            conn.close()
        return redirect(url_for("lots_page"))

    @app.post("/lots/<int:lot_id>/close")
    @login_required
    def lot_close(lot_id: int):
        conn = get_conn()
        try:
            if _has_table(conn, "lots"):
                cols = _table_cols(conn, "lots")
                if "status" in cols:
                    conn.execute("UPDATE lots SET status='closed' WHERE id=?", (lot_id,))
                elif "is_closed" in cols:
                    conn.execute("UPDATE lots SET is_closed=1 WHERE id=?", (lot_id,))
                elif "is_active" in cols:
                    conn.execute("UPDATE lots SET is_active=0 WHERE id=?", (lot_id,))
                conn.commit()
                flash(f"Лот #{lot_id} закрито ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("lots_page"))

    @app.route("/lots/<int:lot_id>/activate", methods=["POST", "GET"])
    @login_required
    def lot_activate(lot_id: int):
        conn = get_conn()
        try:
            if _has_table(conn, "lots"):
                cols = _table_cols(conn, "lots")
                if "status" in cols:
                    conn.execute("UPDATE lots SET status='active' WHERE id=?", (lot_id,))
                elif "is_closed" in cols:
                    conn.execute("UPDATE lots SET is_closed=0 WHERE id=?", (lot_id,))
                elif "is_active" in cols:
                    conn.execute("UPDATE lots SET is_active=1 WHERE id=?", (lot_id,))
                conn.commit()
                flash(f"Лот #{lot_id} активовано ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("lots_page"))

    # -------- Контакти --------
    @app.get("/contacts")
    @login_required
    def contacts_page():
        conn = get_conn()
        try:
            if not _has_table(conn, "contacts"):
                return render_template("contacts.html", contacts=[])
            contacts = conn.execute("""
                SELECT c.id, c.user_id, c.contact_user_id, c.status, c.created_at,
                       u1.full_name as user_name, u1.username as user_username,
                       u1.telegram_id as user_telegram_id,
                       u2.full_name as contact_name, u2.username as contact_username,
                       u2.telegram_id as contact_telegram_id
                FROM contacts c
                LEFT JOIN users u1 ON c.user_id = u1.id
                LEFT JOIN users u2 ON c.contact_user_id = u2.id
                ORDER BY c.created_at DESC LIMIT 500
            """).fetchall()
            return render_template("contacts.html", contacts=contacts)
        finally:
            conn.close()

    # -------- Налаштування --------
    @app.get("/settings")
    @login_required
    def settings_page():
        s = {
            "platform_name": get_setting("platform_name", "Agro Marketplace"),
            "currency":       get_setting("currency", "UAH"),
            "min_price":      get_setting("min_price", "0"),
            "max_price":      get_setting("max_price", "999999"),
            "example_amount": get_setting("example_amount", "25т"),
            "auto_moderation":get_setting("auto_moderation", "0"),
        }
        return render_template("settings.html", s=s)

    @app.post("/settings/save")
    @login_required
    def settings_save():
        for key in ["platform_name", "currency", "min_price", "max_price", "example_amount"]:
            set_setting(key, request.form.get(key, ""))
        set_setting("auto_moderation", "1" if request.form.get("auto_moderation") else "0")
        flash("Налаштування збережено ✅", "success")
        return redirect(url_for("settings_page"))

    # -------- Синхронізація --------
    @app.get("/sync")
    @login_required
    def sync_page():
        conn = get_conn()
        try:
            stats = {"users_count": 0, "lots_count": 0}
            if _has_table(conn, "users"):
                stats["users_count"] = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            if _has_table(conn, "lots"):
                stats["lots_count"] = conn.execute("SELECT COUNT(*) AS c FROM lots").fetchone()["c"]
        finally:
            conn.close()
        return render_template("sync.html", unprocessed_events=[], total_processed=0, stats=stats)

    # -------- Реклама --------
    @app.get("/advertisements")
    @login_required
    def advertisements_page():
        conn = get_conn()
        try:
            ads = conn.execute("SELECT * FROM advertisements ORDER BY created_at DESC").fetchall()
            return render_template("advertisements.html", ads=ads)
        except Exception as e:
            logger.error("Advertisements error: %s", e)
            flash(f"Помилка: {e}", "danger")
            return render_template("advertisements.html", ads=[])
        finally:
            conn.close()

    @app.post("/advertisements/create")
    @login_required
    def create_advertisement():
        title          = request.form.get("title", "").strip()
        ad_type        = request.form.get("type", "text")
        content        = request.form.get("content", "").strip()
        image_url      = request.form.get("image_url", "").strip()
        button_text    = request.form.get("button_text", "").strip()
        button_url     = request.form.get("button_url", "").strip()
        show_frequency = int(request.form.get("show_frequency", 3))
        is_active      = 1 if request.form.get("is_active") else 0

        if not title or not content:
            flash("Назва та текст обов'язкові!", "danger")
            return redirect(url_for("advertisements_page"))

        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO advertisements
                (title, type, content, image_url, button_text, button_url, show_frequency, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, ad_type, content, image_url, button_text, button_url, show_frequency, is_active))
            conn.commit()
            flash("✅ Оголошення створено!", "success")
        except Exception as e:
            logger.error("Error creating ad: %s", e)
            flash(f"Помилка: {e}", "danger")
            conn.rollback()
        finally:
            conn.close()
        return redirect(url_for("advertisements_page"))

    @app.post("/advertisements/<int:ad_id>/toggle")
    @login_required
    def toggle_advertisement(ad_id: int):
        conn = get_conn()
        try:
            conn.execute("""
                UPDATE advertisements
                SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id=?
            """, (ad_id,))
            conn.commit()
            flash("✅ Статус оголошення змінено", "success")
        except Exception as e:
            flash(f"Помилка: {e}", "danger")
            conn.rollback()
        finally:
            conn.close()
        return redirect(url_for("advertisements_page"))

    @app.post("/advertisements/<int:ad_id>/delete")
    @login_required
    def delete_advertisement(ad_id: int):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM advertisement_views WHERE ad_id=?", (ad_id,))
            conn.execute("DELETE FROM advertisements WHERE id=?", (ad_id,))
            conn.commit()
            flash("✅ Оголошення видалено", "success")
        except Exception as e:
            flash(f"Помилка: {e}", "danger")
            conn.rollback()
        finally:
            conn.close()
        return redirect(url_for("advertisements_page"))

    # -------- API --------
    @app.get("/api/ping")
    def api_ping():
        return jsonify({"status": "ok", "message": "Web panel is alive"})

    @app.get("/api/db-check")
    @login_required
    def api_db_check():
        conn = get_conn()
        try:
            result = {
                "db_path":   str(DB_PATH),
                "db_exists": DB_PATH.exists(),
                "db_size":   DB_PATH.stat().st_size if DB_PATH.exists() else 0,
                "tables":    {},
            }
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for t in tables:
                name = t["name"]
                try:
                    count = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
                    result["tables"][name] = count
                except Exception as e:
                    result["tables"][name] = f"Error: {e}"
            return jsonify(result)
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)})
        finally:
            conn.close()

    @app.route("/api/sync", methods=["GET", "POST"])
    def api_sync():
        if request.method == "POST":
            data = request.get_json(silent=True)
            return jsonify({"status": "ok", "received": True, "data": data})
        return jsonify({"status": "ok", "message": "Sync endpoint ready"})

    return app


# ============ HELPERS ============

def _has_table(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return bool(row)


def _table_cols(conn, table: str) -> list:
    try:
        return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _has_col(conn, table: str, col: str) -> bool:
    return col in _table_cols(conn, table)


# ============ ЗАПУСК ============

if __name__ == "__main__":
    import os
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("🌾 Agro Marketplace - Web Panel")
    print("=" * 60)
    print(f"🔗 URL: http://0.0.0.0:{port}")
    print(f"👤 Login: {ADMIN_USER}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
