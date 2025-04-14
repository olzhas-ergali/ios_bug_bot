from typing import Dict, Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Environ
from database.database import ORM
from services.telegram.handlers.registration import ask_contact


class DataMiddleware(BaseMiddleware):
    def __init__(self, orm: ORM, scheduler: AsyncIOScheduler, i18n ):
        self.orm = orm
        self.scheduler = scheduler
        self.i18n = i18n

    async def __call__(
            self,
            handler: Callable[
                [TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        data["env"] = Environ()
        data["orm"] = self.orm
        data["scheduler"] = self.scheduler
        data["i18n"] = self.i18n

        if hasattr(event, "from_user") and event.from_user:
            user = await self.orm.user_repo.find_user_by_user_id(event.from_user.id)
            if user:
                data["user"] = user
                return await handler(event, data)
            else:
                return await ask_contact(event, data["state"], data["orm"], data["i18n"])
    
        return await handler(event, data)


