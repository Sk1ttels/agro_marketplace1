"""
Constants for Agro Marketplace Bot
"""

# User roles
ROLE_FARMER = "farmer"
ROLE_BUYER = "buyer"
ROLE_LOGISTIC = "logistic"

ROLES = {
    ROLE_FARMER: "🌾 Фермер / Продавець",
    ROLE_BUYER: "🛒 Покупець / Трейдер",
    ROLE_LOGISTIC: "🚚 Логіст / Перевізник"
}

# Lot types
LOT_TYPE_SELL = "sell"
LOT_TYPE_BUY = "buy"

LOT_TYPES = {
    LOT_TYPE_SELL: "Продам",
    LOT_TYPE_BUY: "Куплю"
}

# Lot statuses
LOT_STATUS_ACTIVE = "active"
LOT_STATUS_INACTIVE = "inactive"
LOT_STATUS_SOLD = "sold"
LOT_STATUS_CLOSED = "closed"

# Offer statuses
OFFER_STATUS_NEW = "new"
OFFER_STATUS_COUNTER = "counter"
OFFER_STATUS_ACCEPTED = "accepted"
OFFER_STATUS_REJECTED = "rejected"
OFFER_STATUS_EXPIRED = "expired"

# Chat statuses
CHAT_STATUS_ACTIVE = "active"
CHAT_STATUS_ENDED = "ended"
CHAT_STATUS_BLOCKED = "blocked"

# Vehicle types
VEHICLE_TYPE_GRAIN = "grain"
VEHICLE_TYPE_TIPPER = "tipper"
VEHICLE_TYPE_TARP = "tarp"

VEHICLE_TYPES = {
    VEHICLE_TYPE_GRAIN: "🚛 Зерновоз",
    VEHICLE_TYPE_TIPPER: "🚜 Самоскид",
    VEHICLE_TYPE_TARP: "🚐 Тент"
}

# Vehicle statuses
VEHICLE_STATUS_AVAILABLE = "available"
VEHICLE_STATUS_BUSY = "busy"
VEHICLE_STATUS_INACTIVE = "inactive"

# Shipment statuses
SHIPMENT_STATUS_ACTIVE = "active"
SHIPMENT_STATUS_IN_PROGRESS = "in_progress"
SHIPMENT_STATUS_COMPLETED = "completed"
SHIPMENT_STATUS_CANCELLED = "cancelled"

# Contact request statuses
CONTACT_REQUEST_PENDING = "pending"
CONTACT_REQUEST_ACCEPTED = "accepted"
CONTACT_REQUEST_REJECTED = "rejected"

# Broadcast statuses
BROADCAST_STATUS_DRAFT = "draft"
BROADCAST_STATUS_SENDING = "sending"
BROADCAST_STATUS_COMPLETED = "completed"
BROADCAST_STATUS_FAILED = "failed"

# Report types
REPORT_TYPE_USER = "user"
REPORT_TYPE_LOT = "lot"
REPORT_TYPE_CHAT = "chat"
REPORT_TYPE_SPAM = "spam"

# Report statuses
REPORT_STATUS_PENDING = "pending"
REPORT_STATUS_REVIEWED = "reviewed"
REPORT_STATUS_RESOLVED = "resolved"
REPORT_STATUS_DISMISSED = "dismissed"

# Ukrainian regions
UKRAINIAN_REGIONS = [
    "Вінницька",
    "Волинська",
    "Дніпропетровська",
    "Донецька",
    "Житомирська",
    "Закарпатська",
    "Запорізька",
    "Івано-Франківська",
    "Київська",
    "Кіровоградська",
    "Луганська",
    "Львівська",
    "Миколаївська",
    "Одеська",
    "Полтавська",
    "Рівненська",
    "Сумська",
    "Тернопільська",
    "Харківська",
    "Херсонська",
    "Хмельницька",
    "Черкаська",
    "Чернівецька",
    "Чернігівська"
]

# Main crops
CROPS = [
    "Пшениця",
    "Кукурудза",
    "Соняшник",
    "Соя",
    "Ячмінь",
    "Ріпак",
    "Овес",
    "Просо",
    "Горох",
    "Гречка",
    "Льон",
    "Інше"
]

