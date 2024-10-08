from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, \
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.i18n import I18n
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.database import ORM
from services.telegram.misc.callbacks import HomeCallback, CitySelect, \
    AdminCallback, LangCallback, CountrySelect, LangChangeCallBack, RenewSubscription, ChooseModelCallback


class Keyboards:
    @staticmethod
    def send_phone(i18n: I18n, user):
        return ReplyKeyboardMarkup(resize_keyboard=True,
                                   one_time_keyboard=True,
                                   keyboard=[[
                                       KeyboardButton(
                                           text=i18n.gettext('Поделиться номером телефона', locale=user.lang),
                                           request_contact=True)
                                   ]])

    @staticmethod
    def home(i18n: I18n, user) -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n.gettext("Инструкция", locale=user.lang)+" 📕",
                                     callback_data=HomeCallback(
                                         action="instruction").pack())],
            [
                InlineKeyboardButton(text=i18n.gettext('Сменить язык', locale=user.lang)+" 🏳️",
                                     callback_data=LangChangeCallBack(
                                         action="change", lang="").pack())
            ],
            [
                InlineKeyboardButton(text=i18n.gettext('Наш канал', locale=user.lang)+" 👥",
                                     url="https://t.me/Yourrepairassistant")
            ]
        ])
        if user.role == 'admin':
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=i18n.gettext("Продлить подписку", locale=user.lang)+" ⏳", switch_inline_query_current_chat="")])

        return keyboard

    @staticmethod
    def back_to_home(i18n: I18n, user) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text=i18n.gettext("Назад ◀️", locale=user.lang),
                       callback_data=HomeCallback(action="back_to_home"))
        return builder.as_markup()

    @staticmethod
    def links(links: list, i18n: I18n, user):
        builder = InlineKeyboardBuilder()
        for i, link in enumerate(links, start=1):
            builder.button(text=i18n.gettext("Материал {} 📎", locale=user.lang).format(i), url=link)
        builder.adjust(1, repeat=True)
        return builder.as_markup()

    @staticmethod
    def countries(countries: dict):
        builder = InlineKeyboardBuilder()
        for i, country in enumerate(countries):
            builder.button(text=f"{country}",
                           callback_data=CountrySelect(name=country))
        builder.adjust(1, repeat=True)
        return builder.as_markup()

    @staticmethod
    def cities(countries: list):
        builder = InlineKeyboardBuilder()
        for i, country in enumerate(countries):
            builder.button(text=f"{country}",
                           callback_data=CitySelect(name=country))
        # builder.button(text=f"Вперед", callback_data=CitySelect(name=country))
        builder.adjust(1, repeat=True)
        return builder.as_markup()

    @staticmethod
    def empty():
        return InlineKeyboardMarkup(inline_keyboard=[])

    @staticmethod
    def guest(user_id, i18n: I18n, user):
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Принять ✅", locale=user.lang),
            callback_data=AdminCallback(action="accept", user_id=user_id))
        builder.button(
            text=i18n.gettext("Отклонить ❌", locale=user.lang),
            callback_data=AdminCallback(action="cancel", user_id=user_id))
        return builder.as_markup()

    @staticmethod
    def lang(is_menu=False):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Қазақ",
            callback_data=LangCallback(lang="kk") if not is_menu else LangChangeCallBack(action='changed', lang="kk"))
        builder.button(
            text="Русский",
            callback_data=LangCallback(lang="ru") if not is_menu else LangChangeCallBack(action='changed', lang="ru"))
        return builder.as_markup()

    @staticmethod
    def months(user, i18n: I18n):
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("1 месяц", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=1)
        )
        builder.button(
            text=i18n.gettext("3 месяца", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=3)
        )
        builder.button(
            text=i18n.gettext("6 месяцев", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=6)
        )
        builder.button(
            text=i18n.gettext("1 год", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=12)
        )
        return builder.as_markup()

    @staticmethod
    def models(models):
        builder = InlineKeyboardBuilder()
        for model in models:
            builder.row(
                InlineKeyboardButton(
                    text=model,
                    callback_data=ChooseModelCallback(model=model).pack()
                )
            )
        return builder.as_markup()
