from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.telegram.filters.registration import RegistrationFilter
from services.telegram.misc.callbacks import  LangCallback
from services.telegram.misc.keyboards import Keyboards

router = Router()

@router.message(F.text, Command("start"))
async def ask_contact(message: Message,
                      state: FSMContext,
                      orm: ORM,
                      i18n: I18n):
    user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    await state.update_data(columns=user.get_null_columns())
    msg = await message.answer(
        text = 'Для регистрации поделитесь, пожалуйста, номером телефона, нажав на кнопку "Поделиться номером телефона" ниже 👇\n\n'
        'For registration, please share your phone number by clicking the "Share Phone Number" button below 👇\n\n'
        'Название кнопки: "Поделиться номером телефона" / Button name: "Share Phone Number"',
        reply_markup=Keyboards.send_phone(i18n, user)
    )
    await state.update_data(msg_id=msg.message_id)

@router.message(F.contact, RegistrationFilter(filter_column="lang"))
async def ask_fullname(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.save_user(message)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Выберите язык", user.lang), reply_markup=Keyboards.lang())
    await state.update_data(msg_id=msg.message_id)

@router.callback_query(LangCallback.filter(), RegistrationFilter(filter_column="fullname"))
async def ask_fullname(callback: CallbackQuery, callback_data: LangCallback,
                       state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.upsert_user(callback.from_user.id, lang=callback_data.lang)
    await callback.message.delete()
    msg = await callback.message.answer(text=i18n.gettext("Как вас зовут?", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)

@router.message(F.text, RegistrationFilter(filter_column="affiliate"))
async def ask_affiliate(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, fullname=message.text)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Где вы работаете?", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)

@router.message(F.text, RegistrationFilter(filter_column="country")) 
async def ask_country(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, affiliate=message.text)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Введите страну", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)

@router.message(F.text, RegistrationFilter(filter_column="city")) 
async def ask_city(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    user = await orm.user_repo.upsert_user(message.from_user.id, country=message.text)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id, message_id=data["msg_id"])
    msg = await message.answer(text=i18n.gettext("Введите город", locale=user.lang))
    await state.update_data(msg_id=msg.message_id)

@router.message(F.text)
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
    except:
        pass
    
    await message.answer(
        i18n.gettext("Спасибо за предоставленную информацию!"
                     f"\nОжидайте пока админ проверит вашу анкету ⌛️", locale=user.lang)
    )
