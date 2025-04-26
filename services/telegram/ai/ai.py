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
from services.analyzer.analyzer import LogAnalyzer

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

async def analyze_file_with_ai(panic_string: str, db_solution: str = None, language: str = 'ru') -> str:
    """
    Анализирует panic_string с помощью Gemini, опционально проверяя/улучшая решение из БД.
    Использует класс GeminiAI, предоставленный пользователем.
    Формирует промпт на основе переданного языка ('ru' или 'en').
    """
    gemini_ai = GeminiAI() # Создаем экземпляр класса
    if not gemini_ai.api_key:
         # Логгер уже должен был сработать в __init__, возвращаем ошибку
         return "Error: AI analysis service (Gemini) is unavailable due to missing API key." if language == 'en' else "Ошибка: Сервис анализа ИИ (Gemini) недоступен из-за отсутствия API ключа."

    try:
        logging.info(f"Starting file analysis with AI (Gemini - User Class). Language: {language}. Text length: {len(panic_string)}")
        if db_solution:
            logging.info(f"Provided DB solution for verification/improvement.")

        # Обрезаем входной текст (используем свой лимит)
        panic_string = panic_string[:MAX_INPUT_TOKENS_SAFE]
        logging.info(f"Text prepared for Gemini. Length: {len(panic_string)}")

        # Формируем промпт для Gemini на основе языка
        if language == 'en':
            system_instruction = (
                "You are an expert iPhone repair technician. Analyze crash logs (panic string) and provide solutions. "
                "Response format STRICTLY:\\n"
                "MODEL: [device model if known, otherwise Unknown]\\n"
                "SOLUTION: [specific steps for fixing]\\n"
                "Do not use any markdown formatting (like **, *, etc.) in your response."
            )
            prompt_parts = [system_instruction]
            if db_solution:
                user_content = (
                    f"\\n\\nConsider the provided database solution when analyzing the following iPhone error (panic string):\\n\\n"
                    f"--- Panic String Start ---\\n{panic_string}\\n--- Panic String End ---\\n\\n"
                    f"--- Database Solution Start ---\\n{db_solution}\\n--- Database Solution End ---\\n\\n"
                    f"Provide the most accurate and complete final solution in the required format (MODEL / SOLUTION), incorporating or correcting the database solution as needed."
                )
                prompt_parts.append(user_content)
                logging.info("Generated English prompt for Gemini (using DB solution as reference).")
            else:
                user_content = (
                    f"\\n\\nAnalyze the following iPhone error (panic string) and provide a solution:\\n\\n"
                    f"--- Panic String Start ---\\n{panic_string}\\n--- Panic String End ---\\n\\n"
                    f"Provide the answer in the required format (MODEL / SOLUTION)."
                )
                prompt_parts.append(user_content)
                logging.info("Generated English prompt for Gemini (generation from scratch).")
        else: # По умолчанию русский
             system_instruction = (
                "Ты эксперт по ремонту iPhone. Анализируешь crash-логи (panic string) и предоставляешь решения. "
                "Формат ответа СТРОГО:\\n"
                "МОДЕЛЬ: [модель устройства, если известна, иначе Неизвестно]\\n"
                "РЕШЕНИЕ: [конкретные шаги для исправления]\\n"
                "Не используй никакую markdown-разметку (вроде **, *, и т.д.) в своем ответе."
            )
             prompt_parts = [system_instruction]
             if db_solution:
                user_content = (
                    f"\\n\\nУчти предоставленное решение из базы данных при анализе следующей ошибки iPhone (panic string):\\n\\n"
                    f"--- Panic String Начало ---\\n{panic_string}\\n--- Panic String Конец ---\\n\\n"
                    f"--- Решение из Базы Данных Начало ---\\n{db_solution}\\n--- Решение из Базы Данных Конец ---\\n\\n"
                    f"Предоставь наиболее точное и полное окончательное решение в нужном формате (МОДЕЛЬ / РЕШЕНИЕ), используя или исправляя решение из базы данных по необходимости."
                )
                prompt_parts.append(user_content)
                logging.info("Сформирован промпт для Gemini (используя решение из БД как референс).")
             else:
                user_content = (
                    f"\\n\\nПроанализируй следующую ошибку iPhone (panic string) и предоставь решение:\\n\\n"
                    f"--- Panic String Начало ---\\n{panic_string}\\n--- Panic String Конец ---\\n\\n"
                    f"Предоставь ответ в нужном формате (МОДЕЛЬ / РЕШЕНИЕ)."
                )
                prompt_parts.append(user_content)
                logging.info("Сформирован промпт для Gemini (генерация решения с нуля).")

        full_prompt = "\\n".join(prompt_parts)

        logging.info("Calling gemini_ai.generate_text...")
        start_time = time.time()

        # Вызываем метод из класса пользователя
        ai_response = await gemini_ai.generate_text(prompt=full_prompt, max_tokens=1000) # Укажем лимит токенов для ответа

        elapsed_time = time.time() - start_time

        if ai_response is None:
             # Метод generate_text должен вернуть None или строку с ошибкой в случае неудачи
             logging.error("gemini_ai.generate_text returned None")
             return "Error: Failed to get response from AI (method returned None)." if language == 'en' else "Ошибка: Не удалось получить ответ от ИИ (метод вернул None)."

        # Проверяем, не вернул ли метод строку с ошибкой (уже содержит 'Ошибка:' или 'Error:')
        if ai_response.startswith("Ошибка:") or ai_response.startswith("Error:"):
             logging.warning(f"Received error from gemini_ai.generate_text: {ai_response}")
             return ai_response # Возвращаем текст ошибки как есть

        logging.info(f"Received response from Google Gemini API (User Class) in {elapsed_time:.2f} seconds. Length: {len(ai_response)}")
        return ai_response.strip()
        
    except Exception as e:
        logging.error(f"Unexpected error in analyze_file_with_ai using GeminiAI class: {str(e)}", exc_info=True)
        return f"Internal error processing AI request: {str(e)}" if language == 'en' else f"Внутренняя ошибка при обработке запроса ИИ: {str(e)}"