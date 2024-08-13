from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

from services.telegram.misc.callbacks import HomeCallback


class Keyboards:
    """
    TODO Заменить подклассами
    """

    @staticmethod
    def send_phone():
        return ReplyKeyboardMarkup(resize_keyboard=True,
                                   one_time_keyboard=True,
                                   keyboard=[[
                                       KeyboardButton(text='Поделиться номером телефона', request_contact=True)
                                   ]])

    @staticmethod
    def home() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Инструкция", callback_data=HomeCallback(action="instruction").pack()),
            ]
        ])

    @staticmethod
    def back_to_home() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Назад ◀️", callback_data=HomeCallback(action="back_to_home").pack()),
            ]
        ])
