from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.database import ORM
from services.telegram.handlers.analyzer import analyzer
from services.telegram.handlers.home import home, contact
from services.telegram.middlewares.data import DataMiddleware


class TgRegister:
    def __init__(self, dp: Dispatcher, orm: ORM):
        self.dp = dp
        self.orm = orm

    def register(self):
        self._register_handlers()
        self._register_middlewares()

    def _register_handlers(self):
        # home
        self.dp.include_routers(home.router, contact.router)
        # analyzer
        self.dp.include_routers(analyzer.router)

    def _register_middlewares(self):
        scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
        scheduler.start()
        middleware = DataMiddleware(self.orm, scheduler)
        self.dp.callback_query.middleware(middleware)
        self.dp.message.middleware(middleware)
