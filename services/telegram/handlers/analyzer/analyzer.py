import os

from aiogram import Router, F
from aiogram.types import Message

from database.database import ORM
from services.analyzer.analyzer import LogAnalyzer
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.document)
async def document_analyze(message: Message, orm: ORM):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    log = LogAnalyzer(path)
    log_info = log.find_error_solutions()
    model = log.get_model()
    if model:
        if log_info:
            problems = '\n'.join([f"{i}) {p}" for i, p
                                  in enumerate(log_info["solutions"], start=1)])
            text = (f"Инструкция по починке {model[0]}:"
                    f"\nНайденные ошибки: \n{problems}")
            msg = await message.answer(
                text=text, reply_markup=Keyboards.links(log_info["links"]))
        else:
            msg = await message.answer(text="Не найдено ошибок")
    else:
        msg = await message.answer(text=f"Не найдена модель устройства "
                                        f"{log.log_dict['product']}")
    os.remove(path)
    await message.forward(orm.settings.channel_id)
    await msg.forward(orm.settings.channel_id)
