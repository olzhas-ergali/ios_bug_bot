from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.database import ORM
from services.telegram.misc.callbacks import AdminCallback
from services.telegram.misc.keyboards import Keyboards
from aiogram.utils.i18n import I18n

router = Router()


@router.callback_query(AdminCallback.filter(F.action == "accept"))
async def accept_guest(callback: CallbackQuery,
                       callback_data: AdminCallback,
                       orm: ORM,
                       i18n: I18n):
    user = await orm.user_repo.upsert_user(callback_data.user_id, role="user")
    text = callback.message.text + i18n.gettext("\nПользователь принят ✅", locale=user.lang)
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
    await callback.bot.send_message(
        chat_id=callback_data.user_id,
        text=i18n.gettext("Вы приняты, теперь вам доступен весь функционал 😄", locale=user.lang),
        reply_markup=Keyboards.home(i18n, user))
    await orm.subscription_repo.set_subscription(callback_data.user_id, period=3)


@router.callback_query(AdminCallback.filter(F.action == "cancel"))
async def accept_guest(callback: CallbackQuery,
                       callback_data: AdminCallback,
                       orm: ORM,
                       i18n: I18n,
                       user):
    await orm.user_repo.upsert_user(callback_data.user_id, role="no_access")
    text = callback.message.text + i18n.gettext("\nПользователь отклонен ❌", locale=user.lang)
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
