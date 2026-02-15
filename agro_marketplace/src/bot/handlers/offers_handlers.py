"""Обробники для торгу та пропозицій (aiosqlite)
Працює з agro_bot.db та існуючими таблицями users/lots.
"""

import aiosqlite
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()
DB_FILE = "agro_bot.db"

import aiosqlite

DB_FILE = "agro_bot.db"

async def _ensure_tables():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS counter_offers (
                                                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                       lot_id INTEGER NOT NULL,
                                                                       sender_user_id INTEGER NOT NULL,
                                                                       offered_price REAL NOT NULL,
                                                                       message TEXT,
                                                                       status TEXT NOT NULL DEFAULT 'pending',
                                                                       created_at TEXT DEFAULT (datetime('now'))
                             )
                         """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_lot ON counter_offers(lot_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_sender ON counter_offers(sender_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_status ON counter_offers(status)")
        await db.commit()


# ---------- DB helpers ----------

async def ensure_counter_offers_table() -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS counter_offers (
                                                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                       lot_id INTEGER NOT NULL,
                                                                       sender_user_id INTEGER NOT NULL,
                                                                       offered_price REAL NOT NULL,
                                                                       message TEXT,
                                                                       status TEXT NOT NULL DEFAULT 'pending',
                                                                       created_at TEXT DEFAULT (datetime('now'))
                             )
                         """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_lot ON counter_offers(lot_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_sender ON counter_offers(sender_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_counter_offers_status ON counter_offers(status)")
        await db.commit()


# ---------- FSM ----------

class MakeOffer(StatesGroup):
    price = State()
    message = State()


# ---------- Меню торгу ----------

@router.message(F.text == "🔨 Торг")
async def trade_menu(message: Message):
    await ensure_counter_offers_table()

    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Вхідні", callback_data="offers:incoming")
    kb.button(text="📤 Мої", callback_data="offers:my")
    kb.button(text="✅ Прийняті", callback_data="offers:accepted")
    kb.adjust(1)

    await message.answer(
        "<b>🔨 Торг / Пропозиції</b>\n\nОберіть розділ:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "offers:incoming")
async def offers_incoming(cb: CallbackQuery):
    await ensure_counter_offers_table()

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # знайти user.id по telegram_id
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True)
            return

        my_user_id = me["id"]

        # Вхідні пропозиції = pending до моїх лотів
        cur = await db.execute(
            """
            SELECT
                co.id as offer_id,
                co.offered_price,
                co.message,
                co.created_at,
                l.id as lot_id,
                l.crop,
                l.price as lot_price,
                u.telegram_id as sender_telegram_id
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
                     JOIN users u ON co.sender_user_id = u.id
            WHERE l.owner_user_id = ? AND co.status = 'pending'
            ORDER BY co.id DESC
            """,
            (my_user_id,)
        )
        rows = await cur.fetchall()

    if not rows:
        await cb.message.answer("📭 Вхідних пропозицій немає")
        await cb.answer()
        return

    for r in rows:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Прийняти", callback_data=f"offer:accept:{r['offer_id']}")
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

    await cb.answer()


@router.callback_query(F.data == "offers:my")
async def offers_my(cb: CallbackQuery):
    await ensure_counter_offers_table()

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True)
            return
        my_user_id = me["id"]

        cur = await db.execute(
            """
            SELECT
                co.id as offer_id,
                co.offered_price,
                co.message,
                co.status,
                co.created_at,
                l.id as lot_id,
                l.crop,
                l.price as lot_price
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
            WHERE co.sender_user_id = ?
            ORDER BY co.id DESC
            """,
            (my_user_id,)
        )
        rows = await cur.fetchall()

    if not rows:
        await cb.message.answer("📭 Ви ще не робили пропозицій")
        await cb.answer()
        return

    for r in rows:
        await cb.message.answer(
            f"📦 <b>Лот #{r['lot_id']}</b> — {r['crop']}\n"
            f"💰 Ціна лоту: {r['lot_price']} грн/т\n"
            f"💵 Ваша пропозиція: <b>{r['offered_price']}</b> грн/т\n"
            f"📌 Статус: <b>{r['status']}</b>\n"
            f"💬 {r['message'] or '—'}\n"
            f"🕒 {r['created_at']}"
        )

    await cb.answer()


@router.callback_query(F.data == "offers:accepted")
async def offers_accepted(cb: CallbackQuery):
    await ensure_counter_offers_table()

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (cb.from_user.id,))
        me = await cur.fetchone()
        if not me:
            await cb.answer("❌ Профіль не знайдено", show_alert=True)
            return
        my_user_id = me["id"]

        cur = await db.execute(
            """
            SELECT
                co.id as offer_id,
                co.offered_price,
                co.message,
                co.created_at,
                l.id as lot_id,
                l.crop,
                l.price as lot_price,
                l.owner_user_id
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
            WHERE co.status = 'accepted'
              AND (co.sender_user_id = ? OR l.owner_user_id = ?)
            ORDER BY co.id DESC
            """,
            (my_user_id, my_user_id)
        )
        rows = await cur.fetchall()

    if not rows:
        await cb.message.answer("📭 Прийнятих пропозицій немає")
        await cb.answer()
        return

    for r in rows:
        await cb.message.answer(
            f"✅ <b>Прийнято</b>\n"
            f"📦 Лот #{r['lot_id']} — {r['crop']}\n"
            f"💰 Ціна лоту: {r['lot_price']} грн/т\n"
            f"💵 Ціна угоди: <b>{r['offered_price']}</b> грн/т\n"
            f"💬 {r['message'] or '—'}\n"
            f"🕒 {r['created_at']}"
        )

    await cb.answer()


