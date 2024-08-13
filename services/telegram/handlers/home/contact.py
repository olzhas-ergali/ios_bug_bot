from aiogram import F, Router
from aiogram.types import Message, TelegramObject

from database.database import ORM
from services.telegram.misc.keyboards import Keyboards

router = Router()


async def ask_contact(event: TelegramObject):
    await event.bot.send_message(chat_id=event.from_user.id,
                                 text="Для регистрации нажмите на кнопку ⬇️",
                                 reply_markup=Keyboards.send_phone())


@router.message(F.contact)
async def contact_received(message: Message, orm: ORM):
    await orm.user_repo.save_user(message)
    await message.answer("Спасибо за предоставленную информацию!"
                         f"\nОжидайте пока админ проверит вашу анкету ⌛️")
