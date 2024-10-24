from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQuery, Message, \
    InlineKeyboardMarkup
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import AdminCallback, RenewSubscription
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin"]))
router.callback_query.filter(RoleFilter(roles=["admin"]))
router.inline_query.filter(RoleFilter(roles=["admin"]))


# @router.callback_query(AdminCallback.filter(F.action == "renew_subscription"))
# async def renew_subscription_for_user(callback: CallbackQuery,
#                        callback_data: AdminCallback,
#                        orm: ORM,
#                        i18n: I18n):
#     await callback.message.edit_text(i18n.gettext("Введите id пользователя"))

@router.inline_query(F.query.startswith('user '))
async def find_user(inq: InlineQuery, orm: ORM):
    query = inq.query[5:]
    results = []
    users = await orm.user_repo.find_all()
    users = filter(lambda x: x.username.find(query) != -1
                             or str(x.user_id).find(query) != -1
                             or x.fullname.find(query) != -1, users)
    if query:
        for user in users:
            results.append(
                InlineQueryResultArticle(
                    id=str(user.id),
                    title=f'{user.fullname} - @{user.username}',
                    input_message_content=InputTextMessageContent(
                        message_text="/find Имя пользователя @{}\n"
                           "Имя: {}\n"
                           "Место работы: {}\n"
                           "Страна: {}\n"
                           "Город: {}\n"
                           "Номер: {}".format(user.username, user.fullname, user.affiliate, user.country, user.city, user.phone_number),
                        parse_mode=ParseMode.HTML
                    ),
                    description=f"{user.city} {user.affiliate}"
                )
            )
    await inq.answer(results=results, cache_time=10)

@router.message(Command("find"))
async def find_command(message: Message, orm: ORM, i18n: I18n):
    username = message.text.split("\n")[0].split()[-1].replace('@', '')
    user = await orm.user_repo.find_user_by_username(username)
    await message.answer(i18n.gettext("Выберите длительность подписки", locale=user.lang),
                         reply_markup=Keyboards.months(user, i18n))

@router.callback_query(RenewSubscription.filter())
async def renew_user_subscription(callback: CallbackQuery, callback_data: RenewSubscription, orm: ORM, i18n: I18n):
    sub = await orm.subscription_repo.set_subscription(callback_data.user_id, period=callback_data.months*30)
    user = await orm.user_repo.find_user_by_user_id(callback_data.user_id)
    await callback.message.edit_text(i18n.gettext("Вы успешно продлили подписку пользователя @{}", locale=user.lang).format(user.username),
                                     reply_markup=Keyboards.back_to_home(i18n, user))
    await callback.bot.send_message(callback_data.user_id, i18n.gettext("Вам продлили подписку \nСрок ее окончания: \n{}", locale=user.lang).format(sub.date_end),
                                    reply_markup=Keyboards.back_to_home(i18n, user))

