"""
Gemini AI integration for the Telegram bot
"""
import logging
import aiohttp
import json
from typing import Optional, Dict, Any, List
from config import Environ # Импортируем класс Environ
import base64 # Добавлен импорт для analyze_image
import time

# Configure logger
logger = logging.getLogger(__name__)

class GeminiAI:
    """Class for interacting with Google's Gemini API"""
    
    def __init__(self):
        """Initialize Gemini AI using API key from config"""
        # Создаем экземпляр Environ для доступа к ключу
        config_env = Environ()
        self.api_key = config_env.gemini_api_key # Берем ключ из экземпляра Environ
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in environment variables or config!")
            # Можно добавить обработку ошибки, например, выбрасывать исключение
            # raise ValueError("GEMINI_API_KEY not configured")
            
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        # Используем более новую модель
        self.model_name = "gemini-1.5-flash-latest" 
        self.vision_model_name = "gemini-1.5-flash-latest" # Используем ту же модель для Vision
        
    async def generate_text(self, prompt: str, temperature: float = 0.7, 
                            max_tokens: int = None) -> Optional[str]:
        """
        Generate text using Gemini AI
        
        Args:
            prompt: The text prompt to generate from
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            Generated text or None if error
        """
        if not self.api_key:
             return "Ошибка: Ключ GEMINI_API_KEY не найден."
             
        try:
            url = f"{self.base_url}/{self.model_name}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                }
            }
            
            if max_tokens:
                payload["generationConfig"]["maxOutputTokens"] = max_tokens
                
            # Make async request
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Gemini API error: {response.status}, {error_text}")
                        # Попытка вернуть более читаемую ошибку
                        try:
                            error_data = json.loads(error_text)
                            api_error_msg = error_data.get('error', {}).get('message', error_text)
                            return f"Ошибка API Gemini ({response.status}): {api_error_msg}"
                        except json.JSONDecodeError:
                            return f"Ошибка API Gemini ({response.status}): {error_text}"
                    
                    data = await response.json()
                    
                    # Extract generated text
                    if "candidates" in data and data["candidates"]:
                        candidate = data["candidates"][0]
                         # Проверка на блокировку контента
                        if candidate.get('finishReason') == 'SAFETY':
                             logger.warning(f"Gemini заблокировал ответ по соображениям безопасности.")
                             return "Ошибка: Ответ ИИ был заблокирован по соображениям безопасности."
                        if "content" in candidate and "parts" in candidate["content"]:
                            parts = candidate["content"]["parts"]
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]
                    
                    # Проверка на пустой ответ без кандидатов (например, из-за промпта)
                    if "promptFeedback" in data and data["promptFeedback"].get("blockReason"):
                         block_reason = data["promptFeedback"]["blockReason"]
                         logger.warning(f"Запрос к Gemini заблокирован: {block_reason}")
                         return f"Ошибка: Запрос к ИИ был заблокирован ({block_reason})."
                         
                    logger.error(f"Неожиданный формат ответа Gemini: {data}")
                    return "Ошибка: Не удалось извлечь текст из ответа ИИ."
                
        except aiohttp.ClientConnectorError as e:
             logger.error(f"Ошибка подключения к Gemini API: {str(e)}")
             return f"Ошибка сети при обращении к ИИ: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при генерации текста с помощью Gemini AI: {str(e)}", exc_info=True)
            return f"Внутренняя ошибка при обращении к ИИ: {str(e)}"
            
    async def analyze_image(self, image_data: bytes, prompt: str) -> Optional[str]:
        """
        Analyze image using Gemini Vision capabilities
        
        Args:
            image_data: Binary image data
            prompt: Text prompt describing what to analyze
            
        Returns:
            Analysis result or None if error
        """
        if not self.api_key:
             return "Ошибка: Ключ GEMINI_API_KEY не найден."

        try:
            # Используем vision модель
            url = f"{self.base_url}/{self.vision_model_name}:generateContent?key={self.api_key}"
            
            # Convert image to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg", # Предполагаем JPEG, можно сделать умнее
                                    "data": base64_image
                                }
                            }
                        ]
                    }
                ]
                # Можно добавить generationConfig если нужно
            }
            
            # Make async request
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Gemini Vision API error: {response.status}, {error_text}")
                        try:
                            error_data = json.loads(error_text)
                            api_error_msg = error_data.get('error', {}).get('message', error_text)
                            return f"Ошибка API Gemini Vision ({response.status}): {api_error_msg}"
                        except json.JSONDecodeError:
                            return f"Ошибка API Gemini Vision ({response.status}): {error_text}"
                    
                    data = await response.json()
                    
                    # Extract generated text
                    if "candidates" in data and data["candidates"]:
                        candidate = data["candidates"][0]
                        # Проверка на блокировку контента
                        if candidate.get('finishReason') == 'SAFETY':
                             logger.warning(f"Gemini Vision заблокировал ответ по соображениям безопасности.")
                             return "Ошибка: Ответ ИИ (Vision) был заблокирован по соображениям безопасности."
                        if "content" in candidate and "parts" in candidate["content"]:
                            parts = candidate["content"]["parts"]
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]

                    # Проверка на пустой ответ без кандидатов
                    if "promptFeedback" in data and data["promptFeedback"].get("blockReason"):
                         block_reason = data["promptFeedback"]["blockReason"]
                         logger.warning(f"Запрос к Gemini Vision заблокирован: {block_reason}")
                         return f"Ошибка: Запрос к ИИ (Vision) был заблокирован ({block_reason})."

                    logger.error(f"Неожиданный формат ответа Gemini Vision: {data}")
                    return "Ошибка: Не удалось извлечь текст из ответа ИИ (Vision)."
                
        except aiohttp.ClientConnectorError as e:
             logger.error(f"Ошибка подключения к Gemini Vision API: {str(e)}")
             return f"Ошибка сети при обращении к ИИ (Vision): {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка анализа изображения с помощью Gemini AI: {str(e)}", exc_info=True)
            return f"Внутренняя ошибка при обращении к ИИ (Vision): {str(e)}"

