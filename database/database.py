from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from decimal import Decimal

from config import Environ
from database.models import Base
from database.repo.subscription import SubscriptionRepo
from database.repo.transactions import TransactionRepo
from database.repo.user import UserRepo
from database.repo.currency import CurrencyRepo
from typing import Optional

import logging
import sys

# Настраиваем логирование
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class ORM:
    def __init__(self):
        self.settings = Environ()
        self.user_repo: UserRepo = None
        self.subscription_repo: SubscriptionRepo = None
        self.transactions: TransactionRepo = None
        self.currency_repo: CurrencyRepo = None
        self.async_sessionmaker: Optional[async_sessionmaker] = None

    async def get_async_engine(self, echo=False):
        async_engine = create_async_engine(
            url=self.settings.asyncpg_url(),
            echo=echo
        )
        return async_engine

    def get_engine(self):
        async_engine = create_engine(
            url=self.settings.psycopg_url(),
            echo=True
        )
        return async_engine

    def create_tables(self, with_drop=False):
        engine = self.get_engine()
        if with_drop:
            Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        engine.echo = True

    async def init_currencies(self):
        # Инициализация целевых цен за 1 USD-токен для каждой валюты
        target_prices = {
            "US": {"currency": "USD", "symbol": "$", "price": Decimal("1.0")},
            "KZ": {"currency": "KZT", "symbol": "₸", "price": Decimal("200.0")},
            "RU": {"currency": "RUB", "symbol": "₽", "price": Decimal("55.0")}
        }
        
        for country_code, data in target_prices.items():
            await self.currency_repo.set_rate(
                country_code=country_code,
                currency=data["currency"],
                symbol=data["symbol"],
                target_price=data["price"]
            )

    async def get_async_sessionmaker(self) -> async_sessionmaker:
        if not self.async_sessionmaker:
            async_engine = await self.get_async_engine()
            self.async_sessionmaker = async_sessionmaker(
                async_engine, expire_on_commit=False
            )
        return self.async_sessionmaker
    
    async def create_repos(self):
        async_engine = await self.get_async_engine()
        self.async_sessionmaker = async_sessionmaker(
            async_engine, 
            expire_on_commit=False,
            autoflush=False
        )
        self.user_repo = UserRepo(self.async_sessionmaker)
        self.subscription_repo = SubscriptionRepo(self.async_sessionmaker)
        self.transactions = TransactionRepo(self.async_sessionmaker)
        self.currency_repo = CurrencyRepo(self.async_sessionmaker)
        await self.init_currencies()


