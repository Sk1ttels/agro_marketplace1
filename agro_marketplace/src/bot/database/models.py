"""
Database models for Agro Marketplace Bot
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # farmer/buyer/logistic
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    company: Mapped[Optional[str]] = mapped_column(String(120))
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime)
    settings_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON settings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    lots = relationship("Lot", back_populates="owner", cascade="all, delete-orphan")
    offers_sent = relationship("Offer", foreign_keys="Offer.from_user_id", back_populates="from_user")
    offers_received = relationship("Offer", foreign_keys="Offer.to_user_id", back_populates="to_user")
    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="creator", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"
    
    def get_anonymous_id(self) -> str:
        """Get anonymous display ID"""
        from config.constants import ANONYMOUS_PREFIX_FARMER, ANONYMOUS_PREFIX_BUYER, ANONYMOUS_PREFIX_LOGISTIC
        prefix = {
            "farmer": ANONYMOUS_PREFIX_FARMER,
            "buyer": ANONYMOUS_PREFIX_BUYER,
            "logistic": ANONYMOUS_PREFIX_LOGISTIC
        }.get(self.role, "U")
        return f"{prefix}{self.id:04d}"


class Lot(Base):
    """Lot model (Buy/Sell listing)"""
    __tablename__ = "lots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # buy/sell
    crop: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(100))  # City/village
    quality_json: Mapped[str] = mapped_column(JSON, nullable=False)  # moisture, trash, etc.
    price: Mapped[str] = mapped_column(String(50), nullable=False)  # Price or "договірна"
    comment: Mapped[Optional[str]] = mapped_column(String(700))
    photos_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of file_ids
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    views_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    favorites_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="lots")
    offers = relationship("Offer", back_populates="lot", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint('volume_tons > 0', name='check_volume_positive'),
        Index('idx_lots_active', 'status', 'type', 'crop', 'region'),
    )
    
    def __repr__(self):
        return f"<Lot(id={self.id}, type={self.type}, crop={self.crop}, volume={self.volume_tons}т)>"


class Offer(Base):
    """Offer/Counter-offer model"""
    __tablename__ = "offers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[int] = mapped_column(Integer, ForeignKey("lots.id"), nullable=False, index=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False, index=True)
    history_json: Mapped[str] = mapped_column(JSON, nullable=False)  # Negotiation history
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    lot = relationship("Lot", back_populates="offers")
    from_user = relationship("User", foreign_keys=[from_user_id], back_populates="offers_sent")
    to_user = relationship("User", foreign_keys=[to_user_id], back_populates="offers_received")
    
    __table_args__ = (
        CheckConstraint('price > 0', name='check_price_positive'),
        CheckConstraint('volume > 0', name='check_offer_volume_positive'),
    )
    
    def __repr__(self):
        return f"<Offer(id={self.id}, lot_id={self.lot_id}, price={self.price}, status={self.status})>"


class ChatSession(Base):
    """Chat session between two users"""
    __tablename__ = "chat_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    lot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("lots.id"))
    offer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("offers.id"))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_chat_sessions_users', 'user1_id', 'user2_id', 'status'),
    )
    
    def __repr__(self):
        return f"<ChatSession(id={self.id}, user1={self.user1_id}, user2={self.user2_id})>"


class ChatMessage(Base):
    """Chat message"""
    __tablename__ = "chat_messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    sender_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)  # Text or file_id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, session={self.session_id}, type={self.message_type})>"


class Vehicle(Base):
    """Logistics vehicle"""
    __tablename__ = "vehicles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    body_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # grain/tipper/tarp
    capacity_tons: Mapped[float] = mapped_column(Float, nullable=False)
    count_units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    base_region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    work_regions: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False, index=True)
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="vehicles")
    
    __table_args__ = (
        CheckConstraint('capacity_tons > 0', name='check_capacity_positive'),
        CheckConstraint('count_units > 0', name='check_count_positive'),
    )
    
    def __repr__(self):
        return f"<Vehicle(id={self.id}, type={self.body_type}, capacity={self.capacity_tons}т)>"


class Shipment(Base):
    """Delivery request"""
    __tablename__ = "shipments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cargo_type: Mapped[str] = mapped_column(String(50), nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    from_region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_location: Mapped[Optional[str]] = mapped_column(String(100))
    to_region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    to_location: Mapped[Optional[str]] = mapped_column(String(100))
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime)
    required_body_types: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="shipments")
    
    __table_args__ = (
        CheckConstraint('volume_tons > 0', name='check_shipment_volume_positive'),
    )
    
    def __repr__(self):
        return f"<Shipment(id={self.id}, cargo={self.cargo_type}, volume={self.volume_tons}т)>"


class Favorite(Base):
    """User favorites"""
    __tablename__ = "favorites"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)  # lot/vehicle/shipment
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'item_type', 'item_id', name='uq_user_favorite'),
        Index('idx_favorites_item', 'item_type', 'item_id'),
    )
    
    def __repr__(self):
        return f"<Favorite(user={self.user_id}, type={self.item_type}, item={self.item_id})>"


class ContactRequest(Base):
    """Contact sharing request"""
    __tablename__ = "contact_requests"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    chat_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chat_sessions.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    __table_args__ = (
        UniqueConstraint('from_user_id', 'to_user_id', 'chat_session_id', name='uq_contact_request'),
    )
    
    def __repr__(self):
        return f"<ContactRequest(id={self.id}, from={self.from_user_id}, to={self.to_user_id})>"


class Report(Base):
    """User report"""
    __tablename__ = "reports"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reported_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    report_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    related_id: Mapped[Optional[int]] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    
    def __repr__(self):
        return f"<Report(id={self.id}, type={self.report_type}, status={self.status})>"


class Broadcast(Base):
    """Admin broadcast"""
    __tablename__ = "broadcasts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(20))
    media_file_id: Mapped[Optional[str]] = mapped_column(String(200))
    buttons_json: Mapped[Optional[str]] = mapped_column(Text)
    audience_filter: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    total_users: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    def __repr__(self):
        return f"<Broadcast(id={self.id}, status={self.status}, sent={self.sent_count}/{self.total_users})>"


class Announcement(Base):
    """Announcement/Banner"""
    __tablename__ = "announcements"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(20))
    media_file_id: Mapped[Optional[str]] = mapped_column(String(200))
    buttons_json: Mapped[Optional[str]] = mapped_column(Text)
    audience_filter: Mapped[Optional[str]] = mapped_column(Text)
    show_on: Mapped[str] = mapped_column(String(20), default="start", nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Announcement(id={self.id}, title={self.title}, active={self.active})>"


class PriceAlert(Base):
    """Price alert subscription"""
    __tablename__ = "price_alerts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    crop: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(50))
    price_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    condition: Mapped[str] = mapped_column(String(10), nullable=False)  # above/below
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<PriceAlert(user={self.user_id}, crop={self.crop}, threshold={self.price_threshold})>"


class ActivityLog(Base):
    """User activity log"""
    __tablename__ = "activity_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    
    def __repr__(self):
        return f"<ActivityLog(user={self.user_id}, action={self.action_type})>"
