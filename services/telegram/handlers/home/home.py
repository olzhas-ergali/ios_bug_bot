from aiogram import Router, F, Bot
from decimal import Decimal, InvalidOperation
import logging
import re
from database.repo.user import UserRepo
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hcode
from services.telegram.handlers.states import DeleteUserStates
from services.analyzer.nand import NandList
from services.telegram.handlers.admin.main import BalanceService
from services.telegram.misc.keyboards import Keyboards
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.utils.i18n import I18n
from database.database import ORM
from database.repo.exceptions import UserNotFoundError, InvalidAmountError
from services.telegram.filters.role import RoleFilter
from aiogram.filters import StateFilter

from database.models import User 
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import LangCallback,UserListPagination 
from services.telegram.handlers.states import BalanceStates,AdminStates

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))
CHANNEL_URL = "https://t.me/Yourrepairassistant"
logger = logging.getLogger(__name__)


@router.message(Command("balance"))
async def show_user_balance(message: Message, orm: ORM):
    user_repo = UserRepo(await orm.get_async_sessionmaker())
    balance = await user_repo.get_balance(message.from_user.id)
    if balance is not None:
        await message.answer(f"💰 Ваш текущий баланс: {balance:.2f}₸")
    else:
        await message.answer("😕 Баланс не найден. Вы зарегистрированы?")

@router.message(Command("admin_balance"))
async def show_admin_menu(message: Message):
    await message.answer("🔧 Меню управления балансом:", reply_markup=Keyboards.admin_balance_menu())


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

@router.message(F.text == "Пополнить баланс 💳")
async def request_topup_balance(message: Message, orm: ORM, i18n: I18n, user: User):
    admins = await orm.user_repo.get_admins()
    
    if not admins:
        await message.answer("Ошибка: администратор не найден.")
        return

    admin_contacts = "\n".join([f"@{admin.username}" for admin in admins if admin.username])
    await message.answer(f"Для пополнения баланса свяжитесь с администратором:\n{admin_contacts}")

    for admin in admins:
        await message.bot.send_message(
            admin.user_id, 
            f"Пользователь @{user.username} ({user.user_id}) запросил пополнение баланса.",
            reply_markup=Keyboards.back_to_home(i18n, user)
        )

@router.message(F.text.regexp(r"^\d+\s+\d+$"), RoleFilter(roles=["admin"]))
async def admin_manual_topup(message: Message, orm: ORM):
    try:
        user_id_str, amount_str = message.text.strip().split()
        user_id = int(user_id_str)
        amount = Decimal(amount_str)

        user = await orm.user_repo.find_user_by_user_id(user_id)
        if not user:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
            return

        success = await orm.user_repo.update_balance(user_id, amount)
        if not success:
            await message.answer("❌ Не удалось обновить баланс.")
            return

        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount}₸")

    except Exception as e:
        logger.error(f"Ошибка пополнения: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при пополнении. Проверь данные.")



@router.callback_query(lambda c: c.data.startswith("request_topup"))
async def request_topup(callback: CallbackQuery, orm: ORM):
    user_id = int(callback.data.split(":")[1])

    admins = await orm.user_repo.get_admins()
    if not admins:
        await callback.answer("Ошибка: администратор не найден.", show_alert=True)
        return

    for admin in admins:
        message = await orm.user_repo.request_balance_topup(user_id, admin.user_id)
        await callback.bot.send_message(admin.user_id, message)

    await callback.answer("Запрос на пополнение отправлен администратору.", show_alert=True)

@router.callback_query(F.data.startswith("topup:"))
async def fast_topup(callback: CallbackQuery, orm: ORM):
    _, user_id, amount = callback.data.split(":")
    user_id = int(user_id)
    amount = Decimal(amount)
    
    await orm.user_repo.update_balance(user_id, amount)
    await callback.message.edit_text(
        f"✅ Пополнено {amount}₸ пользователю {user_id}",
        reply_markup=None
    )

@router.callback_query(F.data.startswith("topup_custom:"))
async def ask_custom_amount(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split(":")[1])
    await state.set_data({"user_id": user_id})
    await callback.message.answer("Введите сумму для пополнения:")
    await callback.answer()

@router.message(F.text.isdigit())
async def process_custom_topup(message: Message, state: FSMContext, orm: ORM):
    data = await state.get_data()
    user_id = data["user_id"]
    amount = Decimal(message.text)
    
    await orm.user_repo.update_balance(user_id, amount)
    await message.answer(f"✅ Пополнено {amount}₸ пользователю {user_id}")
    await state.clear()

