from aiogram.fsm.state import StatesGroup, State


class HomeDatetime(StatesGroup):
    wait_date = State()
    wait_time = State()
