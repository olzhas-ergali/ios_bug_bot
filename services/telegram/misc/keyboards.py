from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import I18n
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.database import ORM
from services.telegram.misc.callbacks import  CitySelect, \
    AdminCallback, CountrySelect,  RenewSubscription, ChooseModelCallback, \
    FullButtonCallback,LangCallback,LangChangeCallBack, BroadcastLangCallback, BroadcastCallback

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
    
    from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, InlineKeyboardButton
from aiogram import types

class Keyboards:

    @staticmethod
    def home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        user_keyboard = [
            [KeyboardButton(text=i18n.gettext("Инструкция", locale=user.lang) + " 📕")],
            [KeyboardButton(text=i18n.gettext("Сменить язык", locale=user.lang) + " 🏳️")],
            [KeyboardButton(text=i18n.gettext("Наш канал", locale=user.lang) + " 👥", url="https://t.me/Yourrepairassistant")],
            [KeyboardButton(text=i18n.gettext("Справочник дисков", locale=user.lang) + " 📚")],
        ]

        if user.role == 'admin':
            user_keyboard.append([KeyboardButton(text=i18n.gettext("Админ панель", locale=user.lang) + " ⚙️")])

        reply_markup = ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=user_keyboard
        )

        return reply_markup

    @staticmethod
    def admin_panel(i18n: I18n, user) -> InlineKeyboardMarkup:
        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Продлить подписку", locale=user.lang) + " ⏳",
                    switch_inline_query_current_chat="user "
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассылка", locale=user.lang) + " 📣",
                    callback_data="broadcast"
                )
            ]
        ])

        return admin_keyboard

    @staticmethod
    def back_to_home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(resize_keyboard=True,
                                   one_time_keyboard=True,
                                   keyboard=[[
                                       KeyboardButton(
                                           text=i18n.gettext("Назад ◀️", locale=user.lang))
                                   ]])

    @staticmethod
    def get_consultation(i18n: I18n, user) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=[[
                KeyboardButton(
                    text=i18n.gettext("Получить консультацию", locale=user.lang) + " 📞"
                    ,callback_data="get_consultation"
                )
            ]]
        )
    
    @staticmethod
    def lang(is_menu=False):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸",
            callback_data=LangCallback(lang="en") if not is_menu else LangChangeCallBack(action='changed', lang="en"))
        builder.button(
            text="Русский 🇷🇺",
            callback_data=LangCallback(lang="ru") if not is_menu else LangChangeCallBack(action='changed', lang="ru"))
        return builder.as_markup()

    
    @staticmethod
    def lang2(is_menu=False):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸",
            callback_data=BroadcastLangCallback(lang="en").pack() if not is_menu else BroadcastLangCallback(action='changed', lang="en"))
        builder.button(
            text="Русский 🇷🇺",
            callback_data=BroadcastLangCallback(lang="ru").pack() if not is_menu else BroadcastLangCallback(action='changed', lang="ru"))
        return builder.as_markup()


    @staticmethod
    def links(links: list, i18n: I18n, user):
        builder = InlineKeyboardBuilder()
        for i, link in enumerate(links, start=1):
            builder.button(text=i18n.gettext("Материал {} 📎", locale=user.lang).format(i), url=link)
        builder.adjust(1, repeat=True)
        return builder

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
    def broadcast(user_id, i18n: I18n, user):
        builder = InlineKeyboardBuilder()

        builder.button(
            text=i18n.gettext("Принять ✅", locale=user.lang),
            callback_data=BroadcastCallback(action="accept", user_id=user_id))
        builder.button(
            text=i18n.gettext("Отклонить ❌", locale=user.lang),
            callback_data=BroadcastCallback(action="cancel", user_id=user_id))
        return builder.as_markup()
    
    @staticmethod
    def months(user, i18n: I18n):
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("1 месяц", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=1).pack()
        )
        builder.button(
            text=i18n.gettext("3 месяца", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=3).pack()
        )
        builder.button(
            text=i18n.gettext("6 месяцев", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=6).pack()
        )
        builder.button(
            text=i18n.gettext("1 год", locale=user.lang),
            callback_data=RenewSubscription(user_id=user.user_id, months=12).pack()
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

    @staticmethod
    def add_full_btn(builder, error_code, model):
        if error_code.find(':') != -1:
            error_code = error_code.replace(':', 'doubledott')
        builder.row(
            InlineKeyboardButton(
                text='Полная версия инструкции',
                callback_data=FullButtonCallback(action='show', error_code=error_code, model=model).pack()
            )
        )
        return builder