# --- Адаптированная функция для вызова из хендлера ---

MAX_INPUT_TOKENS_SAFE = 30000 # Увеличим запасной лимит токенов для Gemini

async def analyze_file_with_ai(panic_string: str, language: str = 'ru') -> str: # Убран db_solution
    """
    Анализирует panic_string с помощью Gemini для извлечения КЛЮЧЕВОЙ СТРОКИ ОШИБКИ.
    Использует класс GeminiAI.
    Формирует промпт на основе переданного языка ('ru' или 'en').
    Возвращает извлеченную строку ошибки или сообщение об ошибке.
    """
    gemini_ai = GeminiAI()
    if not gemini_ai.api_key:
         return "Error: AI analysis service (Gemini) is unavailable due to missing API key." if language == 'en' else "Ошибка: Сервис анализа ИИ (Gemini) недоступен из-за отсутствия API ключа."

    try:
        logging.info(f"Starting key error extraction with AI (Gemini). Language: {language}. Text length: {len(panic_string)}")
        # Убрана проверка db_solution

        # Обрезаем входной текст
        panic_string = panic_string[:MAX_INPUT_TOKENS_SAFE]
        logging.info(f"Text prepared for Gemini. Length: {len(panic_string)}")

        # Формируем промпт для Gemini на основе языка
        if language == 'en':
            system_instruction = (
                "You are an expert system analyzing iPhone crash logs (panic strings). "
                "Your task is to EXTRACT the single, most relevant error code or concise error message phrase from the provided text. "
                "Examples of expected output: 'Missing sensor(s): mic2', 'AppleBCMWLANCore', 'ap watchdog expired'. "
                "Output ONLY the extracted error string, with no additional text, labels, or explanations. "
                "Do not include 'panic(...)', 'Debugger message:', or similar prefixes."
            )
            user_content = (
                f"Extract the key error code/message from the following panic string:\n\n"
                f"--- Panic String Start ---\n{panic_string}\n--- Panic String End ---\n"
            )
            logging.info("Generated English prompt for Gemini (key error extraction).")
        else: # По умолчанию русский
             system_instruction = (
                "Ты экспертная система, анализирующая crash-логи iPhone (panic strings). "
                "Твоя задача - ИЗВЛЕЧЬ единственный, наиболее релевантный код ошибки или краткую фразу с описанием ошибки из предоставленного текста. "
                "Примеры ожидаемого вывода: 'Missing sensor(s): mic2', 'AppleBCMWLANCore', 'ap watchdog expired'. "
                "Выведи ТОЛЬКО извлеченную строку ошибки, без дополнительного текста, меток или объяснений. "
                "Не включай 'panic(...)', 'Debugger message:' и подобные префиксы."
            )
             user_content = (
                 f"Извлеки ключевой код/сообщение об ошибке из следующей panic string:\n\n"
                 f"--- Panic String Начало ---\n{panic_string}\n--- Panic String Конец ---\n"
             )
             logging.info("Сформирован русский промпт для Gemini (извлечение ключевой ошибки).")

        full_prompt = f"{system_instruction}\n\n{user_content}"

        logging.info("Calling gemini_ai.generate_text for key error extraction...")
        start_time = time.time()

        # Уменьшим max_tokens, так как ожидаем короткий ответ
        ai_response = await gemini_ai.generate_text(prompt=full_prompt, max_tokens=150, temperature=0.2) # Низкая температура для точности

        elapsed_time = time.time() - start_time

        if ai_response is None:
             logging.error("gemini_ai.generate_text returned None during key error extraction")
             return "Error: Failed to get response from AI (method returned None)." if language == 'en' else "Ошибка: Не удалось получить ответ от ИИ (метод вернул None)."

        if ai_response.startswith("Ошибка:") or ai_response.startswith("Error:"):
             logging.warning(f"Received error from gemini_ai.generate_text: {ai_response}")
             return ai_response

        # Убираем возможные кавычки и лишние пробелы из ответа ИИ
        extracted_error = ai_response.strip().strip('"\'')

        logging.info(f"Received key error string from Gemini API in {elapsed_time:.2f} seconds: '{extracted_error}' (Raw: '{ai_response.strip()}')")
        return extracted_error
        
    except Exception as e:
        logging.error(f"Unexpected error in analyze_file_with_ai (key error extraction): {str(e)}", exc_info=True)
        return f"Internal error processing AI request: {str(e)}" if language == 'en' else f"Внутренняя ошибка при обработке запроса ИИ: {str(e)}"