import os

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.analyzer.analyzer import LogAnalyzer
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import ChooseModelCallback
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


@router.message(F.photo)
async def photo_analyze(message: Message, user, orm: ORM, i18n, state: FSMContext):
    await message.chat.do("typing")
    file = await message.bot.get_file(message.photo[-1].file_id)
    path = f"data/tmp/{file.file_unique_id}"
    await message.bot.download(file=message.photo[-1].file_id, destination=path)
    # photo
    log = LogAnalyzer(path, orm.settings.tesseract_path)
    log_info = log.find_error_solutions(True)

    await state.update_data(log_info)
    for i in log_info:
        if log_info[i]["solutions"] or log_info[i]["links"]:
            await message.forward(orm.settings.channel_id)
            await message.answer(i18n.gettext("Выберите вашу модель телефона", locale=user.lang),
                                 reply_markup=Keyboards.models(list(log_info.keys())))
    else:
        msg = await message.answer(text=i18n.gettext(
            "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
            "В скором времени добавим решение по данному анализу!", locale=user.lang))
        await message.forward(orm.settings.channel_id)
        await msg.forward(orm.settings.channel_id)

    # if model:
    #     if log_info["solutions"] or log_info["links"]:
    #         problems = '\n'.join([f"{i}) {p}" for i, p
    #                               in enumerate(log_info["solutions"], start=1)])
    #         text = i18n.gettext("Инструкция по починке {}:"
    #                             "\nНайденные ошибки: \n{}", locale=user.lang).format(model[0], problems)
    #         msg = await message.answer(
    #             text=text, reply_markup=Keyboards.links(log_info["links"], i18n, user))
    #     else:
    #         msg = await message.answer(text=i18n.gettext(
    #             "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
    #             "В скором времени добавим решение по данному анализу!", locale=user.lang))
    # else:
    #     msg = await message.answer(text=i18n.gettext("Не найдена модель устройства "
    #                                                  "{}", locale=user.lang).format(log.log_dict['product']))
    os.remove(path)

@router.callback_query(ChooseModelCallback.filter())
async def choose_model(callback: CallbackQuery,
                       callback_data: ChooseModelCallback,
                       state: FSMContext,
                       i18n: I18n,
                       orm: ORM,
                       user):
    await callback.message.delete()

    data = await state.get_data()

    log_info = data.get(callback_data.model)

    if log_info["solutions"] or log_info["links"]:
        problems = '\n'.join([f"{i}) {p}" for i, p
                              in enumerate(log_info["solutions"], start=1)])
        text = i18n.gettext("Инструкция по починке {}:"
                            "\nНайденные ошибки: \n{}", locale=user.lang).format(callback_data.model, problems)
        msg = await callback.message.answer(
            text=text, reply_markup=Keyboards.links(log_info["links"], i18n, user))
    else:
        msg = await callback.message.answer(text=i18n.gettext(
            "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
            "В скором времени добавим решение по данному анализу!", locale=user.lang))

    await msg.forward(orm.settings.channel_id)
