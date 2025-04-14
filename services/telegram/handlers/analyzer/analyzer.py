import os
import json
import re
import logging
import redis
import hashlib
import openpyxl
from PIL import Image
import pytesseract
from decimal import Decimal
from openpyxl.utils import get_column_letter
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.i18n import I18n
from database.database import ORM
from services.analyzer.analyzer import LogAnalyzer, fix_json_structure, parse_json_safely
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import ChooseModelCallback, FullButtonCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.ai.ai import analyze_file_with_ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

try:
    cache = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
    cache.ping()
    REDIS_AVAILABLE = True
except Exception as e:
    logging.warning(f"Redis недоступен: {e}. Кэширование отключено.")
    REDIS_AVAILABLE = False
    
router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))

PRICE_PER_ANALYSIS = Decimal(os.getenv("PRICE_PER_ANALYSIS", "10.00"))
os.makedirs("data/tmp", exist_ok=True)

def split_message(text, max_length=4000):
    if not text:
        return ["Нет текста для отправки"]
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

async def forward_to_channel(message: Message, channel_id: int, text: str = None) -> Message:
    try:
        if text:
            sent_msg = await message.answer(text)
            await sent_msg.forward(channel_id)
            return sent_msg
        await message.forward(channel_id)
        return message
    except Exception as e:
        logging.error(f"Ошибка пересылки в канал: {e}")
        return None

async def save_file(message: Message, file_type: str = "document") -> str:
    try:
        os.makedirs("data/tmp", exist_ok=True)
        
        if file_type == "document":
            file_id = message.document.file_id
            file_name = message.document.file_name
        elif file_type == "photo":
            file_id = message.photo[-1].file_id
            file_name = f"{message.photo[-1].file_unique_id}.jpg"
        else:
            raise ValueError(f"Неподдерживаемый тип файла: {file_type}")
            
        path = f"data/tmp/{file_name}"
        await message.bot.download(file=file_id, destination=path)
        return path
    except Exception as e:
        logging.error(f"Ошибка сохранения файла: {e}")
        return None

async def process_analysis_payment(
    user_id: int,
    crash_key: str,
    orm: ORM,
    bot: Bot,
    price: Decimal = PRICE_PER_ANALYSIS
) -> bool:
    balance = await orm.user_repo.get_balance(user_id)

    # Даже если crash_key уже есть — не пускаем, если баланса нет
    if balance < price:
        return False
    
    if await orm.subscription_repo.check_crash_key_exists(crash_key):
        return True  
    

    if not await orm.user_repo.deduct_analysis_fee(user_id, price, crash_key,bot):
        return False
    
    try:
        user = await orm.user_repo.find_user_by_user_id(user_id)
        if user:
            balance = await orm.user_repo.get_balance(user_id)
            await bot.send_message(
                user_id,
                f"С вашего баланса списано {price}₸ за анализ файла. Остаток: {balance}₸"
            )
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления о списании: {e}")

    await orm.subscription_repo.save_crash_key(crash_key, user_id)
    return await orm.user_repo.deduct_funds(user_id, PRICE_PER_ANALYSIS, "Анализ файла")

@router.message(F.document.file_name.endswith((".ips", ".txt", ".json")))
async def document_analyze(message: Message, user, orm: ORM, i18n: I18n, state: FSMContext):
    await message.chat.do("typing")
    path = None
    
    try:
        await state.update_data(message_id=message.message_id)
        
        path = await save_file(message, "document")
        if not path:
            await message.answer("Ошибка сохранения файла. Попробуйте снова.")
            return
            
        try:
            log = LogAnalyzer(user.lang, path, message.from_user.username)
        except Exception as e:
            logging.error(f"Ошибка инициализации LogAnalyzer: {e}", exc_info=True)
            await message.answer("Ошибка анализа файла. Проверьте формат файла и попробуйте снова.")
            return
        
        if not log.log:
            await message.answer("Файл пустой или имеет неподдерживаемый формат.")
            return
            
        if not isinstance(log.log_dict, dict):
            log.log_dict = fix_json_structure(log.log)
            if not isinstance(log.log_dict, dict):
                await message.answer("Файл содержит некорректные данные. Не удалось распознать структуру.")
                return
        
        product, crash_key, panic_string = log.extract_product_info()

        if not crash_key:
            crash_key = hashlib.md5(panic_string.encode()).hexdigest()

        if not await process_analysis_payment(user.user_id, crash_key, orm, message.bot):
            await message.answer("Недостаточно средств на балансе.")
            return

        if not panic_string:
            await message.answer("Ошибка: В файле отсутствует информация об ошибке.")
            return
        
        ai_response = None
        if REDIS_AVAILABLE:
            file_hash = hashlib.md5(panic_string.encode()).hexdigest()
            cached_response = cache.get(file_hash)
            if cached_response:
                ai_response = cached_response.decode("utf-8")
                # await message.answer("Кэшированный анализ:\n" + ai_response)
        
        if not ai_response:
            try:
                # Сначала ищем в локальной базе решений
                solutions = log.find_error_solutions()
                if solutions and solutions[0].get("is_full", False):
                    ai_response = "\n".join(solutions[0].get("solutions", ["Решение не найдено"]))
                else:
                    # Если не нашли в базе, используем ИИ
                    ai_response = await analyze_file_with_ai(panic_string, log)
            except Exception as e:
                logging.error(f"Ошибка анализа: {e}", exc_info=True)
                ai_response = "Ошибка при анализе файла. Попробуйте позже."
        
        if "Ошибка" in ai_response:
            await message.answer(ai_response)
            return
            
        if REDIS_AVAILABLE and ai_response and "Ошибка" not in ai_response:
            try:
                file_hash = hashlib.md5(panic_string.encode()).hexdigest()
                cache.set(file_hash, ai_response, ex=3600*24) 
            except Exception as e:
                logging.error(f"Ошибка сохранения в кэш: {e}")
        
        response_text = (
            f"📱 Модель: {product}\n"
            # f"Ошибка: {panic_string.splitlines()[0] if panic_string else 'Неизвестная ошибка'}\n"
            f"Решение:\n{ai_response}"
        )
        
        # Отправляем ответ пользователю
        for part in split_message(response_text):
            sent_msg = await message.answer(part)
            if orm.settings and orm.settings.channel_id:
                try:
                    await sent_msg.forward(orm.settings.channel_id)
                except Exception as e:
                    logging.error(f"Ошибка пересылки в канал: {e}")

    except Exception as e:
        logging.error(f"Ошибка обработки файла: {e}", exc_info=True)
        await notify_no_funds(message, orm)
    
    finally:
        if path and os.path.exists(path):
            os.remove(path)

