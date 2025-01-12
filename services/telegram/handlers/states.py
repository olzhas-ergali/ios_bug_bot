from aiogram.fsm.state import StatesGroup, State


class HomeDatetime(StatesGroup):
    wait_date = State()
    wait_time = State()

class BroadcastStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_message = State()
    confirming_message = State()
    
class DeleteUserStates(StatesGroup):
    waiting_for_user_id = State()
    
class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_language = State()
    waiting_for_fullname = State()
    waiting_for_affiliate = State()
    waiting_for_country = State()
    waiting_for_city = State()