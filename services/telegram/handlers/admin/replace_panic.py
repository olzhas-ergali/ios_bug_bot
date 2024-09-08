import shutil
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message

from database.database import ORM
from services.analyzer.xlsx import is_valid_panic_xlsx
from services.telegram.filters.role import RoleFilter
from aiogram.utils.i18n import I18n

from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin"]))

timestamp = datetime.now().strftime("%Y_%m_%d-%H:%M")
panic_codes = dict(
    new=f"./data/verifying.panic_codes.xlsx",
    exist=f"./data/panic_codes.xlsx",
    old=f"./data/old_panics/panic_codes_{timestamp}.xlsx",
    name="panic_codes.xlsx"
)
cities = dict(
    new=f"./data/verifying.cities.xlsx",
    exist=f"./data/cities.xlsx",
    old=f"./data/old_cities/cities_{timestamp}.xlsx",
    name="cities.xlsx"
)


@router.message(F.document.file_name.endswith(".xlsx"))
async def replace_panic_file(message: Message, i18n: I18n, orm: ORM):
    await message.chat.do("typing")
    if message.document.file_name.startswith("panic_codes"):
        paths = panic_codes
    elif message.document.file_name.startswith("cities"):
        paths = cities
    else:
        return await message.answer(i18n.gettext("Можно заменить только файлы cities и panic_codes❗️"))

    await message.bot.download(file=message.document.file_id, destination=paths["new"])
    if is_valid_panic_xlsx(paths["new"]):
        shutil.move(paths["exist"], paths["old"])
        shutil.move(paths["new"], paths["exist"])
        await message.send_copy(orm.settings.channel_id)
        await message.bot.send_message(orm.settings.channel_id, text=i18n.gettext(f"Файл {paths['name']} заменен"))
        return await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен"))
    await message.send_copy(orm.settings.channel_id)
    await message.bot.send_message(orm.settings.channel_id,
                                   text=i18n.gettext(f"Файл {paths['name']} имеет неправильную структуру"))
    return await message.answer(text=i18n.gettext(f"Файл {paths['name']} имеет неправильную структуру"))
