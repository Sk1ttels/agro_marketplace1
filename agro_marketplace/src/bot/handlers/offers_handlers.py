"""
Обробники для торгу та пропозицій (counter_offers).
Повна функціональність: перегляд вхідних/моїх, прийняти/відхилити, зробити пропозицію.
"""

import aiosqlite
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    from config.settings import DB_PATH as _DB_PATH
    DB_FILE = str(_DB_PATH)
except Exception:
    import os
    DB_FILE = os.getenv("DB_FILE", "data/agro_bot.db")

router = Router()


# ---------- Ініціалізація таблиць ----------

async def _ensure_tables():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS counter_offers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id          INTEGER NOT NULL,
                sender_user_id  INTEGER NOT NULL,
                offered_price   REAL NOT NULL,
                message         TEXT,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_co_lot    ON counter_offers(lot_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_co_sender ON counter_offers(sender_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_co_status ON counter_offers(status)")
        await db.commit()


# ---------- FSM ----------

class MakeOffer(StatesGroup):
    price   = State()
    comment = State()


# ============================================================
# MENU: 🔨 Торг
# ============================================================

@router.message(F.text == "🔨 Торг")
async def trade_menu(message: Message):
    await _ensure_tables()
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Вхідні пропозиції",  callback_data="offers:incoming")
    kb.button(text="📤 Мої пропозиції",      callback_data="offers:my")
    kb.button(text="✅ Прийняті угоди",      callback_data="offers:accepted")
    kb.adjust(1)
    await message.answer(
        "🔨 <b>Торг / Пропозиції</b>\n\nОберіть розділ:",
        reply_markup=kb.as_markup()
    )


# ============================================================
# INCOMING OFFERS (до моїх лотів)
# ============================================================

@router.callback_query(F.data == "offers:incoming")
async def offers_incoming(cb: CallbackQuery):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur  = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me   = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True); return
        my_id = me["id"]

        cur = await db.execute("""
            SELECT co.id AS offer_id, co.offered_price, co.message, co.created_at,
                   l.id AS lot_id, l.crop, l.price AS lot_price,
                   u.telegram_id AS sender_telegram_id
            FROM counter_offers co
            JOIN lots l  ON co.lot_id         = l.id
            JOIN users u ON co.sender_user_id = u.id
            WHERE l.owner_user_id = ? AND co.status = 'pending'
            ORDER BY co.id DESC
        """, (my_id,))
        rows = await cur.fetchall()

    await cb.answer()
    if not rows:
        await cb.message.answer("📭 <b>Вхідних пропозицій немає</b>")
        return

    await cb.message.answer(f"📥 <b>Вхідні пропозиції: {len(rows)}</b>")
    for r in rows:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Прийняти",  callback_data=f"offer:accept:{r['offer_id']}")
        kb.button(text="❌ Відхилити", callback_data=f"offer:reject:{r['offer_id']}")
        kb.adjust(2)
        await cb.message.answer(
            f"📦 <b>Лот #{r['lot_id']}</b> — {r['crop']}\n"
            f"💰 Ваша ціна: {r['lot_price']} грн/т\n"
            f"💵 Пропозиція: <b>{r['offered_price']}</b> грн/т\n"
            f"💬 {r['message'] or '—'}\n"
            f"🕒 {r['created_at']}",
            reply_markup=kb.as_markup()
        )


# ============================================================
# MY OFFERS (я робив пропозиції)
# ============================================================

@router.callback_query(F.data == "offers:my")
async def offers_my(cb: CallbackQuery):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur  = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me   = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True); return
        my_id = me["id"]

        cur = await db.execute("""
            SELECT co.id AS offer_id, co.offered_price, co.message, co.status, co.created_at,
                   l.id AS lot_id, l.crop, l.price AS lot_price
            FROM counter_offers co
            JOIN lots l ON co.lot_id = l.id
            WHERE co.sender_user_id = ?
            ORDER BY co.id DESC
        """, (my_id,))
        rows = await cur.fetchall()

    await cb.answer()
    if not rows:
        await cb.message.answer("📭 <b>Ви ще не робили пропозицій</b>")
        return

    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}
    await cb.message.answer(f"📤 <b>Мої пропозиції: {len(rows)}</b>")
    for r in rows:
        emoji = status_emoji.get(r["status"], "❓")
        await cb.message.answer(
            f"📦 <b>Лот #{r['lot_id']}</b> — {r['crop']}\n"
            f"💰 Ціна лоту: {r['lot_price']} грн/т\n"
            f"💵 Моя пропозиція: <b>{r['offered_price']}</b> грн/т\n"
            f"📌 Статус: {emoji} <b>{r['status']}</b>\n"
            f"💬 {r['message'] or '—'}\n"
            f"🕒 {r['created_at']}"
        )


