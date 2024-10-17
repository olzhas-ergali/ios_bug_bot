from aiogram import Router, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import I18n

from database.database import ORM
from database.models import User
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

@router.message(F.text == "alfinkly")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("Мои создатель... жив?", locale=user.lang))


@router.message(F.text == "dokuzu")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("Это мой хозяин!!!!", locale=user.lang))


@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()
