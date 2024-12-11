from aiogram.fsm.state import StatesGroup, State


class HomeDatetime(StatesGroup):
    wait_date = State()
    wait_time = State()
    
class BroadcastStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_message = State()
    waiting_for_confirmation = State()
