# -*- coding: utf-8 -*-
"""
Agro Marketplace — Admin Web Panel
✅ Синхронізація з ботом через спільну SQLite БД + JSON-файл подій
✅ Бот отримує сповіщення про бан/розбан/зміну лота через FileBasedSync
✅ Єдиний context_processor, правильне закриття з'єднань
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

# Імпорт FileBasedSync для відправки подій боту
try:
    from src.bot.services.sync_service import FileBasedSync
except ImportError:
    # Fallback якщо запускається не з кореня проекту
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from src.bot.services.sync_service import FileBasedSync
    except ImportError:
        class FileBasedSync:
            """Заглушка якщо sync_service недоступний"""
            @classmethod
            def write_event(cls, *a, **kw): pass
            @classmethod
            def read_unprocessed_events(cls): return []

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
    login_manager.login_message = "Будь ласка, увійдіть для доступу."
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

    # Єдиний context_processor
    @app.context_processor
    def inject_defaults():
        return {
            "stats": {"users": 0, "lots": 0, "active_lots": 0, "banned": 0},
            "weekly_data": {
                "labels": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
                "new_users": [0] * 7,
                "new_lots":  [0] * 7,
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

            weekly_data = {"labels": [], "new_users": [0] * 7, "new_lots": [0] * 7}
            for i in range(6, -1, -1):
                d = datetime.datetime.now() - datetime.timedelta(days=i)
                weekly_data["labels"].append(["Пн","Вт","Ср","Чт","Пт","Сб","Нд"][d.weekday()])

            if _has_table(conn, "users") and _has_col(conn, "users", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            "SELECT COUNT(*) AS c FROM users WHERE date(created_at)=date('now','-'||?||' days')", (i,)
                        ).fetchone()
                        weekly_data["new_users"][6 - i] = row["c"] if row else 0
                except Exception:
                    pass

            if _has_table(conn, "lots") and _has_col(conn, "lots", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE date(created_at)=date('now','-'||?||' days')", (i,)
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

            return render_template("dashboard.html", stats=stats, weekly_data=weekly_data, recent_lots=recent_lots)
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
                    search.append("CAST(telegram_id AS TEXT) LIKE ?"); params.append(f"%{q}%")
                if "username" in cols:
                    search.append("LOWER(COALESCE(username,'')) LIKE LOWER(?)"); params.append(f"%{q}%")
                if "full_name" in cols:
                    search.append("LOWER(COALESCE(full_name,'')) LIKE LOWER(?)"); params.append(f"%{q}%")
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
                flash("Таблиця не знайдена", "danger")
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
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=users_export.csv",
                                 "Content-Type": "text/csv; charset=utf-8"})

    @app.get("/users/<int:user_id>")
    @login_required
    def user_detail(user_id: int):
        conn = get_conn()
        try:
            if not _has_table(conn, "users"):
                flash("Таблиця не знайдена", "danger")
                return redirect(url_for("users_page"))
            user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                flash(f"Користувач #{user_id} не знайдений", "danger")
                return redirect(url_for("users_page"))
            lots = []
            if _has_table(conn, "lots"):
                lots = conn.execute(
                    "SELECT * FROM lots WHERE owner_user_id=? ORDER BY id DESC LIMIT 50", (user_id,)
                ).fetchall()
        finally:
            conn.close()
        return render_template("user_detail.html", user=user, lots=lots)

    @app.post("/users/<int:user_id>/set_subscription")
    @login_required
    def user_set_subscription(user_id: int):
        plan = request.form.get("plan", "free")
        if plan not in ("free", "basic", "premium", "business"):
            flash("Невірний план", "danger")
            return redirect(url_for("user_detail", user_id=user_id))
        conn = get_conn()
        try:
            cols = _table_cols(conn, "users")
            if "subscription_plan" in cols:
                conn.execute(
                    "UPDATE users SET subscription_plan=? WHERE id=?",
                    (plan, user_id)
                )
                conn.commit()
                flash(f"✅ Підписку змінено на '{plan}'", "success")
            else:
                flash("Колонка subscription_plan відсутня в БД", "warning")
        except Exception as e:
            flash(f"Помилка: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for("user_detail", user_id=user_id))

    @app.post("/users/<int:user_id>/ban")
    @login_required
    def user_ban(user_id: int):
        """Бан користувача + сповіщення бота через FileBasedSync"""
        conn = get_conn()
        try:
            if not _has_table(conn, "users") or not _has_col(conn, "users", "is_banned"):
                flash("Неможливо забанити ❌", "danger")
                return redirect(url_for("users_page"))

            # Отримуємо telegram_id ДО оновлення
            user = conn.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,)).fetchone()
            telegram_id = user["telegram_id"] if user else None

            conn.execute("UPDATE users SET is_banned=1 WHERE id=?", (user_id,))
            conn.commit()
            flash("Користувача забанено ✅", "success")

            # Відправляємо подію боту — він сповістить користувача в Telegram
            if telegram_id:
                FileBasedSync.write_event("user_banned", {
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                })
                logger.info("Sync event 'user_banned' sent for telegram_id=%s", telegram_id)

        except Exception as e:
            logger.error("Error banning user %s: %s", user_id, e)
            flash(f"Помилка: {e}", "danger")
            try: conn.rollback()
            except Exception: pass
        finally:
            conn.close()
        return redirect(url_for("users_page"))

    @app.post("/users/<int:user_id>/unban")
    @login_required
    def user_unban(user_id: int):
        """Розбан користувача + сповіщення бота"""
        conn = get_conn()
        try:
            if not _has_table(conn, "users") or not _has_col(conn, "users", "is_banned"):
                flash("Неможливо розбанити ❌", "danger")
                return redirect(url_for("users_page"))

            user = conn.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,)).fetchone()
            telegram_id = user["telegram_id"] if user else None

            conn.execute("UPDATE users SET is_banned=0 WHERE id=?", (user_id,))
            conn.commit()
            flash("Користувача розбанено ✅", "success")

            if telegram_id:
                FileBasedSync.write_event("user_unbanned", {
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                })
                logger.info("Sync event 'user_unbanned' sent for telegram_id=%s", telegram_id)

        except Exception as e:
            logger.error("Error unbanning user %s: %s", user_id, e)
            flash(f"Помилка: {e}", "danger")
            try: conn.rollback()
            except Exception: pass
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
                flash("Таблиця не знайдена", "danger")
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
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=lots_export.csv"})

    @app.get("/lots/<int:lot_id>")
    @login_required
    def lot_detail(lot_id: int):
        conn = get_conn()
        try:
            if not _has_table(conn, "lots"):
                flash("Таблиця не знайдена", "danger")
                return redirect(url_for("lots_page"))
            lot = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
            cols_lots = _table_cols(conn, "lots")
            if not lot:
                flash(f"Лот #{lot_id} не знайдений", "danger")
                return redirect(url_for("lots_page"))
            owner = None
            if _has_table(conn, "users") and lot["owner_user_id"]:
                owner = conn.execute("SELECT * FROM users WHERE id=?", (lot["owner_user_id"],)).fetchone()
        finally:
            conn.close()
        return render_template("lot_detail.html", lot=lot, owner=owner, cols=cols_lots)

    def _notify_lot_status(conn, lot_id: int, new_status: str):
        """Відправляє sync-подію боту при зміні статусу лота"""
        try:
            if _has_table(conn, "users"):
                row = conn.execute("""
                    SELECT u.telegram_id FROM lots l
                    JOIN users u ON l.owner_user_id = u.id
                    WHERE l.id=?
                """, (lot_id,)).fetchone()
                if row and row["telegram_id"]:
                    FileBasedSync.write_event("lot_status_changed", {
                        "lot_id": lot_id,
                        "new_status": new_status,
                        "owner_telegram_id": row["telegram_id"],
                    })
        except Exception as e:
            logger.error("Failed to send lot sync event: %s", e)

    @app.post("/lots/<int:lot_id>/set_status")
    @login_required
    def lot_set_status(lot_id: int):
        new_status = request.form.get("status", "").strip()
        conn = get_conn()
        try:
            if _has_table(conn, "lots") and _has_col(conn, "lots", "status"):
                conn.execute("UPDATE lots SET status=? WHERE id=?", (new_status, lot_id))
                conn.commit()
                _notify_lot_status(conn, lot_id, new_status)
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
                _notify_lot_status(conn, lot_id, "closed")
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
                _notify_lot_status(conn, lot_id, "active")
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
                       u1.full_name as user_name, u1.username as user_username, u1.telegram_id as user_telegram_id,
                       u2.full_name as contact_name, u2.username as contact_username, u2.telegram_id as contact_telegram_id
                FROM contacts c
                LEFT JOIN users u1 ON c.user_id=u1.id
                LEFT JOIN users u2 ON c.contact_user_id=u2.id
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
            "platform_name":  get_setting("platform_name", "Agro Marketplace"),
            "currency":        get_setting("currency", "UAH"),
            "min_price":       get_setting("min_price", "0"),
            "max_price":       get_setting("max_price", "999999"),
            "example_amount":  get_setting("example_amount", "25т"),
            "auto_moderation": get_setting("auto_moderation", "0"),
        }
        return render_template("settings.html", s=s)

    @app.post("/settings/save")
    @login_required
    def settings_save():
        for key in ["platform_name", "currency", "min_price", "max_price", "example_amount"]:
            set_setting(key, request.form.get(key, ""))
        set_setting("auto_moderation", "1" if request.form.get("auto_moderation") else "0")
        # Сповіщаємо бота про зміну налаштувань
        FileBasedSync.write_event("settings_changed", {"changed": True})
        flash("Налаштування збережено ✅", "success")
        return redirect(url_for("settings_page"))

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

    @app.post("/advertisements/<int:ad_id>/edit")
    @login_required
    def edit_advertisement(ad_id: int):
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
                UPDATE advertisements
                SET title=?, type=?, content=?, image_url=?, button_text=?, button_url=?,
                    show_frequency=?, is_active=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (title, ad_type, content, image_url, button_text, button_url,
                  show_frequency, is_active, ad_id))
            conn.commit()
            flash("✅ Оголошення оновлено!", "success")
        except Exception as e:
            logger.error("Error editing ad: %s", e)
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
                SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END, updated_at=CURRENT_TIMESTAMP
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

    @app.post("/sync/clear")
    @login_required
    def sync_clear():
        try:
            FileBasedSync.write_event("__clear__", {})
            # Очищаємо файл подій
            import json
            from pathlib import Path
            events_file = Path("sync_events.json")
            if events_file.exists():
                events_file.write_text("[]", encoding="utf-8")
            flash("✅ Список подій очищено", "success")
        except Exception as e:
            flash(f"Помилка: {e}", "danger")
        return redirect(url_for("sync_page"))

    # -------- Синхронізація (моніторинг) --------
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
        unprocessed = FileBasedSync.read_unprocessed_events()
        return render_template("sync.html", unprocessed_events=unprocessed, total_processed=0, stats=stats)

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
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                name = t["name"]
                try:
                    result["tables"][name] = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
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


    # ================== LOGISTICS — Повна адмін-панель ==================

    def _log_get_stats(conn):
        """Статистика логістики"""
        stats = {"total_vehicles": 0, "available_vehicles": 0, "total_shipments": 0, "active_shipments": 0}
        try:
            if _has_table(conn, "vehicles"):
                stats["total_vehicles"] = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
                stats["available_vehicles"] = conn.execute("SELECT COUNT(*) FROM vehicles WHERE status='available'").fetchone()[0]
            if _has_table(conn, "shipments"):
                stats["total_shipments"] = conn.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
                stats["active_shipments"] = conn.execute("SELECT COUNT(*) FROM shipments WHERE status='active'").fetchone()[0]
        except Exception:
            pass
        return stats

    @app.get("/logistics")
    @login_required
    def logistics_page():
        tab = request.args.get("tab", "shipments")
        q = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "").strip()

        conn = get_conn()
        try:
            stats = _log_get_stats(conn)
            shipments = []
            vehicles = []

            if tab == "shipments" and _has_table(conn, "shipments"):
                conditions = []
                params = []
                if q:
                    conditions.append("(cargo_type LIKE ? OR from_region LIKE ? OR to_region LIKE ? OR comment LIKE ?)")
                    params.extend([f"%{q}%"] * 4)
                if status_filter:
                    conditions.append("status=?")
                    params.append(status_filter)
                where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
                shipments = conn.execute(
                    f"SELECT * FROM shipments{where} ORDER BY id DESC LIMIT 200",
                    tuple(params)
                ).fetchall()

            elif tab == "vehicles" and _has_table(conn, "vehicles"):
                conditions = []
                params = []
                if q:
                    conditions.append("(base_region LIKE ? OR body_type LIKE ? OR comment LIKE ?)")
                    params.extend([f"%{q}%"] * 3)
                if status_filter:
                    conditions.append("status=?")
                    params.append(status_filter)
                where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
                vehicles = conn.execute(
                    f"SELECT * FROM vehicles{where} ORDER BY id DESC LIMIT 200",
                    tuple(params)
                ).fetchall()

        finally:
            conn.close()

        return render_template(
            "logistics.html",
            tab=tab,
            q=q,
            status_filter=status_filter,
            stats=stats,
            shipments=shipments,
            vehicles=vehicles,
        )

    # --- Shipment status change ---
    @app.post("/logistics/shipment/<int:sid>/status")
    @login_required
    def logistics_shipment_status(sid: int):
        new_status = request.form.get("status", "active")
        if new_status not in ("active", "done", "cancelled"):
            flash("Невірний статус", "danger")
            return redirect(url_for("logistics_page", tab="shipments"))
        conn = get_conn()
        try:
            if _has_table(conn, "shipments"):
                conn.execute("UPDATE shipments SET status=?, updated_at=datetime('now') WHERE id=?", (new_status, sid))
                conn.commit()
                labels = {"active": "Активна", "done": "Виконана", "cancelled": "Скасована"}
                flash(f"Заявка #{sid}: {labels.get(new_status, new_status)} ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="shipments"))

    # --- Shipment edit GET ---
    @app.get("/logistics/shipment/<int:sid>/edit")
    @login_required
    def logistics_shipment_edit(sid: int):
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM shipments WHERE id=?", (sid,)).fetchone()
            if not row:
                flash("Заявку не знайдено", "danger")
                return redirect(url_for("logistics_page", tab="shipments"))
            cols = _table_cols(conn, "shipments")
        finally:
            conn.close()
        return render_template("logistics_edit.html", table="shipments", cols=cols, row=row, pk="id",
                               back_url=url_for("logistics_page", tab="shipments"))

    # --- Shipment edit POST ---
    @app.post("/logistics/shipment/<int:sid>/edit")
    @login_required
    def logistics_shipment_edit_post(sid: int):
        conn = get_conn()
        try:
            cols = _table_cols(conn, "shipments")
            editable = [c for c in cols if c not in ("id", "creator_user_id", "created_at")]
            updates, params = [], []
            for c in editable:
                if c in request.form:
                    updates.append(f"{c}=?")
                    params.append(request.form.get(c) or None)
            if updates:
                params.append(sid)
                conn.execute(f"UPDATE shipments SET {', '.join(updates)} WHERE id=?", tuple(params))
                conn.commit()
                flash("Заявку оновлено ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="shipments"))

    # --- Shipment delete ---
    @app.post("/logistics/shipment/<int:sid>/delete")
    @login_required
    def logistics_shipment_delete(sid: int):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM shipments WHERE id=?", (sid,))
            conn.commit()
            flash(f"Заявку #{sid} видалено", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="shipments"))

    # --- Vehicle status change ---
    @app.post("/logistics/vehicle/<int:vid>/status")
    @login_required
    def logistics_vehicle_status(vid: int):
        new_status = request.form.get("status", "available")
        if new_status not in ("available", "busy"):
            flash("Невірний статус", "danger")
            return redirect(url_for("logistics_page", tab="vehicles"))
        conn = get_conn()
        try:
            if _has_table(conn, "vehicles"):
                conn.execute("UPDATE vehicles SET status=?, updated_at=datetime('now') WHERE id=?", (new_status, vid))
                conn.commit()
                label = "Доступний" if new_status == "available" else "Зайнятий"
                flash(f"Авто #{vid}: {label} ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="vehicles"))

    # --- Vehicle edit GET ---
    @app.get("/logistics/vehicle/<int:vid>/edit")
    @login_required
    def logistics_vehicle_edit(vid: int):
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()
            if not row:
                flash("Авто не знайдено", "danger")
                return redirect(url_for("logistics_page", tab="vehicles"))
            cols = _table_cols(conn, "vehicles")
        finally:
            conn.close()
        return render_template("logistics_edit.html", table="vehicles", cols=cols, row=row, pk="id",
                               back_url=url_for("logistics_page", tab="vehicles"))

    # --- Vehicle edit POST ---
    @app.post("/logistics/vehicle/<int:vid>/edit")
    @login_required
    def logistics_vehicle_edit_post(vid: int):
        conn = get_conn()
        try:
            cols = _table_cols(conn, "vehicles")
            editable = [c for c in cols if c not in ("id", "owner_user_id", "created_at")]
            updates, params = [], []
            for c in editable:
                if c in request.form:
                    updates.append(f"{c}=?")
                    params.append(request.form.get(c) or None)
            if updates:
                params.append(vid)
                conn.execute(f"UPDATE vehicles SET {', '.join(updates)} WHERE id=?", tuple(params))
                conn.commit()
                flash("Авто оновлено ✅", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="vehicles"))

    # --- Vehicle delete ---
    @app.post("/logistics/vehicle/<int:vid>/delete")
    @login_required
    def logistics_vehicle_delete(vid: int):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM vehicles WHERE id=?", (vid,))
            conn.commit()
            flash(f"Авто #{vid} видалено", "success")
        finally:
            conn.close()
        return redirect(url_for("logistics_page", tab="vehicles"))

    return app


# ============ HELPERS ============

def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def _table_cols(conn, table: str) -> list:
    try:
        return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _has_col(conn, table: str, col: str) -> bool:
    return col in _table_cols(conn, table)


def _list_tables(conn) -> list[str]:
    """Повертає список таблиць (без системних)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] if not isinstance(r, dict) else r["name"] for r in rows]


# ============ ЗАПУСК ============
if __name__ == "__main__":
    import os
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("🌾 Agro Marketplace - Web Panel")
    print(f"🔗 http://0.0.0.0:{port}")
    print(f"👤 Login: {ADMIN_USER}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
