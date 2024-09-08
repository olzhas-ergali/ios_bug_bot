from aiogram.filters.callback_data import CallbackData


class HomeCallback(CallbackData, prefix="home"):
    action: str


class ProductSelect(CallbackData, prefix="product_select"):
    name: str


class CitySelect(CallbackData, prefix="cities"):
    name: str


class CountrySelect(CallbackData, prefix="countries"):
    name: str


class AdminCallback(CallbackData, prefix="guest"):
    action: str
    user_id: int


class LangCallback(CallbackData, prefix="lang"):
    lang: str
