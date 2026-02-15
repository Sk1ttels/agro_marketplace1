"""
Text formatters and utilities
"""
from datetime import datetime
from typing import Optional
from src.bot.database.models import Lot, User, Offer
from config.constants import DATE_FORMAT, PRICE_NEGOTIABLE

def format_lot_card(lot: Lot, owner: User, show_full: bool = True) -> str:
    """Format lot as text card"""
    import json
    
    type_emoji = "📦" if lot.type == "sell" else "🛒"
    type_text = "ПРОДАМ" if lot.type == "sell" else "КУПЛЮ"
    
    quality = json.loads(lot.quality_json) if isinstance(lot.quality_json, str) else lot.quality_json
    
    text = f"{type_emoji} <b>{type_text}: {lot.crop}</b>\n\n"
    text += f"📊 Обсяг: {lot.volume_tons} тонн\n"
    text += f"📍 Регіон: {lot.region}"
    
    if lot.location:
        text += f", {lot.location}"
    text += "\n"
    
    text += f"💰 Ціна: {lot.price}"
    if lot.price != PRICE_NEGOTIABLE:
        text += " грн/т"
    text += "\n\n"
    
    if quality.get("moisture"):
        text += f"🌡 Вологість: {quality['moisture']}%\n"
    if quality.get("trash"):
        text += f"🗑 Сміття: {quality['trash']}%\n"
    
    if lot.comment and show_full:
        text += f"\n💬 {lot.comment}\n"
    
    text += f"\n🕐 {lot.created_at.strftime(DATE_FORMAT)}\n"
    text += f"👤 {owner.get_anonymous_id()}"
    
    return text

def format_offer_card(offer: Offer, lot: Lot) -> str:
    """Format offer as text card"""
    text = f"🤝 <b>Пропозиція</b>\n\n"
    text += f"Лот: {lot.crop}, {lot.volume_tons}т\n"
    text += f"Запропонована ціна: {offer.price:,.0f} грн/т\n"
    text += f"Обсяг: {offer.volume} тонн\n"
    
    if offer.comment:
        text += f"\n💬 {offer.comment}\n"
    
    text += f"\n🕐 {offer.created_at.strftime(DATE_FORMAT)}"
    
    return text

def format_price(price: float) -> str:
    """Format price with thousands separator"""
    return f"{price:,.0f}".replace(",", " ")
