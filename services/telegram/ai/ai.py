"""
AI integration for the Telegram bot (Now using OpenAI only)
"""
import logging
# import aiohttp # Removed - Was used by GeminiAI
import json
from typing import Optional, Dict, Any, List
from config import Environ # Импортируем класс Environ
# import base64 # Removed - Was used by GeminiAI
# import time # Removed - Was used by GeminiAI
# from services.analyzer.analyzer import LogAnalyzer # Removed - Not used in remaining code
import os
import openai

# Configure logger
logger = logging.getLogger(__name__)

# Removed GeminiAI class definition (lines 16-201 approx.)
                    
# Removed analyze_file_with_ai function definition (lines 204-300 approx.)

# --- Функция для вызова OpenAI ---
# ИЗМЕНЕНО: Используем константу
MAX_LOG_LENGTH_OPENAI = 50000 

async def analyze_log_via_ai(log_content: str, known_error_codes: List[str]) -> Optional[Dict[str, Optional[str]]]:
    """
    Анализирует полный лог с помощью OpenAI (GPT-4o) для извлечения
    информации об устройстве и определения наиболее релевантного кода ошибки.

    Args:
        log_content: Полное содержимое файла лога.
        known_error_codes: Список известных кодов ошибок для выбора.

    Returns:
        Словарь с ключами "product", "os_version", "timestamp", "error_code"
        или None при ошибке. Значения могут быть None, если информация не найдена.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY не найден для analyze_log_via_ai.")
        return None

    # Ограничиваем длину для API, используя константу
    # УДАЛЕНО: Локальная переменная max_length больше не нужна и строка log_content_short
    log_content_for_ai = log_content # По умолчанию используем полный лог
    if len(log_content) > MAX_LOG_LENGTH_OPENAI:
        logger.warning(f"Лог слишком длинный ({len(log_content)}), обрезается до {MAX_LOG_LENGTH_OPENAI} для OpenAI.")
        log_content_for_ai = log_content[:MAX_LOG_LENGTH_OPENAI] # Обрезаем, если нужно

    codes_list_str = "\n".join(known_error_codes)

    system_prompt = f"""Твоя задача - внимательно проанализировать предоставленный лог сбоя iOS.
Извлеки следующую информацию:
1.  **Идентификатор продукта (product):** Найди значение ключа \"product\", \"hardwaremodel\" или аналогичного (например, \"iPhone11,2\", \"iPad8,1\"). Если не найдено, верни null.
2.  **Версия ОС (os_version):** Найди версию ОС, обычно указанную в \"os_version\" (например, \"iPhone OS 17.5.1 (21F90)\"). Если не найдено, верни null.
3.  **Временная метка (timestamp):** Найди дату и время сбоя из ключа \"timestamp\" или \"date\" (например, \"2024-07-27 22:27:33.26 -0700\"). Верни ТОЛЬКО дату и время в формате YYYY-MM-DD HH:MM:SS, отбросив миллисекунды и часовой пояс. Если не найдено, верни null.
4.  **Код ошибки (error_code):** Проанализируй основную причину сбоя, указанную в логе (особенно в \"panicString\"). Выбери ОДИН наиболее подходящий код/фразу из списка ниже, который ТОЧНО соответствует этой причине.

**СПИСОК ДОПУСТИМЫХ КОДОВ/ФРАЗ (выбери ТОЛЬКО ОДИН):**
{codes_list_str}

**ПРАВИЛА ФОРМАТИРОВАНИЯ ОТВЕТА:**
- Верни ТОЛЬКО валидный JSON объект.
- JSON объект должен содержать ТОЛЬКО ключи: \"product\", \"os_version\", \"timestamp\", \"error_code\".
- Значения для ключей должны быть строками или null, если информация не найдена.
- Для \"error_code\" используй ТОЧНОЕ написание кода/фразы из предоставленного списка. НЕ добавляй ничего лишнего.

Пример идеального ответа:
{{
  \"product\": \"iPhone11,2\",
  \"os_version\": \"iPhone OS 17.5.1 (21F90)\",
  \"timestamp\": \"2024-07-27 22:27:33\",
  \"error_code\": \"i2c3\"
}}
Пример, если что-то не найдено:
{{
  \"product\": \"iPhone16,1\",
  \"os_version\": null,
  \"timestamp\": \"2024-12-01 10:30:00\",
  \"error_code\": \"ApplePMGR\"
}}
"""

    # ИЗМЕНЕНО: Используем log_content_for_ai вместо log_content_short
    user_prompt = f"**Лог сбоя iOS:**\n```\n{log_content_for_ai}\n```\n\n**JSON результат:**" 

    logger.info(f"Запрос анализа лога у OpenAI (модель gpt-4o)...")
    try:
        # TODO: Consider using an async client if this function is always awaited (AsyncOpenAI уже используется, все ок)
        client = openai.AsyncOpenAI(api_key=api_key)
        
        # УДАЛЕНО: Блок обрезки лога перенесен выше
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}, # Request JSON output
            temperature=0.0,
            timeout=60 # Increased timeout
        )
        ai_response_raw = response.choices[0].message.content.strip()
        logger.info(f"Ответ от OpenAI (raw JSON): {ai_response_raw}")

        # Attempt to parse JSON - оставляем внутренний try-except
        try:
            ai_result = json.loads(ai_response_raw)
            required_keys = {"product", "os_version", "timestamp", "error_code"}
            if not all(key in ai_result for key in required_keys):
                 logger.error(f"Ответ OpenAI JSON не содержит всех нужных ключей: {ai_result}")
                 return None
            if ai_result.get("error_code") and ai_result["error_code"].lower() not in {c.lower() for c in known_error_codes}:
                 logger.warning(f"Код ошибки '{ai_result['error_code']}' от AI не найден в списке известных кодов!")
            return ai_result
        except json.JSONDecodeError as e:
            logger.error(f"Не удалось распарсить JSON ответ от OpenAI: {e}. Ответ: {ai_response_raw}")
            return None

    # ИЗМЕНЕНО: Правильная обработка ошибок OpenAI API
    except openai.RateLimitError as e:
        logger.error(f"OpenAI Ошибка API (анализ лога): Превышен лимит запросов - {e}")
        # Можно добавить доп. логику, например, уведомление админа или возврат спец. ошибки
        return None # Возвращаем None, чтобы обработчик в analyzer.py мог сообщить об ошибке
    except openai.Timeout as e:
         logger.error(f"OpenAI Ошибка API (анализ лога): Превышен таймаут - {e}")
         return None
    except openai.APIConnectionError as e: # Добавлено: Ошибка соединения
        logger.error(f"OpenAI Ошибка API (анализ лога): Ошибка соединения - {e}")
        return None
    except openai.APIError as e: # Этот должен ловить остальные ошибки 5xx/4xx, не пойманные выше
        logger.error(f"OpenAI Ошибка API (анализ лога): {e}", exc_info=False)
        return None
    except Exception as e: # Общая ошибка
        logger.error(f"Непредвиденная ошибка при вызове OpenAI API (анализ лога): {e}", exc_info=True)
        return None