# Callback data prefixes
CB_MAIN_MENU = "main_menu"
CB_MARKET = "market"
CB_CREATE_LOT = "create_lot"
CB_VIEW_LOT = "view_lot"
CB_EDIT_LOT = "edit_lot"
CB_DELETE_LOT = "delete_lot"
CB_MY_LOTS = "my_lots"
CB_MATCHES = "matches"
CB_MAKE_OFFER = "make_offer"
CB_VIEW_OFFER = "view_offer"
CB_ACCEPT_OFFER = "accept_offer"
CB_REJECT_OFFER = "reject_offer"
CB_COUNTER_OFFER = "counter_offer"
CB_CHAT = "chat"
CB_START_CHAT = "start_chat"
CB_END_CHAT = "end_chat"
CB_REQUEST_CONTACT = "request_contact"
CB_ACCEPT_CONTACT = "accept_contact"
CB_REJECT_CONTACT = "reject_contact"
CB_BLOCK_USER = "block_user"
CB_REPORT_USER = "report_user"
CB_LOGISTICS = "logistics"
CB_MY_VEHICLES = "my_vehicles"
CB_ADD_VEHICLE = "add_vehicle"
CB_SHIPMENTS = "shipments"
CB_CREATE_SHIPMENT = "create_shipment"
CB_PROFILE = "profile"
CB_ADMIN = "admin"
CB_BROADCAST = "broadcast"
CB_FAVORITES = "favorites"
CB_ADD_FAVORITE = "add_favorite"
CB_REMOVE_FAVORITE = "remove_favorite"
CB_SHARE_LOT = "share_lot"
CB_CALCULATORS = "calculators"
CB_PRICES = "prices"

# Pagination
ITEMS_PER_PAGE = 10

# Anonymous ID prefixes
ANONYMOUS_PREFIX_FARMER = "F"
ANONYMOUS_PREFIX_BUYER = "B"
ANONYMOUS_PREFIX_LOGISTIC = "L"

# Message types
MESSAGE_TYPE_TEXT = "text"
MESSAGE_TYPE_PHOTO = "photo"
MESSAGE_TYPE_DOCUMENT = "document"
MESSAGE_TYPE_VOICE = "voice"
MESSAGE_TYPE_LOCATION = "location"

# Price display
PRICE_NEGOTIABLE = "договірна"

# Date format
DATE_FORMAT = "%d.%m.%Y"
DATETIME_FORMAT = "%d.%m.%Y %H:%M"

# Emojis for UI
EMOJI_MARKET = "🌾"
EMOJI_MATCHES = "🔁"
EMOJI_OFFER = "🤝"
EMOJI_CHAT = "💬"
EMOJI_LOGISTICS = "🚚"
EMOJI_PROFILE = "👤"
EMOJI_ADMIN = "🛠"
EMOJI_FAVORITE = "⭐"
EMOJI_SHARE = "📩"
EMOJI_EDIT = "✏️"
EMOJI_DELETE = "⛔"
EMOJI_BACK = "◀️"
EMOJI_NEXT = "▶️"
EMOJI_ACCEPT = "✅"
EMOJI_REJECT = "❌"
EMOJI_CALCULATOR = "🧮"
EMOJI_PRICES = "📈"
EMOJI_HELP = "🆘"

# Help texts
HELP_TEXT = """
🌾 <b>Агромаркет - Допомога</b>

<b>Основні можливості:</b>

📝 <b>Маркет</b>
• Створюйте оголошення "Куплю/Продам"
• Переглядайте актуальні пропозиції
• Фільтруйте за регіоном та культурою
• Додавайте до обраного

🔁 <b>Зустрічні пропозиції</b>
• Автоматичний підбір покупців/продавців
• Релевантні пропозиції для ваших лотів

🤝 <b>Торг</b>
• Пропонуйте свою ціну
• Контрпропозиції без обмежень
• Прозора історія переговорів

💬 <b>Анонімний чат</b>
• Спілкуйтеся без розкриття даних
• Запит контактів за згодою обох сторін
• Безпечне спілкування

🚚 <b>Логістика</b>
• Додавайте транспорт (для логістів)
• Створюйте заявки на перевезення
• Знаходьте підходящий транспорт

📊 <b>Аналітика</b>
• Середні ціни по культурах
• Тренди ринку
• Калькулятори

👤 <b>Профіль</b>
• Ваші оголошення
• Активні переговори
• Налаштування

<b>Конфіденційність:</b>
Ваші персональні дані не показуються іншим користувачам без вашої згоди.

<b>Підтримка:</b>
За питаннями звертайтесь до адміністраторів через кнопку "Підтримка".
"""
DB_FILE = "agro_bot.db"
