from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.telegram.filters.registration import RegistrationFilter
from services.telegram.misc.callbacks import LangCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.handlers.states import RegistrationStates  

router = Router()

@router.message(F.text, Command("start"))
async def ask_contact(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    if not user:
        user = await orm.user_repo.create_user(
            user_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            last_name=message.from_user.last_name or "",
            username=message.from_user.username or "",
            phone_number=None,  # Ожидаем номер телефона
            lang=None,  # Ожидаем выбор языка
            fullname=None,  # Ожидаем ФИО
            affiliate=None,  # Ожидаем место работы
            country=None,  # Ожидаем страну
            city=None,  # Ожидаем город
            role="guest"
        )
    
    await state.update_data(columns=user.get_null_columns())
    msg = await message.answer(
        text='Для регистрации поделитесь, пожалуйста, номером телефона, нажав на кнопку "Поделиться номером телефона" ниже 👇\n\n'
             'For registration, please share your phone number by clicking the "Share Phone Number" button below 👇\n\n'
             'Название кнопки: "Поделиться номером телефона" / Button name: "Share Phone Number"',
        reply_markup=Keyboards.send_phone(i18n, user)
    )
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_contact)

@router.message(F.contact, RegistrationFilter(filter_column="lang"), RegistrationStates.waiting_for_contact) 
async def process_contact(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.save_user(message)
    data = await state.get_data()

    columns = data.get("columns", [])
    columns = [col for col in columns if col != "phone_number"] 
    await state.update_data(columns=columns)

    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Выберите язык", user.lang), reply_markup=Keyboards.lang())
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_language)  


@router.callback_query(LangCallback.filter(), RegistrationFilter(filter_column="fullname"), RegistrationStates.waiting_for_language)  
async def ask_fullname(callback: CallbackQuery, callback_data: LangCallback, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.upsert_user(callback.from_user.id, lang=callback_data.lang)
    await callback.message.delete()
    msg = await callback.message.answer(text=i18n.gettext("Как вас зовут?", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_fullname) 


@router.message(F.text, RegistrationFilter(filter_column="affiliate"), RegistrationStates.waiting_for_fullname) 
async def ask_affiliate(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, fullname=message.text)
    data = await state.get_data()

    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Где вы работаете?", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_affiliate)  


@router.message(F.text, RegistrationFilter(filter_column="country"), RegistrationStates.waiting_for_affiliate)  
async def ask_country(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, affiliate=message.text)
    data = await state.get_data()

    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Введите страну", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_country)  


@router.message(F.text, RegistrationFilter(filter_column="city"), RegistrationStates.waiting_for_country)
async def ask_city(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, country=message.text)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Введите город", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_city)  


@router.message(F.text, RegistrationStates.waiting_for_city)
async def finalize_registration(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    
    user = await orm.user_repo.upsert_user(message.from_user.id, city=message.text, role="no_access")

    text_admins = i18n.gettext("Имя: {}\n"
                              "Место работы: {}\n"
                              "Страна: {}\n"
                              "Город: {}\n"
                              "Номер: {}").format(
        user.fullname, user.affiliate, user.country, user.city, user.phone_number
    )

    await message.bot.send_message(
        orm.settings.application_channel_id,
        text=text_admins,
        reply_markup=Keyboards.guest(message.from_user.id, i18n, user)
    )

    data = await state.get_data()

    try:
        await message.bot.delete_message(
            chat_id=message.from_user.id,
            message_id=data["msg_id"],
        )
    except Exception as e:
        print(f"Error deleting message: {e}")

    await state.clear()  

    await message.answer(
        i18n.gettext("Спасибо за предоставленную информацию!\n"
                    "Ожидайте, пока администратор проверит вашу анкету ⌛️", locale=user.lang)
    )