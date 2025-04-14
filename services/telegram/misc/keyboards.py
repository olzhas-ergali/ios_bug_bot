from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import I18n
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.database import ORM
from services.telegram.misc.callbacks import (
    AdminCallback, RenewSubscription, ChooseModelCallback,
    FullButtonCallback, LangCallback, LangChangeCallBack, 
    BroadcastLangCallback, BroadcastCallback, UserListPagination
)

class Keyboards:
    @staticmethod
    def balance_keyboard(i18n: I18n, user) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=i18n.gettext("Пополнить баланс", locale=user.lang) + " 💳",
                callback_data="topup_balance_user"
            )]
        ])

    @staticmethod
    def send_phone(i18n: I18n, user):
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=[[
                KeyboardButton(
                    text=i18n.gettext('Поделиться номером телефона', locale=user.lang),
                    request_contact=True
                )
            ]]
        )

    @staticmethod
    def home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        user_keyboard = [
            [KeyboardButton(text=i18n.gettext("Инструкция", locale=user.lang) + " 📕")],
            [KeyboardButton(text=i18n.gettext("Мой баланс", locale=user.lang) + " 💰")],
            [KeyboardButton(text=i18n.gettext("Пополнить баланс", locale=user.lang) + " 💳")],
            [KeyboardButton(text=i18n.gettext("Сменить язык", locale=user.lang) + " 🏳️")],
            [KeyboardButton(text=i18n.gettext("Наш канал", locale=user.lang) + " 👥", url="https://t.me/Yourrepairassistant")],
            [KeyboardButton(text=i18n.gettext("Справочник дисков", locale=user.lang) + " 📚")]
            
        ]

        if user.role == 'admin':
            user_keyboard.append([KeyboardButton(text=i18n.gettext("Админ панель", locale=user.lang) + " ⚙️")])

        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=user_keyboard
        )

    @staticmethod
    def admin_panel(i18n: I18n, user) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            # [
            #     InlineKeyboardButton(
            #         text=i18n.gettext("Продлить подписку", locale=user.lang) + " ⏳",
            #         switch_inline_query_current_chat="user "
            #     )
            # ],
            [   
                InlineKeyboardButton(
                    text=i18n.gettext("Изменить сумму списания", locale=user.lang) + " 💵", 
                    callback_data="set_fee"
                )
            ],
            # [   
            #     InlineKeyboardButton(
            #         text=i18n.gettext("Пополнить баланс пользователя", locale=user.lang) + " 💰", 
            #         callback_data="topup"
            #     )
            # ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассылка", locale=user.lang) + " 📣",
                    callback_data="broadcast"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Список пользователей", locale=user.lang) + " 👥",
                    callback_data="users_list"
                )
            ]
        ])
    
    def admin_balance_menu():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Пополнить баланс", callback_data="topup")],
            [InlineKeyboardButton(text="🔎 Проверить баланс", callback_data="admin_check_balance")],
            [InlineKeyboardButton(text="🧾 История операций", callback_data="admin_history")],
            [InlineKeyboardButton(text="🧼 Обнулить баланс", callback_data="admin_reset_balance")],
        ])
    
    @staticmethod
    def get_users_list_keyboard(total_pages: int, current_page: int, i18n: I18n, user) -> InlineKeyboardMarkup:
        buttons = []
        nav_buttons = []

        if current_page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=UserListPagination(page=current_page - 1).pack()
                )
            )

        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{current_page + 1}/{total_pages}",
                callback_data="nothing"
            )
        )

        if current_page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=UserListPagination(page=current_page + 1).pack()
                )
            )

        buttons.append(nav_buttons)
        buttons.append([
            InlineKeyboardButton(
                text=i18n.gettext("Удалить пользователя по ID", locale=user.lang),
                callback_data="delete_user_by_id"
            ),
            InlineKeyboardButton(
                text=i18n.gettext("Назад в админ панель", locale=user.lang) + " ↩️",
                callback_data="back_to_admin"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def back_to_home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=[[
                KeyboardButton(text=i18n.gettext("Назад ◀️", locale=user.lang))
            ]]
        )

    @staticmethod
    def balance_request_button(user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💰 Пополнить баланс",
                callback_data=f"request_topup:{user_id}"
            )]
        ])

    @staticmethod
    def get_consultation(i18n: I18n, user) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.gettext("Получить консультацию", locale=user.lang) + " 📧",
                        callback_data="get_consultation"
                    )
                ]
            ]
        )

    @staticmethod
    def lang(is_menu=False):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸",
            callback_data=LangCallback(lang="en") if not is_menu else LangChangeCallBack(action='changed', lang="en")
        )
        builder.button(
            text="Русский 🇷🇺",
            callback_data=LangCallback(lang="ru") if not is_menu else LangChangeCallBack(action='changed', lang="ru")
        )
        return builder.as_markup()

    @staticmethod
    def links(links: list, i18n: I18n, user):
        builder = InlineKeyboardBuilder()
        for i, link in enumerate(links, start=1):
            builder.button(
                text=i18n.gettext("Материал {number} 📎", locale=user.lang).format(number=i), 
                url=link
            )
        builder.adjust(1, repeat=True)
        return builder.as_markup()

    @staticmethod
    def empty() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[])

    @staticmethod
    def guest(user_id: int, i18n: I18n, user) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Принять ✅", locale=user.lang),
            callback_data=AdminCallback(action="accept", user_id=user_id).pack()
        )
        builder.button(
            text=i18n.gettext("Отклонить ❌", locale=user.lang),
            callback_data=AdminCallback(action="cancel", user_id=user_id).pack()
        )
        return builder.as_markup()

    @staticmethod
    def broadcast_confirmation(user_id: int, i18n: I18n, user) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Принять ✅", locale=user.lang),
            callback_data=BroadcastCallback(action="accept", user_id=user_id).pack()
        )
        builder.button(
            text=i18n.gettext("Отклонить ❌", locale=user.lang),
            callback_data=BroadcastCallback(action="cancel", user_id=user_id).pack()
        )
        return builder.as_markup()

    @staticmethod
    def months(user, i18n: I18n) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        periods = [
            (1, i18n.gettext("1 месяц", locale=user.lang)),
            (3, i18n.gettext("3 месяца", locale=user.lang)),
            (6, i18n.gettext("6 месяцев", locale=user.lang)),
            (12, i18n.gettext("1 год", locale=user.lang))
        ]
        
        for months, text in periods:
            builder.button(
                text=text,
                callback_data=RenewSubscription(user_id=user.user_id, months=months).pack())
        
        builder.adjust(2, repeat=True)
        return builder.as_markup()

    @staticmethod
    def models(models: list) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for model in models:
            builder.button(
                text=model,
                callback_data=ChooseModelCallback(model=model).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def add_full_btn(builder: InlineKeyboardBuilder, error_code: str, model: str) -> InlineKeyboardBuilder:
        safe_error_code = error_code.replace(':', 'doubledott')
        builder.row(
            InlineKeyboardButton(
                text='Полная версия инструкции',
                callback_data=FullButtonCallback(
                    action='show', 
                    error_code=safe_error_code, 
                    model=model
                ).pack()
            )
        )
        return builder
    
    def get_topup_keyboard(user_id: int):
        builder = InlineKeyboardBuilder()
        builder.button(text="100₸", callback_data=f"topup:{user_id}:100")
        builder.button(text="500₸", callback_data=f"topup:{user_id}:500") 
        builder.button(text="1000₸", callback_data=f"topup:{user_id}:1000")
        builder.button(text="Другая сумма", callback_data=f"topup_custom:{user_id}")
        builder.adjust(3, 1)
        return builder.as_markup()