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
from services.analyzer.analyzer import LogAnalyzer, parse_json_safely, KNOWN_MODEL_IDENTIFIERS, KNOWN_ERROR_CODES
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import ChooseModelCallback, FullButtonCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.ai.ai import analyze_log_via_ai

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

PRICE_PER_ANALYSIS = Decimal(os.getenv("PRICE_PER_ANALYSIS", "1.00"))
os.makedirs("data/tmp", exist_ok=True)

# Сообщение по умолчанию, если решение не найдено
SOLUTION_NOT_FOUND_DETAILED_KEY = "error write @mikoto699"

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
) -> tuple[bool, Decimal, str]:
    user = await orm.user_repo.find_user_by_user_id(user_id)
    if not user:
        return False, Decimal(0), ""

    country_code = await orm.user_repo.get_country_code(user_id)
    price_in_currency, currency_symbol = await orm.currency_repo.get_price_in_user_currency(price, country_code)
    balance = await orm.user_repo.get_balance(user_id)

    if balance < price_in_currency:
        return False, price_in_currency, currency_symbol
    
    if await orm.subscription_repo.check_crash_key_exists(crash_key):
        return True, price_in_currency, currency_symbol

    return True, price_in_currency, currency_symbol

@router.message(F.document.file_name.endswith((".ips", ".txt", ".json")))
async def document_analyze(message: Message, user, orm: ORM, i18n: I18n, state: FSMContext):
    await message.chat.do("typing")
    path = None
    final_response_text = "" # Initialize response text
    ai_analysis_result = None # Initialize AI result
    solution_from_excel = None # Initialize Excel solution
    log_analyzer_instance = None # Initialize LogAnalyzer instance

    try:
        # --- Сохранение файла ---
        await state.update_data(message_id=message.message_id)
        path = await save_file(message, "document")
        if not path:
            await message.answer(i18n.gettext("Ошибка сохранения файла. Попробуйте снова.", locale=user.lang))
            return

        # --- Чтение содержимого файла ---
        try:
            log_content = LogAnalyzer._read_log_file(path)
            if not log_content:
                 await message.answer(i18n.gettext("Файл пустой или не удалось прочитать.", locale=user.lang))
                 return
        except Exception as e:
            logging.error(f"Ошибка чтения файла {path}: {e}", exc_info=True)
            await message.answer(i18n.gettext("Ошибка чтения файла.", locale=user.lang))
            return

        # --- Генерация Crash Key (если возможно из имени файла или контента) ---
        # Генерируем ключ до проверки баланса
        try:
            # Попробуем извлечь из JSON, если он там есть (базовый парсинг)
            crash_key = None
            try:
                log_dict_simple = json.loads(log_content)
                crash_key = log_dict_simple.get("crashReporterKey")
            except json.JSONDecodeError:
                 logging.warning("Лог не является чистым JSON, crashReporterKey не извлечен стандартно.")
                 pass # Ошибка парсинга JSON ожидаема для многих логов

            if not crash_key:
                 key_source = log_content # Используем весь контент для хэша, если ключа нет
                 crash_key = hashlib.md5(key_source.encode()).hexdigest()
                 logging.info(f"crashReporterKey не найден/извлечен, сгенерирован хэш из содержимого лога: {crash_key}")

        except Exception as e:
             logging.error(f"Не удалось сгенерировать crash_key: {e}", exc_info=True)
             # В крайнем случае используем имя файла
             crash_key = hashlib.md5(os.path.basename(path).encode()).hexdigest()
             logging.warning(f"Использован хэш имени файла как crash_key: {crash_key}")

        # --- Проверка и СПИСАНИЕ БАЛАНСА ---
        base_price = Decimal(os.getenv("PRICE_PER_ANALYSIS", "1.00"))
        ok, price_in_currency, currency_symbol = await process_analysis_payment(user.user_id, crash_key, orm, message.bot, base_price)

        if not ok:
            await message.answer(i18n.gettext("Недостаточно средств на балансе. Необходимо {price}{symbol}.", locale=user.lang).format(price=price_in_currency, symbol=currency_symbol))
            return

        # --- Списание средств (если необходимо) ---
        deduct_success = False
        try:
            if not await orm.subscription_repo.check_crash_key_exists(crash_key):
                logging.info(f"Списание {price_in_currency}{currency_symbol} с пользователя {user.user_id} за crash_key {crash_key}")
                deduct_success = await orm.user_repo.deduct_analysis_fee(user.user_id, price_in_currency, crash_key, message.bot)
                if deduct_success:
                    logging.info(f"Списание УСПЕШНО для {user.user_id}.")
                    try:
                        balance = await orm.user_repo.get_balance(user.user_id)
                        deduction_text = i18n.gettext(
                           "С вашего баланса списано {price}{symbol} за анализ файла. Остаток: {balance}{symbol}",
                           locale=user.lang
                        ).format(price=price_in_currency, symbol=currency_symbol, balance=balance)
                        await message.answer(deduction_text)
                    except Exception as e:
                        logging.error(f"Ошибка отправки уведомления о списании: {e}")
                else:
                    logging.warning(f"Списание НЕ УДАЛОСЬ для {user.user_id}.")
                    await message.answer(i18n.gettext("Ошибка при списании средств. Пожалуйста, проверьте баланс или обратитесь к администратору.", locale=user.lang))
                    return # Прерываем, если списание не удалось
            else:
                logging.info(f"Пользователь {user.user_id} уже оплачивал анализ для crash_key {crash_key}. Списание не требуется.")
                deduct_success = True # Считаем успешным, так как уже оплачено
        except Exception as e:
            logging.error(f"Ошибка на этапе проверки/списания: {e}", exc_info=True)
            await message.answer(i18n.gettext("Внутренняя ошибка при обработке платежа.", locale=user.lang))
            return

        # --- Анализ с помощью AI ---
        logging.info(f"Вызов analyze_log_via_ai для файла {path}...")
        await message.chat.do("typing") # Показываем индикатор на время AI анализа
        try:
            ai_analysis_result = await analyze_log_via_ai(log_content, KNOWN_ERROR_CODES)
        except Exception as e:
            logging.error(f"Ошибка при вызове analyze_log_via_ai: {e}", exc_info=True)
            await message.answer(i18n.gettext("Ошибка при обращении к сервису анализа AI.", locale=user.lang))
            return # Прерываем, если AI недоступен

        if not ai_analysis_result:
            logging.warning(f"Анализ AI для файла {path} не вернул результат.")
            await message.answer(i18n.gettext("Не удалось проанализировать лог с помощью AI. Возможно, лог имеет не стандартный формат.", locale=user.lang))
            # Не прерываем полностью, можем попробовать показать только базовую инфу, если есть
            # Но пока просто выходим
            return

        # --- Извлечение данных из результата AI ---
        product_id = ai_analysis_result.get("product")
        os_version = ai_analysis_result.get("os_version")
        timestamp = ai_analysis_result.get("timestamp")
        error_code_from_ai = ai_analysis_result.get("error_code")

        model_name = KNOWN_MODEL_IDENTIFIERS.get(product_id.lower() if product_id else "", "Неизвестно") if product_id else "Неизвестно"
        os_version_str = os_version if os_version else "Неизвестно"
        timestamp_str = timestamp if timestamp else "Неизвестно"

        # --- Формирование заголовка ответа ---
        output_header_parts = [
            f"*Модель:* {model_name} ({product_id})" if product_id else "*Модель:* Неизвестно",
            f"*Версия iOS:* {os_version_str}",
            f"*Дата сбоя:* {timestamp_str}"
        ]
        output_header = "\n".join(output_header_parts)
        logging.info(f"Сформирован заголовок: {output_header}")

        # --- Поиск решения в Excel по данным от AI ---
        if error_code_from_ai and product_id and product_id.lower() != "неизвестно":
            logging.info(f"Поиск решения в Excel для модели '{product_id}' и кода '{error_code_from_ai}'...")
            await message.chat.do("typing") # Еще один индикатор на время поиска в Excel
            try:
                # Инициализируем LogAnalyzer ЗДЕСЬ, только если нужен поиск в Excel
                log_analyzer_instance = LogAnalyzer(lang=user.lang)

                # Ищем сначала в panic_codes.xlsx
                solution_from_excel = log_analyzer_instance._find_solution_by_code(
                    log_analyzer_instance.panic_sheet,
                    product_id,
                    error_code_from_ai
                )
                if solution_from_excel:
                    logging.info(f"Решение найдено в panic_codes.xlsx")
                else:
                    logging.info(f"Решение НЕ найдено в panic_codes.xlsx, ищем в nand_list.xlsx...")
                    # Если не нашли в panic, ищем в nand_list.xlsx
                    solution_from_excel = log_analyzer_instance._find_solution_by_code(
                        log_analyzer_instance.nand_sheet,
                        product_id,
                        error_code_from_ai
                    )
                    if solution_from_excel:
                         logging.info(f"Решение найдено в nand_list.xlsx")
                    else:
                         logging.info(f"Решение НЕ найдено и в nand_list.xlsx.")

            except Exception as e:
                logging.error(f"Ошибка при поиске решения в Excel: {e}", exc_info=True)
                # Не прерываем, просто решение не будет найдено

        # --- Формирование финального ответа ---
        solution_part = ""
        if error_code_from_ai:
            solution_part += f"\n\n*Код ошибки (AI):* `{error_code_from_ai}`" # Используем ` для кода
            if solution_from_excel:
                solution_part += f"\n\n*Решение (Excel):*\n{solution_from_excel}"
            elif product_id and product_id.lower() != "неизвестно":
                # Код ошибки есть, но решения для этой модели нет
                solution_part += f"\n\n*Решение:* {i18n.gettext(SOLUTION_NOT_FOUND_DETAILED_KEY, locale=user.lang)}" # Используем ключ локализации
            else:
                 # Код ошибки есть, но модель неизвестна, поиск не выполнялся
                 solution_part += f"\n\n*Решение:* Невозможно выполнить поиск в базе (модель не определена)."
        else:
            solution_part += f"\n\n*Код ошибки:* {i18n.gettext('Не удалось определить код ошибки по логу.', locale=user.lang)}"

        final_response_text = output_header + solution_part
        logging.info("Финальный текст ответа сформирован.")

    except Exception as e:
        logging.error(f"Критическая ошибка в document_analyze: {e}", exc_info=True)
        final_response_text = i18n.gettext("Произошла непредвиденная ошибка при анализе файла.", locale=user.lang)
        # Попытаемся отправить хоть какое-то сообщение об ошибке
        try:
            await message.answer(final_response_text)
        except Exception as send_error:
             logging.error(f"Не удалось даже отправить сообщение об ошибке: {send_error}")

    finally:
        # Отправляем результат (даже если это сообщение об ошибке, сформированное в except)
        if final_response_text:
            parts = split_message(final_response_text)
            for part in parts:
                await message.answer(part, parse_mode="Markdown") # Используем Markdown

        # Удаляем временный файл
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logging.info(f"Временный файл {path} удален.")
            except Exception as e:
                logging.error(f"Ошибка удаления временного файла {path}: {e}")

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
        
        # Анализируем текст, передавая язык пользователя
        try:
            # Передаем язык пользователя в функцию ИИ
            ai_response = await analyze_file_with_ai(extracted_text, language=user.lang)
        except Exception as e:
            logging.error(f"Ошибка анализа текста: {e}", exc_info=True)
            # Возвращаем ошибку на языке пользователя
            error_message = "Error analyzing text. Please try later." if user.lang == 'en' else "Ошибка при анализе текста. Попробуйте позже."
            await message.answer(error_message)
            return

        # Проверяем ответ ИИ на ошибки
        if ai_response.startswith("Ошибка:") or ai_response.startswith("Error:"):
            await message.answer(ai_response)
            return

        # Форматируем ответ (можно тоже локализовать, но пока оставим так)
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