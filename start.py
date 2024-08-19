import asyncio
import logging

import coloredlogs
from aiogram import Bot, Dispatcher

from config import Environ
from database.database import ORM
from services.telegram.register import TgRegister


async def start(environment: Environ):
    orm = ORM()

    bot = Bot(token=environment.bot_token)
    dp = Dispatcher()
    tg_register = TgRegister(dp, orm)

    await orm.create_repos()
    orm.create_tables(with_drop=True)

    # resume_jobs()
    tg_register.register()
    await dp.start_polling(bot)


if __name__ == "__main__":
    env = Environ()
    logging.basicConfig(level=env.logging_level)
    coloredlogs.install()
    asyncio.run(start(env))
