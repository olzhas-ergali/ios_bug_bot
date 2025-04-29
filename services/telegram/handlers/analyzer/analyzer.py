import os
import json
import re
import logging
import redis
import hashlib
import openpyxl
import asyncio
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
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- ДОБАВЛЕНО: Семафор для ограничения одновременных вызовов OpenAI ---
# Значение 1 означает, что только один анализ будет выполняться одновременно
openai_semaphore = asyncio.Semaphore(1)

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

@router.message(F.document.file_name.endswith((".ips", ".txt", ".json")))
async def document_analyze(message: Message, user, orm: ORM, i18n: I18n, state: FSMContext):
    
    # Используем семафор для контроля доступа к блоку анализа
    async with openai_semaphore:
    await message.chat.do("typing")
    path = None
        final_response_text = ""
        ai_analysis_result = None
        solution_from_excel = None
        log_analyzer_instance = None
        analysis_result = None # To store if analysis was paid, free, or failed due to balance

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
                     # Ensure file is cleaned up even if empty
                     if path and os.path.exists(path):
                         try: os.remove(path); logging.info(f"Удален пустой/нечитаемый файл: {path}")
                         except OSError as e_rm: logging.error(f"Ошибка удаления файла {path}: {e_rm}")
                 return
        except Exception as e:
            logging.error(f"Ошибка чтения файла {path}: {e}", exc_info=True)
            await message.answer(i18n.gettext("Ошибка чтения файла.", locale=user.lang))
                # Ensure file is cleaned up on read error
                if path and os.path.exists(path):
                    try: os.remove(path); logging.info(f"Удален файл после ошибки чтения: {path}")
                    except OSError as e_rm: logging.error(f"Ошибка удаления файла {path}: {e_rm}")
            return

            # --- Генерация Crash Key ---
            crash_key = None
            try:
                 log_dict_simple = parse_json_safely(log_content) # Use safe parsing
                 if isinstance(log_dict_simple, dict):
                      # Case-insensitive search for key
                      for key in log_dict_simple:
                           if key.lower() == "crashreporterkey":
                                crash_key = log_dict_simple[key]
                                break

            if not crash_key:
                     key_source = log_content
                 crash_key = hashlib.md5(key_source.encode()).hexdigest()
                 logging.info(f"crashReporterKey не найден/извлечен, сгенерирован хэш из содержимого лога: {crash_key}")
                 else:
                      logging.info(f"Извлечен crashReporterKey: {crash_key}")

        except Exception as e:
             logging.error(f"Не удалось сгенерировать crash_key: {e}", exc_info=True)
             crash_key = hashlib.md5(os.path.basename(path).encode()).hexdigest()
             logging.warning(f"Использован хэш имени файла как crash_key: {crash_key}")


            # --- Проверка Подписки и Баланса Токенов ---
            analysis_result = "pending" # paid, free_sub, no_tokens
            subscription = await orm.subscription_repo.get_subscription(user.user_id, crash_key)
            now = datetime.now()
            is_subscription_active_and_valid = False
    
            if subscription and subscription.date_end and now < subscription.date_end and subscription.analysis_count < 10:
                 is_subscription_active_and_valid = True
                 analysis_result = "free_sub"
                 logging.info(f"Активная подписка найдена для user {user.user_id}, crash_key {crash_key}. Анализ будет бесплатным ({subscription.analysis_count + 1}/10).")
            else:
                 # Если нет активной подписки, проверяем баланс токенов
                 token_balance = await orm.user_repo.get_token_balance(user.user_id)
                 if token_balance >= 1:
                     analysis_result = "paid"
                     logging.info(f"Подписка неактивна/нет. Баланс токенов ({token_balance}) достаточен. Анализ будет платным (1 токен).")
                 else:
                     analysis_result = "no_tokens"
                     logging.warning(f"Недостаточно токенов для user {user.user_id} (баланс: {token_balance}).")
                     # TODO: i18n: Localize no tokens message
                     await message.answer(i18n.gettext("Недостаточно токенов на балансе. Необходимо 1 токен для анализа.", locale=user.lang))
                     # Ensure file is cleaned up on no tokens
                     if path and os.path.exists(path):
                          try: os.remove(path); logging.info(f"Удален файл из-за нехватки токенов: {path}")
                          except OSError as e_rm: logging.error(f"Ошибка удаления файла {path}: {e_rm}")
                     return # Прерываем выполнение

        # --- Анализ с помощью AI ---
        logging.info(f"Вызов analyze_log_via_ai для файла {path}...")
            await message.chat.do("typing")
        try:
                # Этот вызов теперь внутри семафора
            ai_analysis_result = await analyze_log_via_ai(log_content, KNOWN_ERROR_CODES)
            except Exception as e: # Ловим общую ошибку здесь на всякий случай, хотя ai.py должен возвращать None
                logging.error(f"Непредвиденная ошибка при вызове analyze_log_via_ai в обработчике: {e}", exc_info=True)
                ai_analysis_result = None # Устанавливаем в None, чтобы обработать ниже
            
            # --- Обработка результата AI и поиск решения в Excel ---
        if not ai_analysis_result:
                logging.warning(f"Анализ лога для файла {path} не вернул результат или произошла ошибка.")
                # TODO: i18n: Localize AI no result/error message
                # ИЗМЕНЕНО: Убрано слово "AI"
                await message.answer(i18n.gettext("Не удалось проанализировать лог. Возможно, сервис анализа временно недоступен или формат лога не стандартный.", locale=user.lang))
                # Токен не списываем, т.к. анализ не удался
                # Сообщение об этом теперь не нужно, т.к. списание происходит только при успехе
                # if analysis_result == "paid":
                #     await message.answer(i18n.gettext("Токен не был списан.", locale=user.lang))
                # Возвращаемся, чтобы finally удалил файл
            return

        product_id = ai_analysis_result.get("product")
        os_version = ai_analysis_result.get("os_version")
        timestamp = ai_analysis_result.get("timestamp")
        error_code_from_ai = ai_analysis_result.get("error_code")

        model_name = KNOWN_MODEL_IDENTIFIERS.get(product_id.lower() if product_id else "", "Неизвестно") if product_id else "Неизвестно"
        os_version_str = os_version if os_version else "Неизвестно"
        timestamp_str = timestamp if timestamp else "Неизвестно"

        output_header_parts = [
                f"*{i18n.gettext('Информация об устройстве:', locale=user.lang)}*",
                f"📱 {i18n.gettext('Модель:', locale=user.lang)} {model_name} ({product_id})" if product_id else f"📱 {i18n.gettext('Модель:', locale=user.lang)} {i18n.gettext('Неизвестно', locale=user.lang)}",
                f"🛠️ {i18n.gettext('Версия iOS:', locale=user.lang)} {os_version_str}",
                f"📅 {i18n.gettext('Дата сбоя:', locale=user.lang)} {timestamp_str}"
        ]
        output_header = "\n".join(output_header_parts)
        logging.info(f"Сформирован заголовок: {output_header}")

            solution_found_in_excel = False
        if error_code_from_ai and product_id and product_id.lower() != "неизвестно":
            logging.info(f"Поиск решения в Excel для модели '{product_id}' и кода '{error_code_from_ai}'...")
                await message.chat.do("typing")
            try:
                log_analyzer_instance = LogAnalyzer(lang=user.lang)
                    solution_from_excel = log_analyzer_instance._find_solution_by_code(
                        log_analyzer_instance.panic_sheet, product_id, error_code_from_ai
                    )
                    if solution_from_excel:
                        logging.info(f"Решение найдено в panic_codes.xlsx")
                        solution_found_in_excel = True
                    else:
                         # Убрал поиск в NAND здесь, т.к. его логика вынесена отдельно и не является прямым решением
                         logging.info(f"Решение НЕ найдено в panic_codes.xlsx.")

            except Exception as e:
                logging.error(f"Ошибка при поиске решения в Excel: {e}", exc_info=True)

        # --- Формирование финального ответа ---
            if solution_from_excel:
                # Обрабатываем текст решения для лучшего отображения Markdown
                processed_solution = solution_from_excel.strip()
                # Добавляем пробел после дефиса в начале строки для корректного списка
                processed_solution = re.sub(r"^\s*-", "- ", processed_solution, flags=re.MULTILINE)
                
                final_response_text = f"{output_header}\n\n*{i18n.gettext('Решение:', locale=user.lang)}*\n{processed_solution}"
            else:
                # Если Excel не помог
                # TODO: i18n: Localize new title and no solution message
                # ИЗМЕНЕНО: Добавляем жирный заголовок перед сообщением об отсутствии решения
                no_solution_title = f"*{i18n.gettext('Найденные ошибки и рекомендации по ремонту:', locale=user.lang)}*"
                no_solution_message = i18n.gettext('Решение не найдено в базе знаний. Проверьте информацию выше.', locale=user.lang)
                final_response_text = f"{output_header}\n\n{no_solution_title}\n{no_solution_message}"
                logging.warning(f"Финальное решение не найдено для {path}")

            # --- Списание Токена / Обновление Подписки ---
            # ИЗМЕНЕНО: Переносим логику списания/подписки ВНУТРЬ условия `if solution_found_in_excel`
            token_spent_message = ""
            
            if solution_found_in_excel: # <--- НОВОЕ УСЛОВИЕ
                if analysis_result == "paid":
                     # Списываем 1 токен
                     deducted = await orm.user_repo.deduct_token(user.user_id)
                     if deducted:
                          logging.info(f"Успешно списан 1 токен у пользователя {user.user_id} за crash_key {crash_key}, т.к. решение найдено.")
                          new_token_balance = await orm.user_repo.get_token_balance(user.user_id)
                          token_spent_message = i18n.gettext("\n\nСписан 1 токен (остаток: {balance}). ", locale=user.lang).format(balance=new_token_balance)
                          
                          # Создаем или обновляем подписку (если ее не было или она истекла)
                          if not is_subscription_active_and_valid:
                               subscription_start_date = datetime.now()
                               subscription_end_date = subscription_start_date + timedelta(days=30)
                               sub_created = await orm.subscription_repo.create_or_reset_subscription(
                                    user_id=user.user_id,
                                    crash_key=crash_key,
                                    start_date=subscription_start_date,
                                    end_date=subscription_end_date
                               )
                               if sub_created:
                                    logging.info(f"Создана/обновлена подписка для user {user.user_id}, crash_key {crash_key}.")
                                    token_spent_message += i18n.gettext("Запущен 30-дневный период: следующие 9 анализов для **этого устройства** будут бесплатными.", locale=user.lang)
                               else:
                                    logging.error(f"Не удалось создать/обновить подписку для user {user.user_id}, crash_key {crash_key}.")
                     else:
                          logging.error(f"Не удалось списать токен у user {user.user_id}, хотя проверка баланса прошла и решение найдено.")
                          token_spent_message = i18n.gettext("\n\nОшибка при списании токена.", locale=user.lang)
            
            elif analysis_result == "free_sub": 
                 # Увеличиваем счетчик бесплатного анализа
                 updated = await orm.subscription_repo.increment_analysis_count(user.user_id, crash_key)
                 if updated:
                      analyses_done = (subscription.analysis_count if subscription else 0) + 1
                      logging.info(f"Успешно увеличен счетчик анализов для user {user.user_id}, crash_key {crash_key}. Счетчик: {analyses_done}/10.")
                      token_spent_message = i18n.gettext("\n\nАнализ проведен бесплатно по подписке ({count}/10 для этого устройства).", locale=user.lang).format(count=analyses_done)
        else:
                      logging.error(f"Не удалось увеличить счетчик анализов для user {user.user_id}, crash_key {crash_key}.")
                      token_spent_message = i18n.gettext("\n\nОшибка при обновлении счетчика бесплатных анализов.", locale=user.lang)
            
            elif analysis_result != 'no_tokens': 
                # TODO: i18n: Localize no solution no token spent message
                token_spent_message = i18n.gettext("\n\nТокен **не списан**, т.к. готовое решение не найдено в базе.", locale=user.lang)
                logging.info(f"Токен не списан для user {user.user_id}, crash_key {crash_key}, т.к. решение не найдено в Excel.")

            # --- Отправка финального ответа ---
            # Добавляем информацию о токене/подписке с отступом
            if token_spent_message:
                final_response_text += f"\n\n{token_spent_message.strip()}"
            
            response_parts = split_message(final_response_text)
            for part in response_parts:
                # Указываем parse_mode="Markdown" для обработки звездочек
                await message.answer(part, parse_mode="Markdown") 
            logging.info(f"Финальный текст ответа сформирован.")

    except Exception as e:
            logging.exception(f"Общая ошибка в document_analyze для user {message.from_user.id} (внутри семафора)")
            # TODO: i18n: Localize generic error message
            try:
                await message.answer(i18n.gettext("Произошла непредвиденная ошибка при анализе файла.", locale=user.lang))
            except Exception as send_err:
                 logging.error(f"Не удалось отправить сообщение об ошибке пользователю {message.from_user.id}: {send_err}")
            # Сообщение о несписании токена здесь может быть неточным, т.к. ошибка могла случиться до проверки баланса

    finally:
            # --- Очистка временного файла ---
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logging.info(f"Временный файл {path} удален.")
                except OSError as e:
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