# ============================================================
# ACCEPTED DEALS
# ============================================================

@router.callback_query(F.data == "offers:accepted")
async def offers_accepted(cb: CallbackQuery):
    await _ensure_tables()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur  = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me   = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True); return
        my_id = me["id"]

        cur = await db.execute("""
            SELECT co.offered_price, co.message, co.created_at,
                   l.id AS lot_id, l.crop, l.price AS lot_price
            FROM counter_offers co
            JOIN lots l ON co.lot_id = l.id
            WHERE co.status = 'accepted'
              AND (co.sender_user_id = ? OR l.owner_user_id = ?)
            ORDER BY co.id DESC
        """, (my_id, my_id))
        rows = await cur.fetchall()

    await cb.answer()
    if not rows:
        await cb.message.answer("📭 <b>Прийнятих угод немає</b>")
        return

    await cb.message.answer(f"✅ <b>Прийняті угоди: {len(rows)}</b>")
    for r in rows:
        await cb.message.answer(
            f"✅ <b>Угода укладена</b>\n"
            f"📦 Лот #{r['lot_id']} — {r['crop']}\n"
            f"💰 Ціна лоту: {r['lot_price']} грн/т\n"
            f"💵 Ціна угоди: <b>{r['offered_price']}</b> грн/т\n"
            f"💬 {r['message'] or '—'}\n"
            f"🕒 {r['created_at']}"
        )


# ============================================================
# ACCEPT / REJECT offer
# ============================================================

@router.callback_query(F.data.startswith("offer:accept:"))
async def accept_offer(cb: CallbackQuery):
    await _ensure_tables()
    offer_id = int(cb.data.split(":")[-1])

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT co.*, l.crop, l.price AS lot_price,
                   u.telegram_id AS sender_telegram_id
            FROM counter_offers co
            JOIN lots l  ON co.lot_id         = l.id
            JOIN users u ON co.sender_user_id = u.id
            WHERE co.id = ?
        """, (offer_id,))
        offer = await cur.fetchone()
        if not offer:
            await cb.answer("❌ Пропозицію не знайдено", show_alert=True); return

        await db.execute("UPDATE counter_offers SET status='accepted' WHERE id=?", (offer_id,))
        await db.commit()

    await cb.answer("✅ Пропозицію прийнято!", show_alert=True)

    # Сповіщення покупцю
    try:
        await cb.bot.send_message(
            offer["sender_telegram_id"],
            f"✅ <b>Вашу пропозицію прийнято!</b>\n\n"
            f"🌾 {offer['crop']}\n"
            f"💰 Ціна лоту: {offer['lot_price']} грн/т\n"
            f"💵 Ціна угоди: <b>{offer['offered_price']}</b> грн/т\n\n"
            "Очікуйте на зв'язок від продавця.",
        )
    except Exception:
        pass

    try:
        await cb.message.edit_text(
            f"✅ <b>Пропозицію прийнято</b>\n\n"
            f"🌾 {offer['crop']}\n"
            f"💵 Ціна угоди: {offer['offered_price']} грн/т"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("offer:reject:"))
async def reject_offer(cb: CallbackQuery):
    await _ensure_tables()
    offer_id = int(cb.data.split(":")[-1])

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT co.*, l.crop,
                   u.telegram_id AS sender_telegram_id
            FROM counter_offers co
            JOIN lots l  ON co.lot_id         = l.id
            JOIN users u ON co.sender_user_id = u.id
            WHERE co.id = ?
        """, (offer_id,))
        offer = await cur.fetchone()
        if not offer:
            await cb.answer("❌ Пропозицію не знайдено", show_alert=True); return

        await db.execute("UPDATE counter_offers SET status='rejected' WHERE id=?", (offer_id,))
        await db.commit()

    await cb.answer("❌ Пропозицію відхилено", show_alert=True)

    try:
        await cb.bot.send_message(
            offer["sender_telegram_id"],
            f"❌ <b>Вашу пропозицію відхилено</b>\n\n"
            f"🌾 {offer['crop']}\n"
            f"💵 Ціна: {offer['offered_price']} грн/т"
        )
    except Exception:
        pass

    try:
        await cb.message.edit_text("❌ <b>Пропозицію відхилено</b>")
    except Exception:
        pass


# ============================================================
# CREATE NEW OFFER (кнопка "💰 Запропонувати ціну" з картки лота)
# ============================================================

