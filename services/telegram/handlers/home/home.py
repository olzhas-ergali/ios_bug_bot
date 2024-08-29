from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import gettext as _

from database.models import User
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import HomeCallback
from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(F.text == "Главная")
@router.message(Command("start"))
async def home(message: Message, user: User):
    await message.answer(
        _(f"Приветствую @{user.username}🙂🤝🏼 "
          f"\nЯ помогу тебе с анализом сбоев"
          f"\nОтправь мне файл или изображение и его проанализирую 🔬"),
        reply_markup=Keyboards.home()
    )


@router.callback_query(HomeCallback.filter(F.action == "instruction"))
async def instruction(callback: CallbackQuery):
    await callback.message.edit_text(
        "Инструкция" * 20,
        reply_markup=Keyboards.back_to_home()
    )


@router.callback_query(HomeCallback.filter(F.action == "back_to_home"))
async def instruction(callback: CallbackQuery, user: User):
    await callback.message.edit_text(
        f"Приветствую @{user.username}🙂🤝🏼 "
        f"\nЯ помогу тебе сделать анализ сбоев"
        f"\nОтправь мне файл или изображение и его проанализирую 🔬",
        reply_markup=Keyboards.home()
    )


@router.message(F.text == "alfinkly")
async def info(message: Message):
    await message.answer("Мои создатель жив?")


@router.callback_query(F.data == "nothing")
async def nothing(callback: CallbackQuery):
    await callback.answer()
