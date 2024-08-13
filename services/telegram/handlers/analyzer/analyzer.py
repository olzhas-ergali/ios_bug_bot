from aiogram import Router, F
from aiogram.types import Message

from services.analyzer.analyzer import LogAnalyzer

router = Router()


@router.message(F.document)
async def document_analyze(message: Message):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    log = LogAnalyzer(path)
    log_info = log.analyze()
    problems = '\n'.join(["- " + p for p in log_info['problems']])
    text = f"Инструкция по починке {log_info['product']}:" \
           f"\nНайденная ошибка: \n{problems}"
    await message.answer(text=text)


@router.message(F.image)
async def document_analyze(message: Message):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    analyzer = LogAnalyzer(path)
    text = analyzer.analyze() or "dsa"
    await message.answer(text=text)
