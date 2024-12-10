from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQuery, Message, \
    InlineKeyboardMarkup
from aiogram.utils.i18n import I18n
from services.telegram.handlers.states import BroadcastStates
from aiogram.fsm.context import FSMContext
from services.telegram.misc.callbacks import BroadcastLangCallback,BroadcastCallback
from database.models import User

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


@router.callback_query(F.data == "broadcast")
async def handle_broadcast(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции", locale=user.lang))
        return

    await callback.message.answer(
        i18n.gettext("Выберите язык рассылки:", locale=user.lang),
        reply_markup=Keyboards.lang2()  
    )
    await state.set_state(BroadcastStates.waiting_for_language)


@router.callback_query(BroadcastLangCallback.filter(), BroadcastStates.waiting_for_language)
async def select_broadcast_language(callback: CallbackQuery,
                                   callback_data: BroadcastLangCallback,
                                   state: FSMContext,
                                   i18n: I18n,
                                   user: User):
    selected_lang = callback_data.lang
    await state.update_data(broadcast_language=selected_lang)

    prompt = {
        'en': i18n.gettext("Enter the message in English:", locale=user.lang),
        'ru': i18n.gettext("Введите сообщение на русском языке:", locale=user.lang),
    }

    await callback.message.answer(prompt.get(selected_lang, "Enter your message:"))
    await state.set_state(BroadcastStates.waiting_for_message)


@router.message(BroadcastStates.waiting_for_message)
async def confirm_broadcast_message(message: Message,
                                   state: FSMContext,
                                   user: User,
                                   i18n: I18n):
    if len(message.text) > 4096:
        await message.answer(
            i18n.gettext("Сообщение слишком длинное. Максимальная длина - 4096 символов.", locale=user.lang)
        )
        return

    await state.update_data(broadcast_message=message.text)

    builder = Keyboards.broadcast(user.user_id, i18n, user)

    await message.answer(
        i18n.gettext("Предварительный просмотр сообщения:\n\n{}\n\nПодтвердить рассылку?", locale=user.lang).format(message.text),
        reply_markup=builder 
    )
    await state.set_state(BroadcastStates.waiting_for_confirmation)



@router.callback_query(BroadcastCallback.filter(F.action == "accept"))
async def perform_broadcast(callback: CallbackQuery,
                            callback_data: BroadcastCallback,
                            state: FSMContext,
                            orm: ORM,
                            i18n: I18n):
    data = await state.get_data()
    broadcast_language = data.get('broadcast_language')
    broadcast_message = data.get('broadcast_message')

    if not broadcast_language or not broadcast_message:
        await callback.message.answer(i18n.gettext("Ошибка: Не удалось получить данные для рассылки", locale=callback.from_user.lang))
        await state.clear()  
        return

    users = await orm.user_repo.get_users_by_language(broadcast_language)

    successful_sends = 0
    failed_sends = 0

    for user in users:
        try:
            await callback.bot.send_message(chat_id=user.user_id, text=broadcast_message)
            successful_sends += 1
        except Exception as e:
            failed_sends += 1
            print(f"Failed to send message to {user.user_id}: {e}")

    await callback.message.answer(
        f"Рассылка завершена:\n"
        f"Успешно отправлено: {successful_sends}\n"
        f"Не удалось отправить: {failed_sends}"
    )

    await state.clear() 


@router.callback_query(BroadcastCallback.filter(F.action == "cancel"))
async def cancel_broadcast(callback: CallbackQuery,
                           callback_data: BroadcastCallback,
                           state: FSMContext,
                           i18n: I18n,
                           user: User):
    await callback.message.answer(
        i18n.gettext("Рассылка отменена", locale=user.lang)
    )
    await state.clear() 
