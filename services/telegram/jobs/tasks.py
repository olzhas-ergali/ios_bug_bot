from database.database import ORM
from aiogram import Bot
from aiogram.utils.i18n import I18n


async def check_subscribe_client(orm: ORM, bot: Bot, i18n: I18n):
    (expired_subscriptions, almost_expired_subscriptions) = await orm.subscription_repo.get_expired()

    for subscription in expired_subscriptions:
        user_id = subscription.user_id
        await orm.subscription_repo.delete(user_id)
        user = await orm.user_repo.find_user_by_user_id(user_id)

        text = i18n.gettext('Ваша подписка истекла \nОбратитесь к админу чтобы вам продлили подписку', locale=user.lang)

        await bot.send_message(user_id, text)

    for subscription in almost_expired_subscriptions:
        user_id = subscription.user_id
        await orm.subscription_repo.warn(user_id)
        user = await orm.user_repo.find_user_by_user_id(user_id)

        text = i18n.gettext('Ваша подписка истекает через сутки \nОбратитесь к админу чтобы вам продлили подписку', locale=user.lang)

        await bot.send_message(user_id, text)