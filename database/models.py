from datetime import datetime
from typing import Annotated

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

intpk = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
created_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"))]
updated_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"),
                            onupdate=text("TIMEZONE('utc', now())"))]


class Base(DeclarativeBase):
    __table_args__ = {'extend_existing': True}


class User(Base):
    __tablename__ = "users"

    id: Mapped[intpk]
    user_id: Mapped[int]
    username: Mapped[str]
    fullname: Mapped[str] = mapped_column(nullable=True)
    affiliate: Mapped[str] = mapped_column(nullable=True)
    city: Mapped[str] = mapped_column(nullable=True)
    """
    guest: null in fullname, affiliate, city, phone_number
    no_access: have all datas. wait access from admin
    user: have all user privileges
    admin: have all privileges
    """
    role: Mapped[str] = mapped_column(default="guest")
    phone_number: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[created_at_pk]
    updated_at: Mapped[updated_at_pk]

    def get_null_columns(self):
        result = []
        if not self.fullname:
            result.append("fullname")
        if not self.affiliate:
            result.append("affiliate")
        if not self.city:
            result.append("city")
        if not self.phone_number:
            result.append("phone_number")
        return result
