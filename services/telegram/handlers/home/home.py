from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.i18n import I18n

from database.database import ORM
from database.models import User
from services.analyzer.nand import NandList
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import HomeCallback, LangChangeCallBack
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.text == "Главная")
@router.message(Command("start"))
async def home(message: Message, user: User, i18n: I18n):
    await message.answer(i18n.gettext("Приветствую @{}🙂🤝🏼"
                                      "\nЯ помогу тебе с анализом сбоев"
                                      # "\nОтправь мне файл или изображение и я его проанализирую 🔬"
                                      "\nОтправь мне файл и я его проанализирую 🔬",
                                      locale=user.lang).format(user.username),
                         reply_markup=Keyboards.home(i18n, user)
                         )


@router.callback_query(HomeCallback.filter(F.action == "instruction"))
async def instruction(callback: CallbackQuery, user, i18n: I18n):
    await callback.message.edit_text(
        i18n.gettext("Для отправки файла Panic выполните следующие шаги: \n\n"
                     "1. Откройте Настройки.\n"
                     "2. Выберите Конфиденциальность и безопасность.\n"
                     "3. Перейдите в раздел Аналитика и улучшения.\n"
                     "4. Откройте Данные аналитики. \n\n"
                     "Найдите в списке файл с названием panic-full и отправьте его на устройство, где работает наш бот. Для этого используйте кнопку в верхнем правом углу и выберите AirDrop. \n\n"
                     "Важно: для получения наиболее точной информации из файла диагностики отправьте несколько последних файлов panic.\n",
                     locale=user.lang),
        reply_markup=Keyboards.back_to_home(i18n, user)
    )


@router.callback_query(HomeCallback.filter(F.action == "back_to_home"))
async def instruction(callback: CallbackQuery, user: User, i18n: I18n):
    await callback.message.edit_text(i18n.gettext("Приветствую @{}🙂🤝🏼"
                                                  "\nЯ помогу тебе с анализом сбоев"
                                                  # "\nОтправь мне файл или изображение и я его проанализирую 🔬"
                                                  "\nОтправь мне файл и я его проанализирую 🔬",
                                                  locale=user.lang).format(user.username),
                                     reply_markup=Keyboards.home(i18n, user)
                                     )


@router.callback_query(LangChangeCallBack.filter(F.action == "change"))
async def instruction(callback: CallbackQuery, user: User, i18n: I18n):
    await callback.message.delete()
    await callback.message.answer(i18n.gettext("Выберите язык", user.lang), reply_markup=Keyboards.lang(True))


@router.callback_query(LangChangeCallBack.filter(F.action == "changed"))
async def instruction(callback: CallbackQuery, callback_data: CallbackData, i18n: I18n, orm: ORM):
    user = await orm.user_repo.upsert_user(callback.from_user.id, lang=callback_data.lang)
    await callback.message.delete()
    await callback.message.answer(i18n.gettext("Приветствую @{}🙂🤝🏼"
                                               "\nЯ помогу тебе с анализом сбоев"
                                               # "\nОтправь мне файл или изображение и я его проанализирую 🔬"
                                               "\nОтправь мне файл и я его проанализирую 🔬",
                                               locale=user.lang).format(user.username),
                                  reply_markup=Keyboards.home(i18n, user)
                                  )


@router.inline_query(F.query.startswith('disk '))
async def find_disk(inq: InlineQuery):
    query = inq.query[5:]
    results = []
    if query:
        nand = NandList()
        models = nand.get_models()
        if query != '':
            models = list(filter(lambda x: x['name'].lower().find(query) != -1, models))
        for model in (models if len(models) < 50 else models[:50]):
            results.append(
                InlineQueryResultArticle(
                    id=str(model['row']),
                    title=f'{model["name"]}',
                    input_message_content=InputTextMessageContent(
                        message_text="/disk\n"
                                     "Диск {}\n"
                                     "Номер: {}\n".format(model['name'], model['row']),
                        parse_mode=ParseMode.HTML
                    )
                )
            )
    await inq.answer(results=results, cache_time=10)


@router.message(Command("disk"))
async def find_command(message: Message, user: User, orm: ORM, i18n: I18n):
    model_name = message.text.split("\n")[1].split()[-1]
    model_row = message.text.split("\n")[2].split()[-1]

    nand = NandList()
    answer = nand.find_info(dict(name=model_name, row=model_row), user.lang)
    if answer:
        await message.answer(answer)
    else:
        await message.answer(i18n.gettext("К сожалению данные по {} не найдены", locale=user.lang).format(model_name))


@router.message(F.text == "alfinkly")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("Мои создатель... жив?", locale=user.lang))


@router.message(F.text == "dokuzu")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("Это мой хозяин!!!!", locale=user.lang))


@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()