@router.callback_query(F.data.startswith("offer:make:"))
async def make_offer_start(cb: CallbackQuery, state: FSMContext):
    await _ensure_tables()
    lot_id = int(cb.data.split(":")[-1])

    # Перевіряємо що лот існує і юзер не є його власником
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT l.*, u.telegram_id AS owner_telegram_id
            FROM lots l JOIN users u ON l.owner_user_id = u.id
            WHERE l.id = ?
        """, (lot_id,))
        lot = await cur.fetchone()

    if not lot:
        await cb.answer("❌ Лот не знайдено", show_alert=True); return

    if lot["owner_telegram_id"] == cb.from_user.id:
        await cb.answer("❌ Не можна робити пропозицію на власний лот", show_alert=True); return

    await state.update_data(offer_lot_id=lot_id, offer_lot_crop=lot["crop"],
                            offer_lot_price=lot["price"])
    await state.set_state(MakeOffer.price)
    await cb.answer()

    lot_type = "📤 Продаж" if lot["type"] == "sell" else "📥 Купівля"
    await cb.message.answer(
        f"💰 <b>Пропозиція на лот #{lot_id}</b>\n\n"
        f"{lot_type} — <b>{lot['crop']}</b>\n"
        f"💰 Поточна ціна: <b>{lot['price']} грн/т</b>\n\n"
        "Введіть вашу ціну (грн/т):"
    )


@router.message(MakeOffer.price)
async def make_offer_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", "").strip())
        if price <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Некоректна ціна. Введіть число, наприклад: 8500")
        return

    await state.update_data(offer_price=price)
    await state.set_state(MakeOffer.comment)
    await message.answer(
        f"💵 Ціна: <b>{price} грн/т</b>\n\n"
        "💬 Додайте коментар (або надішліть «-» щоб пропустити):"
    )


@router.message(MakeOffer.comment)
async def make_offer_comment(message: Message, state: FSMContext):
    await _ensure_tables()
    comment = message.text.strip()
    if comment == "-":
        comment = None

    data = await state.get_data()
    lot_id = data["offer_lot_id"]
    price  = data["offer_price"]
    crop   = data.get("offer_lot_crop", "")
    lot_price = data.get("offer_lot_price", "—")

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (message.from_user.id,))
        user_row = await cur.fetchone()
        if not user_row:
            await message.answer("❌ Помилка: профіль не знайдено. Зробіть /start")
            await state.clear(); return

        sender_id = user_row["id"]

        # Перевірка чи вже є активна пропозиція від цього юзера
        cur = await db.execute(
            "SELECT id FROM counter_offers WHERE lot_id=? AND sender_user_id=? AND status='pending'",
            (lot_id, sender_id)
        )
        existing = await cur.fetchone()
        if existing:
            await message.answer(
                "⚠️ У вас вже є активна пропозиція на цей лот.\n"
                "Дочекайтесь відповіді або перегляньте «🔨 Торг → 📤 Мої»"
            )
            await state.clear(); return

        # Дані власника лота для сповіщення
        cur = await db.execute("""
            SELECT u.telegram_id AS owner_telegram_id
            FROM lots l JOIN users u ON l.owner_user_id = u.id
            WHERE l.id = ?
        """, (lot_id,))
        lot_row = await cur.fetchone()
        owner_tg = lot_row["owner_telegram_id"] if lot_row else None

        await db.execute("""
            INSERT INTO counter_offers (lot_id, sender_user_id, offered_price, message, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', datetime('now'))
        """, (lot_id, sender_id, price, comment))
        await db.commit()

    await state.clear()

    await message.answer(
        f"✅ <b>Пропозицію надіслано!</b>\n\n"
        f"🌾 {crop}\n"
        f"💰 Ціна лоту: {lot_price} грн/т\n"
        f"💵 Ваша пропозиція: <b>{price} грн/т</b>\n"
        f"💬 {comment or '—'}\n\n"
        "Очікуйте відповіді від власника лоту.\n"
        "Переглянути: 🔨 Торг → 📤 Мої пропозиції"
    )

    # Сповіщення власника лота
    if owner_tg:
        try:
            await message.bot.send_message(
                owner_tg,
                f"📨 <b>Нова пропозиція на ваш лот!</b>\n\n"
                f"🌾 {crop}\n"
                f"💰 Ваша ціна: {lot_price} грн/т\n"
                f"💵 Пропозиція: <b>{price} грн/т</b>\n"
                f"💬 {comment or '—'}\n\n"
                "Переглянути: 🔨 Торг → 📥 Вхідні пропозиції"
            )
        except Exception:
            pass
