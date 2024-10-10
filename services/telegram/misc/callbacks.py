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


class LangChangeCallBack(CallbackData, prefix="change_lang"):
    action: str
    lang: str

class RenewSubscription(CallbackData, prefix="renew"):
    user_id: int
    months: int

class ChooseModelCallback(CallbackData, prefix="choose_model"):
    model: str

class FullButtonCallback(CallbackData, prefix="full_btn"):
    action: str