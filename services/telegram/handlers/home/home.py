from aiogram import Router, F, Bot

from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hcode
from services.telegram.handlers.states import DeleteUserStates
from services.analyzer.nand import NandList
from services.telegram.misc.keyboards import Keyboards
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.utils.i18n import I18n
from database.database import ORM
from database.models import User 
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import LangCallback,UserListPagination 


router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))
CHANNEL_URL = "https://t.me/Yourrepairassistant"


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

@router.callback_query(F.data == "users_list")
async def show_users_list(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции.", locale=user.lang))
        return
    
    await show_users_page(callback, orm, i18n, user, page=0)

@router.callback_query(UserListPagination.filter())
async def navigate_users_list(callback: CallbackQuery, callback_data: UserListPagination, orm: ORM, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции.", locale=user.lang))
        return
    
    await show_users_page(callback, orm, i18n, user, page=callback_data.page)

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_panel(callback: CallbackQuery, i18n: I18n, user: User):
    await callback.message.edit_text(
        i18n.gettext("Добро пожаловать в админ панель!", locale=user.lang),
        reply_markup=Keyboards.admin_panel(i18n, user)
    )

@router.callback_query(F.data == "delete_user_by_id")
async def ask_for_user_id(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции.", locale=user.lang))
        return

    await state.set_state(DeleteUserStates.waiting_for_user_id)
    await callback.message.answer(i18n.gettext("Введите user_id пользователя, которого хотите удалить:", locale=user.lang))
    await callback.answer()

@router.message(DeleteUserStates.waiting_for_user_id)
async def delete_user_by_id(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    try:
        user_id = int(message.text)  
        user_to_delete = await orm.user_repo.find_user_by_user_id(user_id) 

        if user_to_delete:
            await orm.user_repo.delete(user_to_delete)
            await message.answer(i18n.gettext("Пользователь удален!", locale=user.lang))
        else:
            await message.answer(i18n.gettext("Пользователь с таким ID не найден.", locale=user.lang))

    except ValueError:
        await message.answer(i18n.gettext("Неверный формат user_id. Пожалуйста, введите число.", locale=user.lang))
    except Exception as e:
        print(f"Error deleting user: {e}")
        await message.answer(i18n.gettext("Ошибка при удалении пользователя.", locale=user.lang))
    finally:
        await state.clear()

async def show_users_page(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User, page: int):
    users = await orm.user_repo.find_all()
    
    users_per_page = 5
    total_pages = (len(users) + users_per_page - 1) // users_per_page
    start_idx = page * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users[start_idx:end_idx]
    
    message_parts = [i18n.gettext("📊 Список всех пользователей:", locale=user.lang) + "\n"]
    
    for idx, list_user in enumerate(page_users, start=start_idx + 1):
        user_info = (
            f"🔹 <b>{idx}. {hcode(list_user.username or 'Без username')}</b>\n"
            f"🆔 <i>ID:</i> {hcode(list_user.user_id)}\n"
            f"👤 <i>Роль:</i> {hcode(list_user.role)}\n"
            f"🌍 <i>Язык:</i> {hcode(list_user.lang)}\n"
            f"📱 <i>Телефон:</i> {hcode(list_user.phone_number or 'Не указан')}\n"
            f"<i>{'─' * 30}</i>"
        )
        message_parts.append(user_info)
    
    message_parts.append(f"\n{i18n.gettext('Всего пользователей', locale=user.lang)}: {len(users)}")
    
    full_message = "".join(message_parts)
    keyboard = Keyboards.get_users_list_keyboard(total_pages, page, i18n, user)
    
    await callback.message.edit_text(
        full_message,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    await callback.answer()


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

@router.message(F.text == "Наш канал " + "👥")
@router.message(F.text == "Our channel " + "👥")
async def open_channel(message: Message):
    await message.answer(f"Перейдите по ссылке: {CHANNEL_URL}")

@router.callback_query(F.data == "get_consultation")
async def callback_get_consultation(callback_query: CallbackQuery, user: User, bot: Bot, i18n: I18n, orm: ORM):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        i18n.gettext("Ваш запрос на консультацию получен!", locale=user.lang)
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


@router.message(F.text == ("Disc directory") + " 📚")
@router.message(F.text == ("Справочник дисков") + " 📚")
async def send_disk_guide(message: Message):
    keyboard = get_inline_button()
    await message.answer(
        "Нажмите кнопку ниже, чтобы начать поиск дисков:",
        reply_markup=keyboard,
    )
    

def get_inline_button():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Искать диск 🔍",
                    switch_inline_query_current_chat="disk ",
                )
            ]
        ]
    )
    return keyboard

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

@router.message(F.text == "Admin panel ⚙️")
@router.message(F.text == "Админ панель ⚙️")
async def open_admin_panel(message: Message, user: User, i18n: I18n):
    if user.role == 'admin':
        admin_keyboard = Keyboards.admin_panel(i18n, user)
        await message.answer(i18n.gettext("Добро пожаловать в админ панель!", locale=user.lang), reply_markup=admin_keyboard)
    else:
        await message.answer(i18n.gettext("У вас нет доступа к админ панели.", locale=user.lang))


@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()