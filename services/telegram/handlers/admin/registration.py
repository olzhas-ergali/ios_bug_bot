from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.database import ORM
from services.telegram.misc.callbacks import AdminCallback
from services.telegram.misc.keyboards import Keyboards
from aiogram.utils.i18n import gettext as _

router = Router()


@router.callback_query(AdminCallback.filter(F.action == "accept"))
async def accept_guest(callback: CallbackQuery,
                       callback_data: AdminCallback,
                       orm: ORM):
    await orm.user_repo.upsert_user(callback_data.user_id, role="user")
    text = callback.message.text + _("\nПользователь принят ✅")
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
    await callback.bot.send_message(
        chat_id=callback_data.user_id,
        text=_("Вы приняты, теперь вам доступен весь функционал 😄"),
        reply_markup=Keyboards.home())


@router.callback_query(AdminCallback.filter(F.action == "cancel"))
async def accept_guest(callback: CallbackQuery,
                       callback_data: AdminCallback,
                       orm: ORM):
    await orm.user_repo.upsert_user(callback_data.user_id, role="no_access")
    text = callback.message.text + _("\nПользователь отклонен ❌")
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
