from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import Environ
from database.models import Base
from database.repo.user import UserRepo


class ORM:
    def __init__(self):
        self.settings = Environ()
        self.user_repo: UserRepo = None

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

    async def get_async_sessionmaker(self) -> async_sessionmaker:
        return async_sessionmaker(await self.get_async_engine(),
                                  expire_on_commit=False)

    async def create_repos(self):
        sessionmaker = await self.get_async_sessionmaker()
        self.user_repo = UserRepo(sessionmaker)
