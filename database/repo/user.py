import os
from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select, update, delete, exists
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from phonenumbers import parse, is_valid_number
from phonenumbers import NumberParseException 
from dotenv import load_dotenv

from database.models import User, Subscription, Transaction
from database.repo.repo import Repo
from database.repo.exceptions import InsufficientFundsError, UserNotFoundError

logger = logging.getLogger(__name__)
load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
class UserRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker 

    async def get_balance(self, user_id: int) -> Decimal:
        async with self.sessionmaker() as session:
            result = await session.scalar(select(User.balance).where(User.user_id == user_id))
            return result or Decimal('0.00')

    async def update_balance(self, user_id: int, amount: Decimal) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                try:
                    # Найти пользователя по полю user_id, а не по первичному ключу
                    user = await session.scalar(select(User).where(User.user_id == user_id))
                    if user is None:
                        logger.error(f"User {user_id} not found")
                        return False

                    user.balance += amount
                    
                    # Создать транзакцию, а не UserRepo
                    transaction = Transaction(
                        user_id=user_id,
                        type="topup",
                        amount=amount
                    )
                    session.add(transaction)
                    
                    await session.commit()
                    
                    logger.info(f"Balance updated for {user_id}: {user.balance}")
                    return True
                except Exception as e:
                    logger.error(f"Error updating balance for user {user_id}: {str(e)}")
                    await session.rollback()
                    return False

    async def deduct_analysis_fee(self, user_id: int, fee: Decimal, crash_key: str, bot: Bot) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверяем по crash_key
                existing = await session.scalar(
                    select(Subscription).where(Subscription.crash_key == crash_key))
                if existing:
                    return True
                # Проверяем по user_id
                existing_user_sub = await session.scalar(
                    select(Subscription).where(Subscription.user_id == user_id))
                if not existing_user_sub:
                    session.add(Subscription(
                        user_id=user_id,
                        crash_key=crash_key,
                        date_start=datetime.now()
                    ))
                user = await session.scalar(select(User).where(User.user_id == user_id))
                if not user or user.balance < fee:
                    return False
                user.balance -= fee
                return True

    async def find_all(self) -> list[User]:
        async with self.sessionmaker() as session:
            query = select(User)
            result = await session.scalars(query)
            return result.all() or []

    async def find_user_by_user_id(self, user_id) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(user_id=user_id)
            return await session.scalar(query) or User()

    async def find_user_by_username(self, username) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(username=username)
            return await session.scalar(query) or User()

    async def save_user(self, message: Message) -> User:
        async with self.sessionmaker() as session:
            existing_user = await session.execute(
                select(User).filter_by(user_id=message.from_user.id)
            )
            existing_user = existing_user.scalar_one_or_none()

            if existing_user:
                return existing_user

            new_user = self.create_user_from_contact(message)
            session.add(new_user)
            await session.commit()

            return new_user


    async def get_users_by_language(self, lang: str) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(User).where(User.lang == lang)
            )
            return result.all()

    @staticmethod
    def _validate_phone_number(number: str) -> bool:
        try:
            return is_valid_number(parse(number, None))
        except NumberParseException:
            return False

    @staticmethod
    def create_user_from_contact(message: Message) -> User:
        user = User()
        contact = message.contact
        user.username = message.from_user.username
        # user.fullname = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        user.user_id = message.from_user.id
        user.phone_number = contact.phone_number
        return user

    async def upsert_user(self, user_id: int = None, **user_data):
        async with self.sessionmaker() as session:
            if user_id is not None:
                async with session.begin():
                    result = await session.execute(
                        select(User).filter_by(user_id=user_id))
                    user = result.scalar_one_or_none()
                    if user:
                        for key, value in user_data.items():
                            setattr(user, key, value)
                    else:
                        user = User(**user_data)
                        session.add(user)
            else:
                user = User(**user_data)
                session.add(user)
            await session.commit()
            return user

    async def delete_user(self, user_id: int) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    delete(User).where(User.user_id == user_id)
                )
                await session.commit()
                return result.rowcount > 0

    async def get_admins(self) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(User).where(User.role == 'admin')
            )
            return result.all()
        
    async def get_user(self, user_id: int):
        async with self.sessionmaker() as session:
            result = await session.execute(
            select(
                User.user_id,
                User.balance,
                User.role
            ).where(User.user_id == user_id)
        )
            
        return result.first()

    async def get_or_create_user(self, user_id: int, **kwargs) -> User:
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await session.scalar(
                    select(User).where(User.user_id == user_id)
                )
                
                if not user:
                    user = User(user_id=user_id, **kwargs)
                    session.add(user)
                    await session.commit()
                
                return user
            
    async def user_exists(self, user_id: int) -> bool:
        async with self.sessionmaker() as session:
            stmt = select(exists().where(User.user_id == user_id))
            return await session.scalar(stmt)
        
    async def get_balance_changes(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime
    ) -> dict:
        """Возвращает изменения баланса за период"""
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(
                    Transaction.type,
                    sum(Transaction.amount).label("total")
                )
                .where(Transaction.user_id == user_id)
                .where(Transaction.timestamp.between(start_date, end_date))
                .group_by(Transaction.type)
            )
            return {row[0]: float(row[1]) for row in result.all()}
        
    async def admin_update_balance(self, admin_id: int, user_id: int, amount: Decimal) -> bool:
        """
        Упрощенное пополнение баланса администратором
        Возвращает True если успешно, False если ошибка
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверяем что администратор существует и имеет права
                admin = await session.get(User, admin_id)
                if not admin or admin.role != 'admin':
                    return False
                
                # Обновляем баланс одним запросом
                result = await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(balance=User.balance + amount)
                    .returning(User.balance)
                )
                
                if not result.scalar_one_or_none():
                    raise UserNotFoundError()
                
                return True

    async def quick_topup(self, user_id: int, amount: Decimal) -> bool:
        """
        Максимально упрощенное пополнение баланса
        Без проверок прав, только базовые проверки
        """
        async with self.sessionmaker() as session:
            try:
                await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(balance=User.balance + amount)
                )
                await session.commit()
                return True
            except:
                await session.rollback()
                return False
    async def update_alance(
        self, 
        user_id: int, 
        amount: Decimal, 
        admin_id: Optional[int] = None,
        transaction_type: str = "manual"
    ) -> None:
        """
        Обновление баланса с проверкой прав и созданием транзакции
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверка прав администратора
                if admin_id:
                    admin = await session.get(User, admin_id)
                    if not admin or admin.role != 'admin':
                        raise PermissionError("Admin rights required")

                # Блокировка строки пользователя
                user = await session.execute(
                    select(User)
                    .where(User.user_id == user_id)
                    .with_for_update()
                )
                user = user.scalar_one_or_none()
                
                if not user:
                    raise UserNotFoundError()

                # Проверка типа данных
                if not isinstance(amount, Decimal):
                    raise TypeError("Amount must be Decimal")

                # Обновление баланса
                new_balance = user.balance + amount
                if new_balance < Decimal('0'):
                    raise InsufficientFundsError("Negative balance not allowed")

                user.balance = new_balance
                
                # Логирование транзакции
                transaction = Transaction(
                    user_id=user_id,
                    type=transaction_type,
                    amount=amount,
                    admin_id=admin_id
                )
                session.add(transaction)

    async def deduct_funds(
        self,
        user_id: int,
        amount: Decimal,
        description: str
    ) -> None:
        """
        Списание средств с баланса
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await session.get(User, user_id, with_for_update=True)
                
                if user.balance < amount:
                    raise InsufficientFundsError(
                        f"Insufficient funds. Balance: {user.balance}, Required: {amount}"
                    )
                
                user.balance -= amount
                
                transaction = Transaction(
                    user_id=user_id,
                    type="payment",
                    amount=-amount,
                    description=description
                )
                session.add(transaction)

    async def add_funds(
        self,
        user_id: int,
        amount: Decimal,
        description: str,
        admin_id: Optional[int] = None
    ) -> None:
        """
        Пополнение баланса
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await session.get(User, user_id, with_for_update=True)
                user.balance += amount
                
                transaction = Transaction(
                    user_id=user_id,
                    type="topup",
                    amount=amount,
                    admin_id=admin_id,
                    description=description
                )
                session.add(transaction)

    async def get_country_code(self, user_id: int) -> str:
        async with self.sessionmaker() as session:
            user = await session.scalar(select(User.country).where(User.user_id == user_id))
            if not user:
                 logger.warning(f"Не удалось получить страну для пользователя {user_id}. Возвращаем US.")
                 return "US"
            country = user.strip().upper()
            logger.info(f"Определена страна для пользователя {user_id}: '{country}'") # Логируем полученную страну
            # Добавляем больше вариантов для России и Казахстана
            if country in ["КАЗАХСТАН", "KAZAKHSTAN", "KZ", "КЗ"]:
                logger.info(f"Страна определена как KZ.")
                return "KZ"
            if country in ["РОССИЯ", "RUSSIA", "RU", "РФ", "RUSSIAN FEDERATION"]:
                 logger.info(f"Страна определена как RU.")
                 return "RU"
                 
            # Если не KZ или RU, возвращаем US как дефолт
            logger.warning(f"Страна '{country}' не распознана как KZ или RU. Возвращаем US.")
            return "US"