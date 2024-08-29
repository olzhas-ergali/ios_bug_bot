from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import gettext as _

from database.database import ORM
from services.analyzer.xlsx import get_cities
from services.telegram.filters.registration import RegistrationFilter
from services.telegram.misc.callbacks import CitySelect
from services.telegram.misc.keyboards import Keyboards

router = Router()


@router.message(F.text, Command("start"))
async def ask_contact(message: Message,
                      state: FSMContext,
                      orm: ORM):
    user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    await state.update_data(columns=user.get_null_columns())
    msg = await message.answer(text=_("Для регистрации нажмите на кнопку ⬇️"),
                               reply_markup=Keyboards.send_phone())
    await state.update_data(msg_id=msg.message_id)


@router.message(F.contact, RegistrationFilter(filter_column="fullname"))
async def ask_fullname(message: Message, state: FSMContext, orm: ORM):
    await orm.user_repo.save_user(message)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id,
                                     message_id=data["msg_id"])
    msg = await message.answer(text=_("Как вас зовут?"))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, RegistrationFilter(filter_column="affiliate"))
async def ask_fullname(message: Message, state: FSMContext, orm: ORM):
    await orm.user_repo.upsert_user(message.from_user.id,
                                    fullname=message.text)
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(chat_id=message.from_user.id,
                                     message_id=data["msg_id"])
    msg = await message.answer(text=_("Где вы работаете?"))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, RegistrationFilter(filter_column="city"))
async def ask_city(message: Message, orm: ORM, state: FSMContext):
    await orm.user_repo.upsert_user(message.from_user.id,
                                    affiliate=message.text)
    cities = get_cities()
    data = await state.get_data()
    await message.delete()
    await message.bot.delete_message(
        chat_id=message.from_user.id,
        message_id=data["msg_id"],
    )
    msg = await message.answer(text=_("Выберите город"),
                               reply_markup=Keyboards.cities(cities))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(CitySelect.filter())
async def select_city(callback: CallbackQuery,
                      callback_data: CitySelect,
                      state: FSMContext,
                      orm: ORM):
    await orm.user_repo.upsert_user(callback.from_user.id,
                                    city=callback_data.name,
                                    role="no_access")
    user = await orm.user_repo.find_user_by_user_id(callback.from_user.id)
    data = await state.get_data()
    text_admins = _(f"Имя: {user.fullname}\n"
                    f"Место работы: {user.affiliate}\n"
                    f"Город: {user.city}\n"
                    f"Номер: {user.phone_number}")
    await callback.bot.send_message(
        orm.settings.channel_id,
        text=text_admins,
        reply_markup=Keyboards.guest(callback.from_user.id))
    await callback.bot.delete_message(
        chat_id=callback.from_user.id,
        message_id=data["msg_id"],
    )
    await callback.message.answer(
        _("Спасибо за предоставленную информацию!"
          f"\nОжидайте пока админ проверит вашу анкету ⌛️"))