@router.message(F.text.startswith("+"))
async def quick_topup_handler(message: Message, user: User, orm: ORM, i18n: I18n):
    try:
        if user.role != 'admin':
            await message.answer("⛔ Доступ запрещен")
            return

        parts = message.text.split()
        if len(parts) != 3 or not parts[1].isdigit():
            await message.answer("❌ Неверный формат: Используйте + [user_id] [amount]")
            return

        user_id = int(parts[1])
        amount = Decimal(parts[2])

        if not await orm.user_repo.user_exists(user_id):
            await message.answer(f"👤 Пользователь {user_id} не найден")
            return

        success = await orm.user_repo.update_balance(user_id, amount)
        if not success:
            await message.answer("❌ Ошибка при обновлении баланса")
            return
        
        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount}₸")

    except ValueError as e:
        await message.answer(f"❌ Ошибка формата данных: {str(e)}")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
        await message.answer("⚠️ Произошла системная ошибка")

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

@router.message(F.text.contains("Мой баланс"))
@router.message(F.text == "Мой баланс 💰")
async def show_balance(message: Message, user: User, orm: ORM, i18n: I18n):
    balance = await orm.user_repo.get_balance(user.user_id)
    await message.answer(
        i18n.gettext("Ваш текущий баланс: {balance}₸", locale=user.lang).format(balance=balance),
        reply_markup=Keyboards.home(i18n, user)
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
        
@router.callback_query(F.data == "set_pricing")
async def set_pricing(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новую стоимость анализа:")
    await state.set_state(BalanceStates.waiting_for_pricing)

@router.message(BalanceStates.waiting_for_pricing)
async def update_pricing(message: Message, orm: ORM):
    try:
        global PRICE_PER_ANALYSIS
        PRICE_PER_ANALYSIS = float(message.text)
        await message.answer(f"Новая стоимость установлена: {PRICE_PER_ANALYSIS}₸")
    except ValueError:
        await message.answer("Ошибка! Введите число")

@router.callback_query(F.data == "users_list")
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
            f"🆔 {hcode(list_user.user_id)} — 💰 {list_user.balance}₸"
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

@router.callback_query(F.data == "admin_topup", RoleFilter(roles=["admin"]))
async def start_topup(callback: CallbackQuery, state: FSMContext, i18n: I18n):
    """Инициализация пополнения баланса"""
    try:
        await state.set_state(AdminStates.admin_topup_wait)
        await callback.message.answer(
            i18n.gettext(
                "enter_user_id_and_amount",
                locale=callback.from_user.language_code
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in start_topup: {str(e)}", exc_info=True)
        await callback.message.answer(i18n.gettext("server_error"))

@router.callback_query(F.data.startswith("topup:"))
async def process_topup(callback: CallbackQuery):
    amount = Decimal(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    orm = ORM()
    async with orm.async_session() as session:
        await session.execute(
            f"UPDATE users SET balance = balance + {amount} WHERE user_id = {user_id}"
        )
        await session.commit()
    
    await callback.answer(f"Ваш баланс пополнен на {amount}₸")

@router.callback_query(F.data == "admin_check_balance")
async def ask_user_id_for_check(callback: CallbackQuery, state: FSMContext):
    await state.set_state("admin_check_balance_wait")
    await callback.message.answer("Введите user_id для проверки:")

@router.message(StateFilter("admin_check_balance_wait"))  
async def check_balance(message: Message, state: FSMContext, orm: ORM):
    try:
        user_id = int(message.text.strip())
        balance = await orm.user_repo.get_balance(user_id)
        if balance is not None:
            await message.answer(f"Баланс пользователя {user_id}: {balance:.2f}₸")
        else:
            await message.answer("Пользователь не найден.")
    except ValueError:
        await message.answer("Ошибка: введите корректный user_id (должно быть целое число).")
    except Exception as e:
        await message.answer(f"Произошла ошибка: {str(e)}")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_history")
async def ask_user_id_for_history(callback: CallbackQuery, state: FSMContext):
    await state.set_state("admin_history_wait")
    await callback.message.answer("Введите user_id для просмотра истории:")

@router.message(RoleFilter("admin_history_wait"))
async def show_history(message: Message, state: FSMContext, orm: ORM):
    try:
        user_id = int(message.text.strip())
        history = await orm.transactions.get_last(user_id, limit=5)
        if not history:
            await message.answer("Нет истории операций.")
            return

        text = "Последние операции:\n"
        for t in history:
            text += f"- {t['timestamp']} | {t['type']} | {t['amount']}₸\n"

        await message.answer(text)
    except:
        await message.answer("Ошибка.")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_reset_balance")
async def ask_user_id_for_reset(callback: CallbackQuery, state: FSMContext):
    await state.set_state("admin_reset_wait")
    await callback.message.answer("Введите user_id для обнуления баланса:")

@router.message(RoleFilter("admin_reset_wait"))
async def reset_balance(message: Message, state: FSMContext, orm: ORM):
    try:
        user_id = int(message.text.strip())
        await orm.user_repo.set_balance(user_id, 0)
        await orm.transactions.log(user_id, "reset", 0)
        await message.answer("Баланс обнулён.")
    except:
        await message.answer("Ошибка.")
    finally:
        await state.clear()

