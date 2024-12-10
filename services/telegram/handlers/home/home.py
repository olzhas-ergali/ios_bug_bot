from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from aiogram.types import Message, CallbackQuery
from services.analyzer.nand import NandList
from services.telegram.misc.keyboards import Keyboards
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.i18n import I18n
from database.database import ORM
from database.models import User 
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import LangCallback

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.text == "Главная")
@router.message(Command("start"))
async def home(message: Message, user: User, i18n: I18n):
    reply_markup = Keyboards.home(i18n, user)

    greeting_message = i18n.gettext(
        "Приветствую @{}🙂🤝🏼"
        "\nЯ помогу тебе с анализом сбоев"
        "\nОтправь мне файл и я его проанализирую 🔬",
        locale=user.lang
    ).format(user.username)

    await message.answer(
        greeting_message,
        reply_markup=reply_markup,
        reply_to_message_id=message.message_id
    )


@router.message(F.text == "Инструкция " + "📕")
@router.message(F.text == "Instructions " + "📕")
async def instruction(message: Message, user: User, i18n: I18n):
    await message.answer(
        i18n.gettext(
            "Для отправки файла Panic выполните следующие шаги: \n\n"
            "1. Откройте Настройки.\n"
            "2. Выберите Конфиденциальность и безопасность.\n"
            "3. Перейдите в раздел Аналитика и улучшения.\n"
            "4. Откройте Данные аналитики. \n\n"
            "Найдите в списке файл с названием panic-full и отправьте его на устройство, где работает наш бот. "
            "Для этого используйте кнопку в верхнем правом углу и выберите AirDrop. \n\n"
            "Важно: для получения наиболее точной информации из файла диагностики отправьте несколько последних "
            "файлов panic.\n",
            locale=user.lang),
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id
    )


@router.message(F.text == "Сменить язык " + "🏳️")
@router.message(F.text == "Change language " + "🏳️")
async def change_language(message: Message, user: User, i18n: I18n,state: FSMContext):
    await state.clear()
    await message.answer(i18n.gettext("Выберите язык:", locale=user.lang),
                         reply_markup=Keyboards.lang())


@router.callback_query(LangCallback.filter())
async def change_language_callback(callback: CallbackQuery,
                                   callback_data: LangCallback,
                                   i18n: I18n,
                                   orm: ORM,
                                   state:FSMContext):
    user = await orm.user_repo.upsert_user(callback.from_user.id,
                                          lang=callback_data.lang)
    if callback.message:
        await callback.message.answer(
            i18n.gettext("Язык изменен", locale=user.lang),
            reply_markup=Keyboards.home(i18n, user))
    await state.clear()

@router.message(F.text == "Назад " + "◀️")
@router.message(F.text == "Back " + "◀️")
async def back_to_home(message: Message, user: User, i18n: I18n):
    await message.answer(
        i18n.gettext(
            "Приветствую @{}🙂🤝🏼"
            "\nЯ помогу тебе с анализом сбоев"
            "\nОтправь мне файл и я его проанализирую 🔬",
            locale=user.lang).format(user.username),
        reply_markup=Keyboards.home(i18n, user))


@router.message(F.document.file_name.endswith((".ips", ".txt", ".xlsx")))
async def handle_document_upload(message: Message, user: User, i18n: I18n, orm: ORM, bot: Bot):
    if user.role != 'user':
        await message.answer(i18n.gettext("У вас нет доступа к этой функции", locale=user.lang))
        return

    await message.answer(
        i18n.gettext("Получить консультацию", locale=user.lang),
        reply_markup=Keyboards.get_consultation(i18n, user)
    )

@router.message(F.text == "Получить консультацию 📞")
async def handle_get_consultation(message: Message, user: User, i18n: I18n, orm: ORM, bot: Bot,state:FSMContext):
    await message.answer(i18n.gettext("Ваш запрос на консультацию получен!", locale=user.lang))
    await message.delete()
    await message.answer(
        i18n.gettext("Вы можете вернуться на главную", locale=user.lang),
        reply_markup=Keyboards.back_to_home(i18n, user)
    )

    admins = await orm.user_repo.get_admins()
    
    if admins:
        for admin in admins:
            message_text = i18n.gettext(
                f"Пользователь {user.username} (ID: {user.user_id}) запросил консультацию. "
                f"Вы можете написать ему в чат (ID: {user.phone_number}).", locale=admin.lang
            )
        if user.username:
            message_text += f"\n\nНаписать в Telegram: [t.me/{user.username}](https://t.me/{user.username})"
        await bot.send_message(chat_id=admin.user_id, text=message_text, parse_mode="Markdown")
    await state.finish()

@router.message(F.text == ("Disc guide") + " 📚")
@router.message(F.text == ("Справочник дисков") + " 📚")
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
    await message.answer(i18n.gettext("Мой создатель... жив?", locale=user.lang))


@router.message(F.text == "dokuzu")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("Это мой хозяин!!!!", locale=user.lang))

@router.message(F.text == "onyoka")
async def info(message: Message, user, i18n: I18n):
    await message.answer(i18n.gettext("К Вашим услугам!!!!", locale=user.lang))

@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()