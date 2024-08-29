import asyncio
import logging

import coloredlogs
from aiogram import Bot, Dispatcher
from aiogram.utils.i18n import I18n

from config import Environ
from database.database import ORM
from services.telegram.misc.create_dirs import create_dirs
from services.telegram.register import TgRegister


async def start(environment: Environ):
    orm = ORM()

    bot = Bot(token=environment.bot_token)
    dp = Dispatcher()

    await orm.create_repos()
    orm.create_tables(with_drop=False)
    create_dirs()

    i18n = I18n(path="locales", default_locale="kk", domain="messages")

    tg_register = TgRegister(dp, orm, i18n)
    tg_register.register()
    await dp.start_polling(bot)


if __name__ == "__main__":
    env = Environ()
    logging.basicConfig(level=env.logging_level)
    coloredlogs.install()
    asyncio.run(start(env))
