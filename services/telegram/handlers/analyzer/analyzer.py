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

PRICE_PER_ANALYSIS = Decimal(os.getenv("PRICE_PER_ANALYSIS", "1.00"))
os.makedirs("data/tmp", exist_ok=True)

# Сообщение по умолчанию, если решение не найдено
SOLUTION_NOT_FOUND_DETAILED_KEY = "solution_not_found_detailed"

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
    try:
        # --- Сохранение файла и базовая валидация ---
        await state.update_data(message_id=message.message_id)
        path = await save_file(message, "document")
        if not path:
            await message.answer("Ошибка сохранения файла. Попробуйте снова.") # TODO: Локализовать
            return
        try:
            log = LogAnalyzer(user.lang, path, message.from_user.username)
        except Exception as e:
            logging.error(f"Ошибка инициализации LogAnalyzer: {e}", exc_info=True)
            await message.answer("Ошибка анализа файла. Проверьте формат файла и попробуйте снова.") # TODO: Локализовать
            return
        if not log.log:
            await message.answer("Файл пустой или имеет неподдерживаемый формат.") # TODO: Локализовать
            return
        if not isinstance(log.log_dict, dict):
            log.log_dict = fix_json_structure(log.log)
            if not isinstance(log.log_dict, dict):
                await message.answer("Файл содержит некорректные данные. Не удалось распознать структуру.") # TODO: Локализовать
                return
                
        # --- Извлечение информации --- 
        # Извлекаем модель ЗДЕСЬ, чтобы она была доступна позже для форматирования
        product, crash_key, panic_string = log.extract_product_info()
        # Сохраняем исходное имя модели (или "Неизвестно")
        model_name_for_response = product if product != "неизвестно" else "Неизвестно"
        
        if not crash_key: 
             key_source = panic_string if panic_string else os.path.basename(path or "unknown_file")
             crash_key = hashlib.md5(key_source.encode()).hexdigest()
             logging.info(f"crashReporterKey не найден, сгенерирован хэш из panic/имени файла: {crash_key}")

        # --- Проверка и СПИСАНИЕ БАЛАНСА ---
        base_price = Decimal(os.getenv("PRICE_PER_ANALYSIS", "1.00"))
        ok, price_in_currency, currency_symbol = await process_analysis_payment(user.user_id, crash_key, orm, message.bot, base_price)
        
        if not ok:
            # process_analysis_payment вернет False, если баланса не хватает
            await message.answer(i18n.gettext("Недостаточно средств на балансе. Необходимо {price}{symbol}.", locale=user.lang).format(price=price_in_currency, symbol=currency_symbol))
            return

        # Списываем средства *после* проверки, но *до* отправки результата
        logging.info("--- Начало блока списания (новая логика) ---")
        logging.info(f"Попытка списания {price_in_currency}{currency_symbol} с пользователя {user.user_id} за crash_key {crash_key}")
        deduct_success = False
        try:
            # Проверяем, не был ли этот crash_key оплачен ранее
            if not await orm.subscription_repo.check_crash_key_exists(crash_key):
                 logging.info("Вызов await orm.user_repo.deduct_analysis_fee...")
                 deduct_success = await orm.user_repo.deduct_analysis_fee(user.user_id, price_in_currency, crash_key, message.bot)
                 logging.info(f"Результат deduct_analysis_fee: {deduct_success}")
                 if not deduct_success:
                      logging.warning(f"Списание средств НЕ УДАЛОСЬ для пользователя {user.user_id}.")
                      await message.answer(i18n.gettext("Ошибка при списании средств. Пожалуйста, проверьте баланс или обратитесь к администратору.", locale=user.lang))
                      # Не выходим, так как пользователь уже оплатил или это повторный анализ
                 else:
                      logging.info(f"Списание средств УСПЕШНО для пользователя {user.user_id}.")
                      # Отправка уведомления о списании только если списание успешно
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
                logging.info(f"Пользователь {user.user_id} уже оплачивал анализ для crash_key {crash_key}. Списание не требуется.")
                deduct_success = True # Считаем успешным, так как уже оплачено

        except Exception as e:
            logging.error(f"Ошибка на этапе проверки/списания: {e}", exc_info=True)
            await message.answer(i18n.gettext("Внутренняя ошибка при обработке платежа.", locale=user.lang))
            return # Выходим если ошибка на этапе платежа

        # --- Поиск решения ТОЛЬКО в локальной базе ---
        final_response_text = ""
        solution_used_similarity = False # Инициализируем флаг
        try:
            # Передаем product и panic_string в функцию поиска
            solutions_from_db = log.find_error_solutions()
            
            # Извлекаем флаг used_similarity из первого (и единственного) результата
            if solutions_from_db:
                solution_used_similarity = solutions_from_db[0].get("used_similarity", False)
                logging.info(f"Флаг used_similarity из find_error_solutions: {solution_used_similarity}")
            
            first_solution_info = solutions_from_db[0] if solutions_from_db else {}
            solution_key = first_solution_info.get("solutions", [None])[0]

            if solution_key == SOLUTION_NOT_FOUND_DETAILED_KEY:
                # Используем модель, извлеченную ранее
                logging.info(f"Решение для crash_key {crash_key} (модель: {model_name_for_response}) в локальной БД не найдено.")
                final_response_text = i18n.gettext(
                    "Модель: {model}\nРешение:\nРешение не найдено в нашей базе. Скоро добавим!", 
                    locale=user.lang
                ).format(model=model_name_for_response)
            
            elif solutions_from_db: 
                solution_text = "\n".join(first_solution_info.get("solutions", []))
                if solution_text: 
                    # --- ВОЗВРАЩАЕМ ФОРМАТИРОВАНИЕ --- 
                    response_parts = []
                    response_parts.append(f"Модель: {model_name_for_response}")
                    response_parts.append(f"Решение:\n{solution_text}")
                    final_response_text = "\n\n".join(response_parts) # Разделяем блоки
                    logging.info(f"Найдено решение из БД для crash_key {crash_key}. Отправляем форматированный текст.")
                else:
                    # Если текст решения пустой, считаем, что не найдено (используем новый формат)
                    model_name = first_solution_info.get("model", ["Неизвестно"])[0] # Попытаемся получить модель, если она была передана
                    logging.warning(f"Найдено совпадение для crash_key {crash_key}, но текст решения в БД пуст.")
                    final_response_text = i18n.gettext(
                         "Модель: {model}\nРешение:\nРешение не найдено в нашей базе. Скоро добавим!", 
                         locale=user.lang
                    ).format(model=model_name)
            else:
                 # На случай, если find_error_solutions вернул пустой список (не должно происходить)
                 logging.error(f"find_error_solutions вернул пустой список для {crash_key}")
                 final_response_text = i18n.gettext(
                         "Модель: Неизвестно\nРешение:\nРешение не найдено в нашей базе. Скоро добавим!", 
                         locale=user.lang
                    )

        except Exception as e:
            logging.error(f"Ошибка поиска/форматирования решения из БД: {e}", exc_info=True)
            final_response_text = i18n.gettext("Ошибка при поиске решения в базе данных.", locale=user.lang)

        # --- Отправка финального ответа пользователю (ТОЛЬКО из Excel) ---
        # --- ЭКСПЕРИМЕНТ: Анализ через AI для СРАВНЕНИЯ в логах (встроен в блок отправки) ---
        # Важно: Этот результат НЕ будет отправлен пользователю!
        ai_comparison_result = "AI анализ не проводился или не удался."
        if panic_string: # panic_string был извлечен в начале функции document_analyze
            try:
                logging.info(f"--- [Сравнение] Запуск AI анализа для crash_key {crash_key} ---")
                ai_response_text = await analyze_file_with_ai(panic_string=panic_string, language=user.lang)
                if ai_response_text and not ai_response_text.startswith("Ошибка:") and not ai_response_text.startswith("Error:"):
                    ai_comparison_result = ai_response_text.strip()
                    logging.info(f"--- [Сравнение] Успешный результат AI анализа для crash_key {crash_key} ---")
                else:
                    ai_comparison_result = f"AI анализ вернул ошибку или пустой результат: {ai_response_text}"
                    logging.warning(f"--- [Сравнение] Ошибка/пустой результат AI анализа для crash_key {crash_key}: {ai_response_text}")
            except Exception as ai_err:
                logging.error(f"--- [Сравнение] Исключение при вызове AI анализа для crash_key {crash_key}: {ai_err}", exc_info=True)
                ai_comparison_result = f"Исключение при вызове AI анализа: {ai_err}"
        else:
            logging.warning(f"--- [Сравнение] AI анализ пропущен для crash_key {crash_key}, т.к. panic_string пуст или не извлечен.")

        # Логируем ОБА результата для сравнения
        logging.info(f"""--- [Сравнение] Результат EXCEL для crash_key {crash_key} ---
{final_response_text}
--- КОНЕЦ EXCEL --- """)
        logging.info(f"""--- [Сравнение] Результат   AI  для crash_key {crash_key} ---
{ai_comparison_result}
--- КОНЕЦ AI --- """)
        # -------------------------------------------------------------

        if not final_response_text: # На всякий случай, если текст пустой после всех проверок
            final_response_text = i18n.gettext("Не удалось сформировать ответ.", locale=user.lang)

        # Определяем текст для отправки (с суффиксом или без)
        text_to_send = final_response_text
        if solution_used_similarity: # Проверяем флаг
            text_to_send += "\n\n*если вы думаете что инструкция неккоректна пишите @onyokaa*"
            logging.info("Добавлен суффикс, так как использовался поиск по схожести.")
        else:
            logging.info("Суффикс не добавлен, так как НЕ использовался поиск по схожести.")

        logging.info(f"--- [ПРОВЕРКА] Отправка ответа пользователю для crash_key {crash_key} ---")
        sent_messages = []
        # Используем text_to_send для отправки
        for part in split_message(text_to_send):
            # Отправляем с parse_mode="Markdown", если суффикс был добавлен (чтобы звездочки работали)
            # Иначе отправляем обычным текстом
            parse_mode = "Markdown" if solution_used_similarity else None 
            sent_msg = await message.answer(part, parse_mode=parse_mode)
            sent_messages.append(sent_msg) 
            if orm.settings and orm.settings.channel_id:
                 try:
                     await sent_msg.forward(orm.settings.channel_id)
                 except Exception as e:
                     logging.error(f"Ошибка пересылки в канал: {e}")

        # Сохраняем результат ответа из базы данных (который был отправлен) в FSM для возможной кнопки "Полный лог"
        # Используем оригинальный текст БЕЗ суффикса
        await state.update_data(last_db_response=final_response_text)

    except Exception as e:
        # Общая обработка ошибок
        logging.error(f"Критическая ошибка обработки файла: {e}", exc_info=True)
        await message.answer(i18n.gettext("Произошла непредвиденная ошибка при обработке файла.", locale=user.lang))
        # Не уведомляем о балансе здесь, т.к. ошибка могла быть до проверки баланса

    finally:
        # Очистка временного файла
        if path and os.path.exists(path):
            try:
                os.remove(path)
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