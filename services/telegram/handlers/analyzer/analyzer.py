import os

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.analyzer.analyzer import LogAnalyzer
from services.telegram.filters.role import RoleFilter
from .config import log_info_context
from services.telegram.misc.callbacks import ChooseModelCallback, FullButtonCallback
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.document.file_name.endswith(".ips"))
async def document_analyze(message: Message, user, orm: ORM, i18n: I18n):
    await message.chat.do("typing")
    path = f"data/tmp/{message.document.file_name}"
    await message.bot.download(file=message.document.file_id, destination=path)
    log = LogAnalyzer(path, message.from_user.username)
    log_info = log.find_error_solutions()
    model = log.get_model()
    await message.forward(orm.settings.channel_id)
    if model:
        if log_info:
            text = i18n.gettext("Инструкция по починке {}:"
                                "\nНайденные ошибки: \n", locale=user.lang).format(model[0])
            msg = await message.answer(
                text=text)
            await msg.forward(orm.settings.channel_id)

            problems = ""
            for index, problem in enumerate(log_info, start=1):
                sub_solutions = '\n'.join([i for i in problem.get('solutions')])
                problems += f"{index}) {sub_solutions}"

                if problem.get("image"):
                    msg = await message.bot.send_photo(message.from_user.id, FSInputFile(problem["image"]))
                    await msg.forward(orm.settings.channel_id)
                    os.remove(problem.get("image"))

                btns = Keyboards.links(problem["links"], i18n, user)
                if not problem["is_full"]:
                    btns = Keyboards.add_full_btn(btns, problem['error_code'], model[1])

                msg = await message.answer(problems, reply_markup=btns.as_markup())
                await msg.forward(orm.settings.channel_id)
        else:
            msg = await message.answer(text=i18n.gettext(
                "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
                "В скором времени добавим решение по данному анализу!", locale=user.lang))
            await msg.forward(orm.settings.channel_id)
    else:
        msg = await message.answer(text=i18n.gettext("Не найдена модель устройства "
                                                     "{}", locale=user.lang).format(log.log_dict['product']))
        await msg.forward(orm.settings.channel_id)
    os.remove(path)


@router.callback_query(FullButtonCallback.filter())
async def show_full_version(callback: CallbackQuery, callback_data: FullButtonCallback):
    log = LogAnalyzer(username=callback.from_user.username)
    error_code = callback_data.error_code
    if error_code.find('doubledott') != -1:
        error_code = error_code.replace('doubledott', ':')
    log_info = log.find_error_solutions(error=error_code, model=callback_data.model)

    if log_info:
        sub_solutions = '\n'.join([i for i in log_info.get('solutions')])
        await callback.message.edit_text(sub_solutions)


@router.message(F.photo)
async def photo_analyze(message: Message, user, orm: ORM, i18n, state: FSMContext):
    await message.chat.do("typing")
    file = await message.bot.get_file(message.photo[-1].file_id)
    path = f"data/tmp/{file.file_unique_id}"
    await message.bot.download(file=message.photo[-1].file_id, destination=path)
    # photo
    log = LogAnalyzer(path, message.from_user.username, orm.settings.tesseract_path)
    log_info = log.find_error_solutions(True)

    log_info_context.set(log_info)

    if log_info:
        await message.answer(i18n.gettext("Выберите вашу модель телефона", locale=user.lang),
                             reply_markup=Keyboards.models(list(log_info[0].keys())))
    else:
        msg = await message.answer(text=i18n.gettext(
            "К сожалению поиск ключевого слово по нашей базе анализов не дал результата. \n"
            "В скором времени добавим решение по данному анализу!", locale=user.lang))
        await message.forward(orm.settings.channel_id)
        await msg.forward(orm.settings.channel_id)

        await state.clear()

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
    log_info = log_info_context.get()

    await callback.bot.forward_message(orm.settings.channel_id, callback.from_user.id, data.get("message_id"))

    text = i18n.gettext("Инструкция по починке {}:"
                        "\nНайденные ошибки: \n", locale=user.lang).format(callback_data.model)
    msg = await callback.message.answer(text=text)
    await msg.forward(orm.settings.channel_id)

    problems = ""
    links = []
    for index, problem in enumerate(log_info, start=1):
        model = problem.get(callback_data.model)
        sub_solutions = '\n'.join([i for i in model.get('solutions')])
        problems += f"{index}) {sub_solutions}"
        links.extend(model.get('links'))

        if model.get("image"):
            msg = await callback.message.bot.send_photo(callback.message.from_user.id, FSInputFile(model["image"]))
            await msg.forward(orm.settings.channel_id)
            os.remove(model.get("image"))

        msg = await callback.message.answer(problems,
                                            reply_markup=Keyboards.links(model["links"], i18n, user) if model.get("links") else None)
        await msg.forward(orm.settings.channel_id)

    await msg.forward(orm.settings.channel_id)