# ---------- Прийняти/відхилити ----------

@router.callback_query(F.data.startswith("offer:accept:"))
async def accept_offer(cb: CallbackQuery):
    await ensure_counter_offers_table()
    offer_id = int(cb.data.split(":")[-1])

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            """
            SELECT co.*, l.crop, l.price as lot_price,
                   u.telegram_id as sender_telegram_id
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
                     JOIN users u ON co.sender_user_id = u.id
            WHERE co.id = ?
            """,
            (offer_id,)
        )
        offer = await cur.fetchone()

        if not offer:
            await cb.answer("❌ Пропозицію не знайдено", show_alert=True)
            return

        await db.execute("UPDATE counter_offers SET status='accepted' WHERE id=?", (offer_id,))
        await db.commit()

    await cb.answer("✅ Пропозицію прийнято!", show_alert=True)

    # повідомлення тому, хто зробив пропозицію
    try:
        await cb.bot.send_message(
            offer["sender_telegram_id"],
            "✅ <b>Вашу пропозицію прийнято!</b>\n\n"
            f"🌾 {offer['crop']}\n"
            f"💰 Лот: {offer['lot_price']} грн/т\n"
            f"💵 Угода: <b>{offer['offered_price']}</b> грн/т\n\n"
            "Очікуйте на зв'язок від продавця."
        )
    except Exception:
        pass

    await cb.message.edit_text(
        f"✅ <b>Пропозицію прийнято</b>\n\n💵 Ціна: {offer['offered_price']} грн/т"
    )


@router.callback_query(F.data.startswith("offer:reject:"))
async def reject_offer(cb: CallbackQuery):
    await ensure_counter_offers_table()
    offer_id = int(cb.data.split(":")[-1])

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            """
            SELECT co.*, l.crop,
                   u.telegram_id as sender_telegram_id
            FROM counter_offers co
                     JOIN lots l ON co.lot_id = l.id
                     JOIN users u ON co.sender_user_id = u.id
            WHERE co.id = ?
            """,
            (offer_id,)
        )
        offer = await cur.fetchone()

        if not offer:
            await cb.answer("❌ Пропозицію не знайдено", show_alert=True)
            return

        await db.execute("UPDATE counter_offers SET status='rejected' WHERE id=?", (offer_id,))
        await db.commit()

    await cb.answer("❌ Пропозицію відхилено", show_alert=True)

    try:
        await cb.bot.send_message(
            offer["sender_telegram_id"],
            "❌ <b>Вашу пропозицію відхилено</b>\n\n"
            f"🌾 {offer['crop']}\n"
            f"💵 Ціна: {offer['offered_price']} грн/т"
        )
    except Exception:
        pass

    await cb.message.edit_text("❌ Пропозицію відхилено")


# ---------- Створити пропозицію з лоту ----------

@router.callback_query(F.data.startswith("offer:make:"))
async def make_offer_start(cb: CallbackQuery, state: FSMContext):
    await ensure_counter_offers_table()
    lot_id = int(cb.data.split(":")[-1])

    await state.update_data(offer_lot_id=lot_id)
    await state.set_state(MakeOffer.price)

    await cb.answer()
    await cb.message.answer(
        "💰 <b>Ваша пропозиція</b>\n\nВведіть пропоновану ціну (грн/т):"
    )


@router.message(MakeOffer.price)
async def make_offer_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Некоректна ціна. Введіть число:")
        return

    await state.update_data(offer_price=price)
    await state.set_state(MakeOffer.message)

    await message.answer(
        "💬 Введіть коментар до пропозиції\n(або надішліть '-' щоб пропустити):"
    )


@router.message(MakeOffer.message)
async def make_offer_message(message: Message, state: FSMContext):
    await ensure_counter_offers_table()

    comment = message.text.strip()
    if comment == "-":
        comment = None

    data = await state.get_data()
    lot_id = data["offer_lot_id"]
    price = data["offer_price"]

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # sender user.id
        cur = await db.execute("SELECT id FROM users WHERE telegram_id=?", (message.from_user.id,))
        user_row = await cur.fetchone()
        if not user_row:
            await message.answer("❌ Помилка: профіль не знайдено")
            await state.clear()
            return
        sender_user_id = user_row["id"]

        # lot + owner telegram
        cur = await db.execute(
            """
            SELECT l.*, u.telegram_id as owner_telegram_id
            FROM lots l
                     JOIN users u ON l.owner_user_id = u.id
            WHERE l.id = ?
            """,
            (lot_id,)
        )
        lot = await cur.fetchone()
        if not lot:
            await message.answer("❌ Лот не знайдено")
            await state.clear()
            return

        await db.execute(
            """
            INSERT INTO counter_offers
                (lot_id, sender_user_id, offered_price, message, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', datetime('now'))
            """,
            (lot_id, sender_user_id, price, comment)
        )
        await db.commit()

    await state.clear()

    await message.answer(
        "✅ <b>Пропозицію надіслано!</b>\n\n"
        f"💵 Ціна: <b>{price}</b> грн/т\n"
        f"💬 {comment or '—'}\n\n"
        "Очікуйте відповіді від власника лоту."
    )

    # notify owner
    try:
        await message.bot.send_message(
            lot["owner_telegram_id"],
            "📨 <b>Нова пропозиція!</b>\n\n"
            f"🌾 {lot['crop']}\n"
            f"💰 Ваша ціна: {lot['price']} грн/т\n"
            f"💵 Пропозиція: <b>{price}</b> грн/т\n"
            f"💬 {comment or '—'}\n\n"
            "Переглянути: 🔨 Торг → 📥 Вхідні"
        )
    except Exception:
        pass
