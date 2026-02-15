from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)

    role = Column(String, default="guest")
    region = Column(String, default="unknown")

    company_number = Column(String, nullable=True)
    company = Column(String, nullable=True)

    # 🔑 ПІДПИСКА
    subscription_plan = Column(String, default="free")   # free / pro
    subscription_until = Column(DateTime, nullable=True)

    is_banned = Column(Integer, default=0)
