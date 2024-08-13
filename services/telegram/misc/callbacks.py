from aiogram.filters.callback_data import CallbackData


class HomeCallback(CallbackData, prefix="home"):
    action: str
