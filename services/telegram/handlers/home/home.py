from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from database.models import User
from services.telegram.misc.callbacks import HomeCallback
from services.telegram.misc.keyboards import Keyboards

router = Router()


@router.message(F.text == "Главная")
@router.message(Command("start"))
async def home(message: Message, user: User):
    # TODO Постепенно заменять тексты на Texts
    await message.answer(
        f"Приветствую @{user.username}🙂🤝🏼 "
        f"\nЯ помогу тебе сделать анализ сбоев"
        f"\nОтправь мне файл или изображение и его проанализирую 🔬",
        reply_markup=Keyboards.home()
    )


@router.callback_query(HomeCallback.filter(F.action == "instruction"))
async def instruction(callback: CallbackQuery):
    # TODO Постепенно заменять тексты на Texts
    await callback.message.edit_text(
        f"Инструкция" * 20,
        reply_markup=Keyboards.back_to_home()
    )


@router.callback_query(HomeCallback.filter(F.action == "back_to_home"))
async def instruction(callback: CallbackQuery, user: User):
    # TODO Постепенно заменять тексты на Texts
    await callback.message.edit_text(
        f"Приветствую @{user.username}🙂🤝🏼 "
        f"\nЯ помогу тебе сделать анализ сбоев"
        f"\nОтправь мне файл или изображение и его проанализирую 🔬",
        reply_markup=Keyboards.home()
    )


@router.message(F.text == "alfinkly")
async def info(message: Message):
    await message.answer(f"Мои создатель жив?")


@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()