async def notify_no_funds(message: Message, orm: ORM):
    admins = await orm.user_repo.get_admins()
    admin_contacts = "\n".join([f"@{admin.username}" for admin in admins if admin.username])
    await message.answer(
        f"Ваш баланс равен 0.\n\n"
        f"💬 Пожалуйста, обратитесь к администратору для пополнения баланса:\n\n"
        f"{admin_contacts}"
    )

@router.message(F.photo)
async def photo_analyze(message: Message, user, orm: ORM, i18n: I18n, state: FSMContext):
    await message.chat.do("typing")
    path = None
    
    try:
        await state.update_data(message_id=message.message_id)
        
        path = await save_file(message, "photo")
        if not path:
            await message.answer("Ошибка сохранения изображения. Попробуйте снова.")
            return
        
        # Распознаем текст с изображения
        try:
            img = Image.open(path)
            extracted_text = pytesseract.image_to_string(img, lang='eng')
        except Exception as e:
            logging.error(f"Ошибка распознавания текста: {e}", exc_info=True)
            await message.answer("Ошибка при распознавании текста. Возможно, изображение нечеткое.")
            return
        
        if not extracted_text.strip():
            await message.answer("Ошибка: На изображении не найден текст.")
            return
        
        # Генерируем crash_key из текста
        crash_key = hashlib.md5(extracted_text.encode()).hexdigest()

        # Проверяем баланс и проводим оплату
        if not await process_analysis_payment(user.user_id, crash_key, orm, message.bot):
            await message.answer("Недостаточно средств на балансе.")
            return
        
        # Анализируем текст
        try:
            ai_response = await analyze_file_with_ai(extracted_text)
        except Exception as e:
            logging.error(f"Ошибка анализа текста: {e}", exc_info=True)
            await message.answer("Ошибка при анализе текста. Попробуйте позже.")
            return
        
        if "Ошибка" in ai_response:
            await message.answer(ai_response)
            return
        
        # Форматируем ответ
        response_text = (
            f"📱 Распознанный текст с изображения:\n"
            # f"{extracted_text[:300]}...\n\n"
            f"🛠 Решение:\n{ai_response}"
        )
        
        # Отправляем ответ
        for part in split_message(response_text):
            sent_msg = await message.answer(part)
            if orm.settings and orm.settings.channel_id:
                try:
                    await sent_msg.forward(orm.settings.channel_id)
                except Exception as e:
                    logging.error(f"Ошибка пересылки в канал: {e}")
                
    except Exception as e:
        logging.error(f"Ошибка обработки изображения: {e}", exc_info=True)
        await message.answer("Ошибка при обработке изображения. Попробуйте снова.")
    
    finally:
        if path and os.path.exists(path):
            os.remove(path)

@router.callback_query(ChooseModelCallback.filter())
async def choose_model(
    callback: CallbackQuery, 
    callback_data: ChooseModelCallback, 
    state: FSMContext, 
    i18n: I18n, 
    orm: ORM, 
    user
):
    await callback.message.delete()
    log_info = log_info.get(None)
    
    if not log_info:
        await callback.message.answer("Ошибка: Информация о логах не найдена.")
        return
    
    if callback_data.model not in log_info:
        await callback.message.answer("Ошибка: Модель не найдена в логах.")
        return
    
    await callback.bot.forward_message(
        orm.settings.channel_id, 
        callback.from_user.id, 
        (await state.get_data()).get("message_id")
    )
    
    text = f"Инструкция по починке {callback_data.model}:\nНайденные ошибки:\n"
    msg = await callback.message.answer(text=text)
    await msg.forward(orm.settings.channel_id)
    
    problems = ""
    links = []
    for index, problem in enumerate(log_info, start=1):
        model = problem.get(callback_data.model)
        sub_solutions = '\n'.join(model.get('solutions'))
        problems += f"{index}) {sub_solutions}"
        links.extend(model.get('links'))
        
        if model.get("image"):
            msg = await callback.message.bot.send_photo(
                callback.message.from_user.id, 
                FSInputFile(model["image"])
            )
            await msg.forward(orm.settings.channel_id)
            os.remove(model.get("image"))
        
        msg = await callback.message.answer(
            problems, 
            reply_markup=Keyboards.links(model["links"], i18n, user) if model.get("links") else None
        )
        await msg.forward(orm.settings.channel_id)