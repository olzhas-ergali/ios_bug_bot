from aiogram import Router, F
from aiogram.types import Message

from services.analyzer.analyzer import LogAnalyzer
from services.telegram.misc.keyboards import Keyboards

router = Router()


@router.message(F.document)
async def document_analyze(message: Message):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    log = LogAnalyzer(path)
    log_info = log.analyze()
    if log_info:
        problems = '\n'.join(["- " + p for p in log_info['problems']])
        text = f"Инструкция по починке {log_info['product']}:" \
               f"\nНайденные ошибки: \n{problems}"
        await message.answer(text=text, reply_markup=Keyboards.link("https://youtube.com"))
    else:
        await message.answer(text="Не найдено ошибок")


# @router.message(F.image)
# async def document_analyze(message: Message):
#     await message.chat.do("typing")
#     path = f"data/tmp/{message.document.file_name}"
#     await message.bot.download(file=message.document.file_id, destination=path)
#     analyzer = LogAnalyzer(path)
#     text = analyzer.analyze() or "dsa"
#     await message.answer(text=text)
