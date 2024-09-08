import os

from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.analyzer.analyzer import LogAnalyzer
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.document.file_name.endswith(".ips"))
async def document_analyze(message: Message, user, orm: ORM, i18n: I18n):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    log = LogAnalyzer(path)
    log_info = log.find_error_solutions()
    model = log.get_model()
    if model:
        if log_info["solutions"] or log_info["links"]:
            problems = '\n'.join([f"{i}) {p}" for i, p
                                  in enumerate(log_info["solutions"], start=1)])
            text = i18n.gettext("Инструкция по починке {}:"
                                "\nНайденные ошибки: \n{}", locale=user.lang).format(model[0], problems)
            msg = await message.answer(
                text=text, reply_markup=Keyboards.links(log_info["links"], i18n, user))
        else:
            msg = await message.answer(text=i18n.gettext(
                "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
                "В скором времени добавим решение по данному анализу!", locale=user.lang))
    else:
        msg = await message.answer(text=i18n.gettext("Не найдена модель устройства "
                                                     "{}", locale=user.lang).format(log.log_dict['product']))
    os.remove(path)
    await message.forward(orm.settings.channel_id)
    await msg.forward(orm.settings.channel_id)
