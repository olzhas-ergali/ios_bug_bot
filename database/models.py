from datetime import datetime
from typing import Annotated, Optional
from decimal import Decimal
from sqlalchemy import Column, text, BigInteger, ForeignKey, DateTime, func, Boolean,String, Numeric, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

intpk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]
created_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"))]
updated_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"),
                            onupdate=text("TIMEZONE('utc', now())"))]


class Base(DeclarativeBase):
    __table_args__ = {'extend_existing': True}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index('ix_users_balance', 'balance'),
        Index('ix_users_role', 'role'),
        Index('ix_users_lang', 'lang'),
        Index('ix_user_id', 'user_id', postgresql_using='hash')
    )
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(nullable=True)
    fullname: Mapped[str] = mapped_column(nullable=True)
    affiliate: Mapped[str] = mapped_column(nullable=True)
    city: Mapped[str] = mapped_column(nullable=True)
    country: Mapped[str] = mapped_column(nullable=True)
    """
    guest: null in fullname, affiliate, city, phone_number
    no_access: have all datas. wait access from admin
    user: have all user privileges
    admin: have all privileges
    """
    role: Mapped[str] = mapped_column(String(20), default="guest") 
    lang: Mapped[str] = mapped_column(default="ru")
    phone_number: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[created_at_pk]
    updated_at: Mapped[updated_at_pk]
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)



    def get_null_columns(self):
        result = []
        if not self.fullname:
            result.append("fullname")
        if not self.affiliate:
            result.append("affiliate")
        if not self.city:
            result.append("city")
        if not self.country:
            result.append("country")
        if not self.phone_number:
            result.append("phone_number")
        result.append("lang")
        return result


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index('ix_subscriptions_crash_key', 'crash_key', unique=True),
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    date_start = mapped_column(DateTime)
    crash_key = mapped_column(String(255), unique=True)
    date_end = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_warn = mapped_column(Boolean, default=False)

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index('ix_transactions_user_id', 'user_id'),
        Index('ix_transactions_timestamp', 'timestamp'),
    )
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'topup', 'payment', 'refund'
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)  # Используем Python datetime
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger)

class CurrencyRate(Base):
    __tablename__ = "currency_rates"
    
    id: Mapped[intpk]
    country_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    symbol: Mapped[str] = mapped_column(String(5), nullable=False)
    target_price_per_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[created_at_pk]
    updated_at: Mapped[updated_at_pk]