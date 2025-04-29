from aiogram import F, Router
from aiogram.types import CallbackQuery
from database.database import ORM
from services.telegram.misc.callbacks import AdminCallback
from services.telegram.misc.keyboards import Keyboards
from aiogram.utils.i18n import I18n
import os # Import os to get environment variable
from decimal import Decimal # Import Decimal for calculations
import logging # Import logging

router = Router()

# --- Constants for Token Bonuses ---
WELCOME_BONUS_TOKENS = 5
MONTHLY_BONUS_TOKENS = 1 

@router.callback_query(AdminCallback.filter(F.action == "accept"))
async def accept_guest(callback: CallbackQuery,
                       callback_data: AdminCallback,
                       orm: ORM,
                       i18n: I18n):
    # Set role to user and get user object
    # TODO: i18n: Consider language setting before user completes profile if lang is needed here
    user = await orm.user_repo.upsert_user(callback_data.user_id, role="user")
    
    # Add WELCOME_BONUS_TOKENS to user's token_balance
    bonus_message_part = "" # Initialize
    try:
        logging.info(f"Начисление приветственного бонуса {WELCOME_BONUS_TOKENS} токенов пользователю {callback_data.user_id}")
        await orm.user_repo.add_tokens(callback_data.user_id, WELCOME_BONUS_TOKENS)
        token_balance_after_bonus = await orm.user_repo.get_token_balance(callback_data.user_id)
        logging.info(f"Бонусные токены успешно начислены. Новый token_balance пользователя {callback_data.user_id}: {token_balance_after_bonus}")
        
        # Welcome bonus message using tokens
        bonus_message_part = i18n.gettext(
            "\n\n🎁 Вам начислен приветственный бонус: {count} токенов.", 
            locale=user.lang # Use user's language
        ).format(count=WELCOME_BONUS_TOKENS)
        
        # Add monthly bonus info using tokens
        bonus_message_part += i18n.gettext(
            "\n🗓️ Также каждый месяц 1-го числа в 9:00 вам будет начисляться бонус в размере {monthly_count} токена.",
            locale=user.lang # Use user's language
        ).format(monthly_count=MONTHLY_BONUS_TOKENS)
        
        # ИЗМЕНЕНО: Добавляем информацию о подписке на устройство
        bonus_message_part += i18n.gettext(
            "\n💡 **Важно:** Первый анализ лога с *каждого нового устройства* стоит 1 токен (если решение найдено). После этого для *данного устройства* активируется 30-дневный период, в течение которого следующие 9 анализов будут **бесплатными**.",
            locale=user.lang # Use user's language
        )
        
    except Exception as e:
        logging.error(f"Ошибка начисления бонусных токенов пользователю {callback_data.user_id}: {e}")
        bonus_message_part = "\n\n⚠️ Не удалось начислить приветственный бонус."
        
    # Edit admin message
    # TODO: i18n: Localize admin message confirmation
    text = callback.message.text + i18n.gettext("\nПользователь принят ✅", locale="ru") # Assuming admin panel is Russian for now
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
    
    # Send acceptance message + bonus info to user
    # TODO: i18n: Make sure user.lang is correctly set before this message
    acceptance_text = i18n.gettext("Вы приняты, теперь вам доступен весь функционал 😄", locale=user.lang)
    full_message_to_user = acceptance_text + bonus_message_part
    
    await callback.bot.send_message(
        chat_id=callback_data.user_id,
        text=full_message_to_user,
        reply_markup=Keyboards.home(i18n, user)
    )
    
    # Set initial subscription (existing logic)
    # await orm.subscription_repo.set_subscription(callback_data.user_id, period=3)
    # Commented out the 3-day subscription as the requirements changed towards token/usage model

@router.callback_query(AdminCallback.filter(F.action == "cancel"))
async def cancel_guest(callback: CallbackQuery,
                        callback_data: AdminCallback,
                        orm: ORM,
                        i18n: I18n,
                        user):
    await orm.user_repo.upsert_user(callback_data.user_id, role="no_access")
    text = callback.message.text + i18n.gettext("\nПользователь отклонен ❌", locale=user.lang)
    await callback.message.edit_text(text=text, reply_markup=Keyboards.empty())
