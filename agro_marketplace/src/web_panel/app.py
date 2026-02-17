# -*- coding: utf-8 -*-
"""
Agro Marketplace — Admin Web Panel
✅ Синхронізована БД з ботом
✅ Сучасний інтерфейс
✅ Керування користувачами та лотами
"""

from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config.settings import FLASK_SECRET, ADMIN_USER, ADMIN_PASS
from .db import get_conn, init_schema, get_setting, set_setting
from .auth import AdminUser, check_login
import logging

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
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return AdminUser(user_id)

    # ✅ Ініціалізація схеми БД (надійно, навіть якщо init_schema має різні сигнатури)
    try:
        conn = get_conn()
        try:
            try:
                init_schema(conn)   # якщо init_schema(conn)
            except TypeError:
                init_schema()       # якщо init_schema()
            try:
                conn.commit()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        logger.exception("DB init failed: %s", e)

    @app.context_processor
    def inject_dashboard_defaults():
        """Default context to prevent template crashes when route misses dashboard data."""
        return {
            "stats": {"users": 0, "lots": 0, "active_lots": 0, "banned": 0},
            "weekly_data": {
                "labels": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
                "new_users": [0, 0, 0, 0, 0, 0, 0],
                "new_lots": [0, 0, 0, 0, 0, 0, 0],
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

            # Статистика користувачів
            if _has_table(conn, "users"):
                try:
                    stats["users"] = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
                    if _has_col(conn, "users", "is_banned"):
                        stats["banned"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM users WHERE is_banned=1"
                        ).fetchone()["c"]
                except Exception:
                    pass

            # Статистика лотів
            if _has_table(conn, "lots"):
                try:
                    stats["lots"] = conn.execute("SELECT COUNT(*) AS c FROM lots").fetchone()["c"]
                    cols = _table_cols(conn, "lots")

                    if "status" in cols:
                        stats["active_lots"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE status IN ('active', 'open', 'published')"
                        ).fetchone()["c"]
                    elif "is_active" in cols:
                        stats["active_lots"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE is_active=1"
                        ).fetchone()["c"]
                    elif "is_closed" in cols:
                        stats["active_lots"] = conn.execute(
                            "SELECT COUNT(*) AS c FROM lots WHERE is_closed=0"
                        ).fetchone()["c"]
                except Exception:
                    pass

            # Дані за останні 7 днів
            weekly_data = {"labels": [], "new_users": [0] * 7, "new_lots": [0] * 7}

            if _has_table(conn, "users") and _has_col(conn, "users", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            """SELECT COUNT(*) as c FROM users
                               WHERE date(created_at) = date('now', '-' || ? || ' days')""",
                            (i,),
                        ).fetchone()
                        weekly_data["new_users"][6 - i] = row["c"] if row else 0
                except Exception:
                    weekly_data["new_users"] = [0] * 7

            if _has_table(conn, "lots") and _has_col(conn, "lots", "created_at"):
                try:
                    for i in range(6, -1, -1):
                        row = conn.execute(
                            """SELECT COUNT(*) as c FROM lots
                               WHERE date(created_at) = date('now', '-' || ? || ' days')""",
                            (i,),
                        ).fetchone()
                        weekly_data["new_lots"][6 - i] = row["c"] if row else 0
                except Exception:
                    weekly_data["new_lots"] = [0] * 7

            import datetime
            for i in range(6, -1, -1):
                d = datetime.datetime.now() - datetime.timedelta(days=i)
                day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"][d.weekday()]
                weekly_data["labels"].append(day_name)

            # Останні лоти
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
            try:
                conn.close()
            except Exception:
                pass

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
            where_clauses = []
            params = []

            if q:
                search_fields = []
                if "telegram_id" in cols:
                    search_fields.append("CAST(telegram_id AS TEXT) LIKE ?")
                    params.append(f"%{q}%")
                if "username" in cols:
                    search_fields.append("LOWER(COALESCE(username,'')) LIKE LOWER(?)")
                    params.append(f"%{q}%")
                if "full_name" in cols:
                    search_fields.append("LOWER(COALESCE(full_name,'')) LIKE LOWER(?)")
                    params.append(f"%{q}%")

                if search_fields:
                    where_clauses.append(f"({' OR '.join(search_fields)})")

            sql = "SELECT * FROM users"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY id DESC LIMIT 300"

            rows = conn.execute(sql, tuple(params)).fetchall()
            return render_template("users.html", rows=rows, q=q)
        finally:
            try:
                conn.close()
            except Exception:
                pass

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
                flash("Неможливо забанити користувача ❌", "danger")
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
            flash(f"Помилка: {str(e)}", "danger")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
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
                flash("Неможливо розбанити користувача ❌", "danger")
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            flash(f"Помилка: {str(e)}", "danger")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("users_page"))

    @app.get("/users/export")
    @login_required
    def users_export():
        import csv
        from io import StringIO

        conn = get_conn()
        try:
            if not _has_table(conn, "users"):
                flash("Таблиця користувачів не знайдена", "danger")
                return redirect(url_for("users_page"))

            users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        output = StringIO()
        if users:
            cols = list(users[0].keys())
            writer = csv.DictWriter(output, fieldnames=cols)
            writer.writeheader()
            for user in users:
                writer.writerow(dict(user))

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment;filename=users_export.csv",
                "Content-Type": "text/csv; charset=utf-8",
            },
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
                    (user_id,),
                ).fetchall()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        try:
            return render_template("user_detail.html", user=user, lots=lots)
        except Exception:
            user_dict = dict(user)
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Користувач #{user_id}</title>
                <meta charset="utf-8">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-4">
                    <h2>👤 Користувач #{user_id}</h2>
                    <div class="card mt-3">
                        <div class="card-body">
                            <p><strong>Telegram ID:</strong> {user_dict.get('telegram_id', '—')}</p>
                            <p><strong>Ім'я:</strong> {user_dict.get('full_name', '—')}</p>
                            <p><strong>Username:</strong> @{user_dict.get('username', '—')}</p>
                            <p><strong>Телефон:</strong> {user_dict.get('phone', '—')}</p>
                            <p><strong>Компанія:</strong> {user_dict.get('company', '—')}</p>
                            <p><strong>Регіон:</strong> {user_dict.get('region', '—')}</p>
                            <p><strong>Роль:</strong> {user_dict.get('role', '—')}</p>
                            <p><strong>Статус:</strong> {'🚫 Заблокований' if user_dict.get('is_banned') else '✅ Активний'}</p>
                            <p><strong>Дата реєстрації:</strong> {user_dict.get('created_at', '—')}</p>
                        </div>
                    </div>
                    <div class="mt-3">
                        <h4>📦 Лоти користувача ({len(lots)})</h4>
                        {'<p>Немає лотів</p>' if not lots else '<ul>' + ''.join([f"<li>Лот #{lot['id']} - {lot.get('crop','')} ({lot.get('status','')})</li>" for lot in lots]) + '</ul>'}
                    </div>
                    <a href="/users" class="btn btn-secondary mt-3">← Назад до списку</a>
                </div>
            </body>
            </html>
            """

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
            try:
                conn.close()
            except Exception:
                pass

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
                flash("Неможливо змінити статус лота ❌", "danger")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("lots_page"))

    @app.get("/lots/export")
    @login_required
    def lots_export():
        import csv
        from io import StringIO

        conn = get_conn()
        try:
            if not _has_table(conn, "lots"):
                flash("Таблиця лотів не знайдена", "danger")
                return redirect(url_for("lots_page"))

            lots = conn.execute("SELECT * FROM lots ORDER BY id DESC").fetchall()
            if not lots:
                flash("Немає лотів для експорту", "warning")
                return redirect(url_for("lots_page"))
        finally:
            try:
                conn.close()
            except Exception:
                pass

        output = StringIO()
        cols = list(lots[0].keys())
        writer = csv.DictWriter(output, fieldnames=cols)
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
            if _has_table(conn, "users") and lot.get("owner_user_id"):
                owner = conn.execute(
                    "SELECT * FROM users WHERE id=?",
                    (lot["owner_user_id"],),
                ).fetchone()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return render_template("lot_detail.html", lot=lot, owner=owner)

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
            else:
                flash("Неможливо закрити лот ❌", "danger")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("lots_page"))

    @app.route("/lots/<int:lot_id>/activate", methods=["POST", "GET"])
    @login_required
    def lot_activate(lot_id: int):
        """Активація лота (кнопка 'Активувати' у веб-панелі)."""
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
            else:
                flash("Неможливо активувати лот ❌", "danger")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("lots_page"))

    # -------- Налаштування --------
    @app.get("/settings")
    @login_required
    def settings_page():
        settings_data = {
            "platform_name": get_setting("platform_name", "Agro Marketplace"),
            "currency": get_setting("currency", "UAH"),
            "min_price": get_setting("min_price", "0"),
            "max_price": get_setting("max_price", "999999"),
            "example_amount": get_setting("example_amount", "25т"),
            "auto_moderation": get_setting("auto_moderation", "0"),
        }
        return render_template("settings.html", s=settings_data)

    @app.post("/settings/save")
    @login_required
    def settings_save():
        set_setting("platform_name", request.form.get("platform_name", "Agro Marketplace"))
        set_setting("currency", request.form.get("currency", "UAH"))
        set_setting("min_price", request.form.get("min_price", "0"))
        set_setting("max_price", request.form.get("max_price", "999999"))
        set_setting("example_amount", request.form.get("example_amount", "25т"))
        set_setting("auto_moderation", "1" if request.form.get("auto_moderation") else "0")
        flash("Налаштування збережено ✅", "success")
        return redirect(url_for("settings_page"))

    # -------- Контакти --------
    @app.get("/contacts")
    @login_required
    def contacts_page():
        conn = get_conn()
        try:
            if not _has_table(conn, "contacts"):
                return render_template("contacts.html", contacts=[])

            contacts = conn.execute("""
                SELECT
                    c.id,
                    c.user_id,
                    c.contact_user_id,
                    c.status,
                    c.created_at,
                    u1.full_name as user_name,
                    u1.username as user_username,
                    u1.telegram_id as user_telegram_id,
                    u2.full_name as contact_name,
                    u2.username as contact_username,
                    u2.telegram_id as contact_telegram_id
                FROM contacts c
                LEFT JOIN users u1 ON c.user_id = u1.id
                LEFT JOIN users u2 ON c.contact_user_id = u2.id
                ORDER BY c.created_at DESC
                LIMIT 500
            """).fetchall()

            return render_template("contacts.html", contacts=contacts)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # -------- API --------
    @app.get("/api/ping")
    def api_ping():
        return jsonify({"status": "ok", "message": "Web panel is alive"})

    @app.get("/api/db-check")
    @login_required
    def api_db_check():
        from config.settings import DB_PATH

        conn = get_conn()
        try:
            result = {
                "db_path": str(DB_PATH),
                "db_exists": DB_PATH.exists(),
                "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
                "tables": {},
            }

            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for table in tables:
                table_name = table["name"]
                try:
                    count = conn.execute(f"SELECT COUNT(*) as c FROM {table_name}").fetchone()
                    result["tables"][table_name] = count["c"]
                except Exception as e:
                    result["tables"][table_name] = f"Error: {str(e)}"

            return jsonify(result)
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)})
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @app.route("/api/sync", methods=["GET", "POST"])
    def api_sync():
        if request.method == "POST":
            data = request.get_json(silent=True)
            return jsonify({"status": "ok", "received": True, "data": data})
        return jsonify({"status": "ok", "message": "Sync endpoint ready"})

    # -------- Сторінка синхронізації --------
    @app.get("/sync")
    @login_required
    def sync_page():
        conn = get_conn()
        try:
            stats = {"users_count": 0, "lots_count": 0}

            if _has_table(conn, "users"):
                try:
                    stats["users_count"] = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
                except Exception:
                    pass

            if _has_table(conn, "lots"):
                try:
                    stats["lots_count"] = conn.execute("SELECT COUNT(*) AS c FROM lots").fetchone()["c"]
                except Exception:
                    pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

        unprocessed_events = []
        total_processed = 0
        return render_template(
            "sync.html",
            unprocessed_events=unprocessed_events,
            total_processed=total_processed,
            stats=stats,
        )

    # -------- Реклама --------
    @app.get("/advertisements")
    @login_required
    def advertisements_page():
        conn = get_conn()
        try:
            # Створюємо таблиці якщо немає
            conn.execute("""
                CREATE TABLE IF NOT EXISTS advertisements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'text',
                    content TEXT NOT NULL,
                    image_url TEXT,
                    button_text TEXT,
                    button_url TEXT,
                    is_active INTEGER DEFAULT 1,
                    show_frequency INTEGER DEFAULT 3,
                    views_count INTEGER DEFAULT 0,
                    clicks_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS advertisement_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ad_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    clicked INTEGER DEFAULT 0,
                    FOREIGN KEY (ad_id) REFERENCES advertisements(id)
                )
            """)
            conn.commit()

            ads = conn.execute("SELECT * FROM advertisements ORDER BY created_at DESC").fetchall()
            return render_template("advertisements.html", ads=ads)
        except Exception as e:
            logger.error(f"Advertisements error: {e}")
            flash(f"Помилка реклами: {str(e)}", "danger")
            return render_template("advertisements.html", ads=[])
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @app.post("/advertisements/create")
    @login_required
    def create_advertisement():
        conn = get_conn()
        try:
            title = request.form.get("title", "").strip()
            ad_type = request.form.get("type", "text")
            content = request.form.get("content", "").strip()
            image_url = request.form.get("image_url", "").strip()
            button_text = request.form.get("button_text", "").strip()
            button_url = request.form.get("button_url", "").strip()
            show_frequency = int(request.form.get("show_frequency", 3))
            is_active = 1 if request.form.get("is_active") else 0

            if not title or not content:
                flash("Назва та текст обов'язкові!", "danger")
                return redirect(url_for("advertisements_page"))

            conn.execute("""
                INSERT INTO advertisements
                (title, type, content, image_url, button_text, button_url,
                 show_frequency, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, ad_type, content, image_url, button_text,
                  button_url, show_frequency, is_active))

            conn.commit()
            flash("✅ Оголошення створено!", "success")
        except Exception as e:
            logger.error(f"Error creating ad: {e}")
            flash(f"Помилка: {str(e)}", "danger")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("advertisements_page"))

    @app.post("/advertisements/<int:ad_id>/toggle")
    @login_required
    def toggle_advertisement(ad_id: int):
        conn = get_conn()
        try:
            conn.execute("""
                UPDATE advertisements
                SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ad_id,))
            conn.commit()
            flash("✅ Статус оголошення змінено", "success")
        except Exception as e:
            logger.error(f"Error toggling ad: {e}")
            flash(f"Помилка: {str(e)}", "danger")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("advertisements_page"))

    @app.post("/advertisements/<int:ad_id>/delete")
    @login_required
    def delete_advertisement(ad_id: int):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM advertisements WHERE id = ?", (ad_id,))
            conn.execute("DELETE FROM advertisement_views WHERE ad_id = ?", (ad_id,))
            conn.commit()
            flash("✅ Оголошення видалено", "success")
        except Exception as e:
            logger.error(f"Error deleting ad: {e}")
            flash(f"Помилка: {str(e)}", "danger")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("advertisements_page"))

    return app


# ============ HELPERS ============

def _has_table(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_cols(conn, table: str) -> list:
    try:
        return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
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
    print(f"🔐 Password: {ADMIN_PASS}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port)
