import io
import json
import re
import logging
import os
import hashlib
import openpyxl
from chardet import detect
from difflib import get_close_matches, SequenceMatcher
from openpyxl.utils import get_column_letter
from PIL import Image
import pytesseract
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Добавлен импорт для обработки ошибок API
# import openai # Убираем импорт OpenAI

# --- СПИСОК ИЗВЕСТНЫХ КОДОВ ОШИБОК (очищенный) ---
KNOWN_ERROR_CODES = [
    "apcie[0:s3e]",
    "ANS2 Recoverable Panic",
    "ANS2 DATA ABORT",
    "AppleBCMWLAN",
    "apcie[0:wlan]",
    "apcie[1:wlan]",
    "apcie[2:wlan]",
    "apcie[3:wlan]",
    "AppleBaseband",
    "baseband-pcie",
    "AppleCS42L75Audio",
    "AppleCS42L77Audio",
    "SEP Memory Protection Module error",
    "AppleOLYHALPortInterfacePCIe",
    "port enable failed:",
    "ApplePMGR",
    "Missing sensor(s): TG0B",
    "0x0, 0x400,",
    "0x0, 0x800,",
    "0x0, 0x1000,",
    "0x0, 0x1800,",
    "0x0, 0x4000,",
    "0x0, 0x20000,",
    "0x0, 0x40000,",
    "0x0, 0x80000,",
    "0x0, 0x100000,",
    "0x0, 0x140000,",
    "0x0, 0x180000,",
    "0x0, 0x200000,",
    "0x0, 0x280000,",
    "0x0, 0x300000,",
    "0x0, 0x400000,",
    "0x0, 0x500000,",
    "0x0, 0x40000000,",
    "0xa1, 0x0,",
    "0x41, 0x0", # Убрана запятая в конце для консистентности
    "0x0, 0xc0000,",
    "0x0, 0x1c0000,",
    "AOP PANIC - [Eiger",
    "AOP PANIC - SCMto:0 - prox",
    "AOP PANIC - SCMto:1 - prox",
    "AOP PANIC - No pulse on",
    "AOP PANIC - moly: bad data",
    "AOP PANIC - !pulse pearl@",
    "AOP PANIC - !pulse main@",
    "Missing sensor(s): Prs0",
    "Missing sensor(s): mic1",
    "Missing sensor(s): mic2",
    "Missing sensor(s): mic3",
    "Missing sensor(s): mic4",
    "Missing sensor(s): TP1A",
    "Missing sensor(s): TP2C",
    "Missing sensor(s): TP3R",
    "Missing sensor(s): TP4H",
    "DCS CHANNEL 2 RDCAL Interrupt",
    "Nested panic detected - entry count: 2 panic_caller",
    "SEP monitor error: INACCESSIBLE SEP",
    "SEP ROM boot panic",
    "SEP Panic",
    "SOCD report detected",
    "AGXSecureGart",
    "Kernel data abort",
    "AppleSocHot: Hot Hot Hot",
    "AOP PANIC - SCMErr:0x0",
    "AOP PANIC - SCMto:",
    "i2c0",
    "i2c1",
    "i2c2",
    "aop-spmi0",
    "aop-spmi1",
    "@PIODMA",
    "for device display-eeprom",
    "for device roswell",
    "@AppleSynopsysMIPIDSIController",
    "IOMFB int_handler",
    "Can't find valid timing element for display",
    "DCP PANIC - ASSERT",
    "DCP PANIC - EDP aggressor table mismatch!",
    "iomfb_ap_callee_0",
    "iomfb_bic_proc_async",
    "DCP PANIC - IOMFB",
    "MTP DATA ABORT",
    "MTP PANIC",
    "SIGNAL, code 6\nservice:", # Экранируем \n
    "userspace watchdog timeout: no successful checkins from SpringBoard",
    "userspace watchdog timeout: no successful checkins from wifid since wake",
    "userspace watchdog timeout: no successful checkins from logd in 180",
    "Port-Lightning",
    "AppleKraken:",
    "AppleHydra:",
    "AppleTriStar2",
    "smc-charger"
]
KNOWN_ERROR_CODES_LOWER = {code.lower() for code in KNOWN_ERROR_CODES} # Для быстрой проверки ответа ИИ

# --- Конец списка ---

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def preprocess_log_content(text):
    text = re.sub(r'<0x[0-9A-Fa-f]+>', '', text)
    
    json_candidates = re.findall(r'\{.*?\}', text, re.DOTALL)
    if json_candidates:
        best_candidate_with_panic = None
        largest_valid_candidate = None
        max_len = -1

        for candidate in json_candidates:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    has_panic_key = any(key.lower() == 'panicstring' for key in data.keys())

                    if has_panic_key:
                        best_candidate_with_panic = candidate
                        logging.info("Найден JSON-кандидат с ключом 'panicString'.")
                        break

                    if len(candidate) > max_len:
                        max_len = len(candidate)
                        largest_valid_candidate = candidate

            except json.JSONDecodeError:
                continue

        if best_candidate_with_panic:
            logging.info("Выбран JSON-кандидат с ключом 'panicString'.")
            return best_candidate_with_panic
        elif largest_valid_candidate:
            logging.info(f"Выбран самый большой валидный JSON-кандидат (длина: {max_len}).")
            return largest_valid_candidate
    
    lines = text.split("\n")
    structured_data = {}
    for line in lines:
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            value = parts[1].strip()
            structured_data[key] = value
    
    if structured_data:
        try:
            logging.info("JSON не найден/выбран, собраны данные из пар ключ:значение.")
            return json.dumps(structured_data)
        except:
            pass
    
    logging.info("JSON не найден/выбран, данные ключ:значение не собраны. Возвращается исходный текст.")
    return text 

def fix_json_structure(text):
    if not text:
        return {}
        
    if isinstance(text, dict):
        return text
        
    if not isinstance(text, str):
        try:
            return json.loads(json.dumps(text))
        except:
            return {}
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            text = re.sub(r'\s+', ' ', text).strip()
            text = re.sub(r'([{\[])\s*"', r'\1"', text)
            text = re.sub(r':\s*"([^"]+)"\s*([,}])', r':"\1"\2', text)
            text = re.sub(r',\s*}', '}', text)
            return json.loads(text)
        except:
            try:
                structured_data = {}
                lines = text.splitlines()
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip()
                        value = parts[1].strip()
                        structured_data[key] = value
                return structured_data if structured_data else {}
            except:
                return {"panicString": text}  # Сохраняем весь текст как panicString

def clean_json_text(text):
    if not isinstance(text, str):
        return json.dumps(text) if hasattr(text, "__iter__") else "{}"
    
    text = re.sub(r'\s+', ' ', text)  
    text = re.sub(r'"\s*([a-zA-Z0-9_]+)\s*"\s*:', r'"\1":', text)  
    text = re.sub(r':\s*"([^"]+)"\s*', r': "\1"', text)  
    text = text.replace('}{', '},{') 
    
    # Проверяем, является ли текст объектом или массивом
    if text.startswith('{') and text.endswith('}'):
        return text
    elif not (text.startswith('[') and text.endswith(']')):
        text = f'[{text}]'
    
    return text

def parse_json_safely(text):
    if isinstance(text, dict):
        return text
        
    try:
        cleaned_text = clean_json_text(text)
        data = json.loads(cleaned_text)
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка JSON: {e}")
        try:
            structured_data = {}
            lines = text.splitlines()
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].strip()
                    value = parts[1].strip()
                    structured_data[key] = value
            return structured_data if structured_data else {"panicString": text}
        except:
            return {"panicString": text}

class LogAnalyzer:
    def __init__(self, lang, path=None, username=None, tesseract_path=None):
        self.panic_sheet = None
        self.nand_sheet = None
        self.gemini_model = None # Атрибут для модели Gemini
        # self.openai_client = None # Убираем атрибут для клиента OpenAI

        # --- Настройка Gemini API ---
        try:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if gemini_api_key:
                genai.configure(api_key=gemini_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
                logging.info("Gemini API клиент успешно настроен (gemini-1.5-flash-latest).")
            else:
                logging.warning("Переменная окружения GEMINI_API_KEY не установлена. Анализ Gemini будет недоступен.")
        except Exception as e:
            logging.error(f"Ошибка инициализации Gemini API: {e}")
        # --- Конец настройки Gemini API ---

        # --- Убираем настройку OpenAI API ---
        # try:
        #     openai_api_key = os.getenv("OPENAI_API_KEY")
        #     # ... (код инициализации OpenAI удален) ...
        # except Exception as e:
        #     logging.error(f"Ошибка инициализации OpenAI API: {e}")
        #     self.openai_client = None
        # --- Конец настройки OpenAI API ---

        # Загружаем panic_codes.xlsx
        try:
            panic_workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
            try:
                 self.panic_sheet = panic_workbook[lang]
                 logging.info(f"Загружен лист '{lang}' из panic_codes.xlsx")
            except KeyError:
                 self.panic_sheet = panic_workbook.active
                 logging.warning(f"Лист '{lang}' не найден в panic_codes.xlsx, используется активный лист: '{self.panic_sheet.title}'")
        except FileNotFoundError:
            logging.error("Файл ./data/panic_codes.xlsx не найден!")
        except Exception as e:
            logging.error(f"Ошибка загрузки panic_codes.xlsx: {e}")

        # Загружаем nand_list.xlsx
        try:
            nand_workbook = openpyxl.load_workbook("./data/nand_list.xlsx")
            try:
                 self.nand_sheet = nand_workbook[lang]
                 logging.info(f"Загружен лист '{lang}' из nand_list.xlsx")
            except KeyError:
                 self.nand_sheet = nand_workbook.active
                 logging.warning(f"Лист '{lang}' не найден в nand_list.xlsx, используется активный лист: '{self.nand_sheet.title}'")
        except FileNotFoundError:
            logging.warning("Файл ./data/nand_list.xlsx не найден! Поиск по нему будет невозможен.")
        except Exception as e:
            logging.error(f"Ошибка загрузки nand_list.xlsx: {e}")
            
        self.path = path
        self.username = username
        self.log = ""
        self.log_dict = {}

        if path is not None:
            self.log = self._process_file(path, tesseract_path)
            if self.log:
                # Используем безопасное парсинг JSON сразу
                self.log_dict = parse_json_safely(self.log)
                # Если парсинг не удался или нет panicString, пытаемся извлечь
                if not isinstance(self.log_dict, dict) or "panicstring" not in {k.lower() for k in self.log_dict.keys()}:
                    _, _, extracted_panic = self.extract_product_info()
                    if "panicString" not in self.log_dict and extracted_panic:
                         self.log_dict["panicString"] = extracted_panic
                    elif "panicString" not in self.log_dict:
                         # Добавляем правильный отступ
                         self.log_dict["panicString"] = self.log

    def _process_file(self, path, tesseract_path):
        """Определяет тип файла и обрабатывает его соответствующим образом."""
        if not os.path.exists(path):
            logging.error(f"Файл не найден: {path}")
            return ""
            
        if path.endswith(('.ips', '.txt', '.json')):
            return self._read_log_file(path)
        elif path.endswith(('.png', '.jpg', '.jpeg')):
            return self._read_photo(path, tesseract_path)
        else:
            logging.warning(f"Неподдерживаемый формат файла: {path}")
            return ""

    @staticmethod
    def _read_log_file(path):
        """Читает файл с автоопределением кодировки"""
        try:
            with open(path, 'rb') as f:
                raw_data = f.read()
                encoding = detect(raw_data)['encoding'] or 'utf-8'
            
            try:
                with open(path, 'r', encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                # если не удалось декодировать с определенной кодировкой, пробуем UTF-8 с игнорированием ошибок
                with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                    return file.read()
        except Exception as e:
            logging.error(f"Ошибка чтения файла {path}: {e}")
            return ""

    @staticmethod
    def _read_photo(path, tesseract_path):
        try:
            img = Image.open(path)
            if tesseract_path:
                pytesseract.tesseract_cmd = tesseract_path
            return pytesseract.image_to_string(img, lang='eng')
        except Exception as e:
            logging.error(f"Ошибка обработки изображения {path}: {e}")
            return ""

    def extract_product_info(self):
        """Извлекает модель/платформу, ключ и panic_string из лога."""
        model = "Неизвестно"
        crash_key = None
        panic_string_value = ""
        log_dict_cleaned_keys = {}

        try:
            # --- Предварительная обработка: получаем словарь с очищенными ключами ---
            if isinstance(self.log_dict, dict):
                 log_dict_cleaned_keys = { re.sub(r'\s+', '', str(k)).lower(): v for k, v in self.log_dict.items() } # Приводим ключи к строке перед очисткой
                 logging.info(f"Очищенные ключи из log_dict: {list(log_dict_cleaned_keys.keys())}")
            else:
                 # Пытаемся исправить структуру, если это не словарь
                 corrected_dict = fix_json_structure(self.log)
                 if isinstance(corrected_dict, dict):
                      self.log_dict = corrected_dict
                      log_dict_cleaned_keys = { re.sub(r'\s+', '', str(k)).lower(): v for k, v in self.log_dict.items() }
                      logging.info(f"Очищенные ключи из log_dict (после исправления): {list(log_dict_cleaned_keys.keys())}")
                 else:
                      logging.warning("log_dict не является словарем и не может быть исправлен, поиск по ключам невозможен.")
                      # В этом случае panicString должен быть всем логом
                      panic_string_value = self.log or ""

            # --- 1. Поиск идентификатора платформы (product) ---
            product_keys_to_check = ["product", "hardwaremodel", "model", "device"]
            found_product = None

            # Шаг 1.1: Ищем в "верхнем" словаре
            for key in product_keys_to_check:
                if key in log_dict_cleaned_keys:
                    value = str(log_dict_cleaned_keys[key] or "").strip()
                    if value:
                        found_product = value
                        logging.info(f"Найден идентификатор платформы по верхнему ключу '{key}': {found_product}")
                        break

            # Шаг 1.2: Если не нашли, пытаемся парсить значение panicstring как JSON (если panicstring есть)
            if not found_product and 'panicstring' in log_dict_cleaned_keys:
                panic_string_content = str(log_dict_cleaned_keys['panicstring'] or "")
                # Очищаем panic_string_content от пробелов МЕЖДУ символами
                cleaned_panic_json_str = panic_string_content
                if re.search(r'\b[a-zA-Z] [a-zA-Z]\b', cleaned_panic_json_str) or re.search(r'" : "', cleaned_panic_json_str):
                    logging.info("Обнаружены пробелы в значении panicstring, применяем очистку...")
                    original_length = len(cleaned_panic_json_str)
                    cleaned_panic_json_str = re.sub(r'\s+(?=[^a-zA-Z0-9\s])|(?<=[^a-zA-Z0-9\s])\s+', '', cleaned_panic_json_str)
                    cleaned_panic_json_str = re.sub(r'(?!\w)\s+(?=\w)|(?<=\w)\s+(?!\w)', '', cleaned_panic_json_str) 
                    cleaned_panic_json_str = ' '.join(cleaned_panic_json_str.split())
                    logging.info(f"Очищенная строка panicstring для JSON парсинга (было {original_length}, стало {len(cleaned_panic_json_str)}): {cleaned_panic_json_str[:200]}...")
                else:
                    logging.info("Пробелы в значении panicstring не обнаружены, очистка не применялась.")
                    
                # Пытаемся распарсить очищенную строку как JSON
                try:
                    # Добавим {} на случай если строка пустая или некорректная
                    inner_data = json.loads(cleaned_panic_json_str or "{}") 
                    if isinstance(inner_data, dict):
                        logging.info(f"Успешно распарсили panicstring как JSON. Ключи: {list(inner_data.keys())}")
                        # Ищем модель внутри этого вложенного словаря (case-insensitive)
                        inner_data_lower_keys = {k.lower(): v for k, v in inner_data.items()}
                        for key in product_keys_to_check:
                            if key in inner_data_lower_keys:
                                value = str(inner_data_lower_keys[key] or "").strip()
                                if value:
                                    found_product = value
                                    logging.info(f"Найден идентификатор платформы по ключу '{key}' ВНУТРИ panicstring JSON: {found_product}")
                                    break # Выходим из внутреннего цикла
                        if found_product: 
                             pass # Уже нашли, ничего не делаем
                        else:
                             logging.info("Ключи модели не найдены внутри panicstring JSON.")
                    else:
                         logging.warning("Распарсенный panicstring не является словарем.")
                except json.JSONDecodeError as e:
                    logging.warning(f"Не удалось распарсить очищенный panicstring как JSON: {e}. Строка (начало): {cleaned_panic_json_str[:200]}...")
                except Exception as e:
                     logging.error(f"Непредвиденная ошибка при парсинге panicstring JSON: {e}")

            # Шаг 1.3: Fallback - ищем старым Regex в сыром тексте лога (если не нашли выше и лог есть)
            if not found_product and self.log:
                logging.info(f"Не найдено ни по ключам, ни в panicstring JSON. Поиск regex в self.log (с удалением пробелов)...")
                try:
                    # Создаем копию лога БЕЗ пробелов
                    log_no_spaces = re.sub(r'\s+', '', self.log)
                    # Ищем ПРОСТОЙ паттерн в тексте БЕЗ пробелов
                    regex_pattern_simple = r'(iPhone\d+,\d+|iPad\d+,\d+|D\d+AP)'
                    match = re.search(regex_pattern_simple, log_no_spaces, re.IGNORECASE)
                    if match:
                        # Найдено! Значение уже без пробелов.
                        found_product = match.group(1) 
                        logging.info(f"Найден идентификатор платформы простым regex в логе без пробелов: '{found_product}'")
                    else:
                        logging.info("Идентификатор платформы НЕ найден простым regex в логе без пробелов.")
                except re.error as e:
                    logging.error(f"Ошибка regex при поиске модели в логе без пробелов: {e}")
            elif not self.log and not found_product:
                 logging.warning("Не найдено ни одним способом, и self.log пуст.")

            model = found_product if found_product else "Неизвестно"
            
            # --- 2. Поиск crashReporterKey (как раньше, по очищенному ключу) ---
            crash_key = log_dict_cleaned_keys.get("crashreporterkey")
            if crash_key:
                 logging.info(f"Найден crashReporterKey: {crash_key}")

            # --- 3. Извлечение panicString VALUE (без очистки здесь) ---
            # Сначала ищем по ключу 'panicstring'
            if 'panicstring' in log_dict_cleaned_keys:
                 panic_string_value = str(log_dict_cleaned_keys['panicstring'] or "")
                 logging.info(f"Извлечено ИСХОДНОЕ значение panicString из словаря: {panic_string_value[:100]}...")
            # Если ключ не найден или значение пустое, И log есть, используем весь log
            elif self.log and not panic_string_value:
                 panic_string_value = self.log
                 logging.warning("panicString не найден/пуст в словаре, используется весь текст лога.")
            elif not self.log and not panic_string_value:
                 logging.warning("panicString не найден/пуст и текст лога тоже пуст.")

            # --- 4. Генерация crash_key (если не найден) ---
            if not crash_key:
                # Очищаем panic_string ПЕРЕД генерацией ключа
                cleaned_key_source = panic_string_value
                if cleaned_key_source and (re.search(r'\b[a-zA-Z] [a-zA-Z]\b', cleaned_key_source) or re.search(r'" : "', cleaned_key_source)):
                    cleaned_key_source = re.sub(r'\s+(?=[^a-zA-Z0-9\s])|(?<=[^a-zA-Z0-9\s])\s+', '', cleaned_key_source)
                    cleaned_key_source = re.sub(r'(?!\w)\s+(?=\w)|(?<=\w)\s+(?!\w)', '', cleaned_key_source) 
                    cleaned_key_source = ' '.join(cleaned_key_source.split())
                key_source = cleaned_key_source if cleaned_key_source else os.path.basename(self.path or "unknown_file")
                crash_key = hashlib.md5(key_source.encode()).hexdigest()
                logging.info(f"crashReporterKey не найден, сгенерирован хэш из panic/имени файла: {crash_key}")

            model_cleaned = model.lower().strip().replace(" ", "")
            
            # Возвращаем извлеченный panic_string_value
            return model_cleaned, crash_key, panic_string_value or ""

        except Exception as e:
            logging.error(f"Ошибка в extract_product_info: {e}", exc_info=True)
            # В случае ошибки генерируем ключ и возвращаем дефолты
            try:
                 key_source = self.log or os.path.basename(self.path or "unknown_file")
                 crash_key = hashlib.md5(key_source.encode()).hexdigest()
            except Exception:
                 crash_key = hashlib.md5(b"error_key").hexdigest()
            return "неизвестно", crash_key, self.log or ""

    # --- ФУНКЦИЯ ДЛЯ ВЫЗОВА GEMINI (Двухэтапная) ---
    def _get_ai_error_code(self, panic_string):
        """
        Определяет код ошибки из списка KNOWN_ERROR_CODES в два этапа:
        1. Получает общее описание ошибки от Gemini.
        2. Просим Gemini сопоставить это описание с кодом из KNOWN_ERROR_CODES.
        Возвращает кортеж: (найденный_код, использовалась_ли_схожесть: bool)
        """
        if not self.gemini_model:
            logging.warning("Модель Gemini не инициализирована. Невозможно получить код ошибки.")
            return None, False # Возвращаем кортеж
        if not panic_string:
            logging.warning("Пустая panic_string передана в _get_ai_error_code.")
            return None, False # Возвращаем кортеж

        max_length = 30000
        panic_string_short = panic_string[:max_length]
        if len(panic_string) > max_length:
            logging.warning(f"Panic string слишком длинный ({len(panic_string)}), обрезается до {max_length} символов для Gemini.")

        # --- Этап 1: Получаем описание ошибки от Gemini ---
        prompt1_template = """Проанализируй следующий фрагмент лога сбоя iOS.
Определи и кратко опиши ОСНОВНУЮ причину сбоя или ключевую фразу ошибки.
Ответь только этой фразой/описанием, без лишних слов.

**Фрагмент лога:**
{log_fragment}
"""
        prompt1 = prompt1_template.format(log_fragment=panic_string_short)
        logging.info("Этап 1: Запрос описания ошибки у Gemini...")
        error_description = None
        try:
            response1 = self.gemini_model.generate_content(
                prompt1,
                generation_config=genai.types.GenerationConfig(temperature=0.1), # Чуть больше свободы для описания
                request_options={'timeout': 30}
            )
            error_description = response1.text.strip()
            logging.info(f"Этап 1: Ответ от Gemini (описание ошибки): '{error_description}'")
            if not error_description:
                 logging.warning("Этап 1: Gemini вернул пустое описание.")
                 return None, False # Возвращаем кортеж

        except google_exceptions.DeadlineExceeded:
             logging.error("Этап 1 Gemini Ошибка API: Превышен таймаут.")
             return None, False # Возвращаем кортеж
        except Exception as e:
            logging.error(f"Этап 1 Gemini Ошибка API: {e}", exc_info=False)
            return None, False # Возвращаем кортеж
        except BaseException as e:
            logging.error(f"Этап 1 Gemini Критическая ошибка: {e}", exc_info=True)
            raise # Перебрасываем критическую ошибку

        # --- Этап 2: Просим Gemini сопоставить описание с кодом из списка ---
        codes_list_str = "\n".join(KNOWN_ERROR_CODES)
        prompt2_template = """Твоя ЗАДАЧА - сопоставить данное описание ошибки с ОДНИМ из кодов в предоставленном ниже списке.
Ты ДОЛЖЕН выбрать НАИБОЛЕЕ ПОХОЖИЙ по смыслу код ТОЛЬКО ИЗ ЭТОГО СПИСКА.

ВАЖНО:
- Список содержит ВСЕ возможные варианты ответа.
- Если ты считаешь, что ни один код из списка ТОЧНО не соответствует описанию, твоя ОБЯЗАННОСТЬ - все равно выбрать САМЫЙ БЛИЗКИЙ ПО СМЫСЛУ вариант из ПРЕДОСТАВЛЕННОГО списка.
- Если ты совсем не уверен, какой код выбрать, выбери ЛЮБОЙ код из списка, который кажется ХОТЬ НЕМНОГО релевантным. Важно, чтобы ответ был из списка.
- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать или возвращать код, которого НЕТ в списке ниже.

**Список ДОПУСТИМЫХ кодов/фраз (выбери ОДИН из них):**
{codes_list}

**Описание ошибки для сопоставления:**
{error_desc}

Твой ответ должен быть ТОЛЬКО ОДНИМ ИЗ КОДОВ, ПЕРЕЧИСЛЕННЫХ ВЫШЕ, без каких-либо изменений, объяснений или добавлений."""

        prompt2 = prompt2_template.format(codes_list=codes_list_str, error_desc=error_description)
        logging.info(f"Этап 2: Запрос сопоставления описания '{error_description[:100]}...' с кодом из списка у Gemini (усиленный промпт, без UNKNOWN)...")
        try:
            response2 = self.gemini_model.generate_content(
                prompt2,
                generation_config=genai.types.GenerationConfig(temperature=0.0),
                request_options={'timeout': 30}
            )
            ai_response_text = response2.text.strip()
            logging.info(f"Этап 2: Ответ от Gemini (сопоставленный код): '{ai_response_text}'")

            if ai_response_text.lower() in KNOWN_ERROR_CODES_LOWER:
                original_code = next((code for code in KNOWN_ERROR_CODES if code.lower() == ai_response_text.lower()), None)
                logging.info(f"Этап 2: Gemini успешно сопоставил код из списка: '{original_code}'")
                return original_code, False # Прямое совпадение, флаг False
            else:
                # Если Gemini все же вернул что-то не из списка, пытаемся найти ближайшее совпадение
                logging.warning(f"Этап 2: Ответ Gemini ('{ai_response_text}') не в списке KNOWN_ERROR_CODES. Поиск ближайшего совпадения...")
                # Ищем одно наиболее похожее совпадение с порогом 0.6
                close_matches = get_close_matches(ai_response_text, KNOWN_ERROR_CODES, n=1, cutoff=0.6)
                if close_matches:
                    closest_match = close_matches[0]
                    # Вычисляем и логируем точный коэффициент схожести для отладки
                    similarity_ratio = SequenceMatcher(None, ai_response_text, closest_match).ratio()
                    logging.warning(f"Этап 2: Найдено ближайшее совпадение в списке: '{closest_match}' для ответа Gemini '{ai_response_text}'. Коэффициент схожести: {similarity_ratio:.4f}")
                    return closest_match, True # Найдено по схожести, флаг True
                else:
                    # Если даже ближайшего совпадения нет, возвращаем None
                    logging.error(f"Этап 2: Не найдено даже близкого совпадения в KNOWN_ERROR_CODES для ответа Gemini: '{ai_response_text}'.")
                    return None, False # Совпадений нет, флаг False

        except google_exceptions.DeadlineExceeded:
             logging.error("Этап 2 Gemini Ошибка API: Превышен таймаут.")
             return None, False # Возвращаем кортеж
        except Exception as e:
            logging.error(f"Этап 2 Gemini Ошибка API: {e}", exc_info=False)
            return None, False # Возвращаем кортеж
        except BaseException as e:
            logging.error(f"Этап 2 Gemini Критическая ошибка: {e}", exc_info=True)
            raise # Перебрасываем критическую ошибку

    # --- НОВАЯ ФУНКЦИЯ ПОИСКА ПО КОНКРЕТНОМУ КОДУ В EXCEL ---
    def _find_solution_by_code(self, sheet, product_key, error_code_from_ai):
        """
        Ищет ТОЧНОЕ совпадение error_code_from_ai в колонке 'A' листа sheet
        и возвращает решение для product_key.
        """
        if not sheet or not product_key or not error_code_from_ai or product_key == "неизвестно":
            return None

        model_column_index = None
        try:
            header_row = sheet[2] # Заголовки моделей во второй строке
        except IndexError:
             logging.error(f"Не удалось прочитать строку заголовков (2) в листе '{sheet.title}'")
             return None

        # Находим индекс колонки для нашей модели
        for cell in header_row:
            if cell.value:
                platform_id = str(cell.value).lower().strip().replace(" ", "")
                if platform_id == product_key:
                    model_column_index = cell.column
                    logging.info(f"Найдена колонка {get_column_letter(model_column_index)} для модели '{product_key}' в листе '{sheet.title}'.")
                    break
        
        if model_column_index is None:
            logging.warning(f"Колонка для модели '{product_key}' не найдена в листе '{sheet.title}'.")
            return None

        # Ищем код ошибки в колонке 'A' (начиная с 3й строки)
        logging.info(f"Поиск кода '{error_code_from_ai}' в колонке 'A' листа '{sheet.title}'...")
        for row_index in range(3, sheet.max_row + 1):
            error_code_cell = sheet.cell(row=row_index, column=1).value
            if not error_code_cell:
                continue
                
            error_code_in_sheet = str(error_code_cell).strip()
            # Сравниваем без учета регистра
            if error_code_in_sheet.lower() == error_code_from_ai.lower():
                solution_cell = sheet.cell(row=row_index, column=model_column_index).value
                solution_text = str(solution_cell or "").strip()
                if solution_text:
                    logging.info(f"Найдено точное совпадение кода '{error_code_from_ai}' в строке {row_index}. Найдено решение.")
                    return {
                        "solutions": [solution_text],
                        "is_full": True,
                        "matched_code": error_code_from_ai # Возвращаем код, который искали
                    }
                else:
                    logging.warning(f"Найдено совпадение кода '{error_code_from_ai}' в строке {row_index}, но ячейка с решением для модели '{product_key}' пуста.")
                    # Продолжаем искать, вдруг код дублируется с решением ниже? (маловероятно, но все же)
                    continue # Обычно здесь должен быть break, но для безопасности оставим continue

        logging.info(f"Код '{error_code_from_ai}' не найден в колонке 'A' листа '{sheet.title}'.")
        return None

    # --- УПРОЩЕННАЯ ОСНОВНАЯ ЛОГИКА АНАЛИЗА (Только Gemini) ---
    def find_error_solutions(self):
        # Проверяем наличие хотя бы одного файла Excel
        if not self.panic_sheet and not self.nand_sheet:
            logging.error("Оба файла Excel (panic_codes, nand_list) не загружены! Поиск невозможен.")
            # Добавляем флаг used_similarity=False
            return [{"solutions": ["Невозможно найти решение - файлы базы знаний отсутствуют."], "is_full": False, "used_similarity": False}]

        # Извлекаем информацию о продукте и паник-строку
        try:
            product, _, panic_string = self.extract_product_info()
            product_cleaned = product.lower().strip().replace(" ", "")
            original_product_name = product if product != "Неизвестно" else None
        except Exception as e:
             logging.error(f"Критическая ошибка при извлечении информации из лога: {e}", exc_info=True)
             # Добавляем флаг used_similarity=False
             return [{"solutions": ["Невозможно найти решение - критическая ошибка обработки лога."], "is_full": False, "used_similarity": False}]

        # Проверяем наличие модели
        if not product_cleaned or product_cleaned == "неизвестно":
             logging.warning(f"Не удалось извлечь 'product'. Анализ невозможен.")
             # Добавляем флаг used_similarity=False
             return [{"solutions": ["solution_not_found_detailed"], "model": ["Неизвестно"], "is_full": False, "used_similarity": False}]

        # Проверяем наличие panic_string
        if not panic_string:
            logging.warning("Отсутствует или пустой panicString для анализа.")
             # Добавляем флаг used_similarity=False
            return [{"solutions": ["Невозможно найти решение - не удалось извлечь текст ошибки (panic string)."], "is_full": False, "used_similarity": False}]

        # --- Шаг 1: Получаем код ошибки от Gemini --- 
        logging.info("Шаг 1: Запрос кода ошибки у Gemini...")
        ai_error_code, used_similarity = self._get_ai_error_code(panic_string) # Получаем и код, и флаг

        if not ai_error_code:
            logging.warning("Gemini не смог определить код ошибки из списка.")
            # Возвращаем ошибку, флаг used_similarity=False (т.к. код не найден)
            return [{"solutions": ["solution_not_found_ai_failed"], "model": [original_product_name or "Неизвестно"], "is_full": False, "used_similarity": False}]

        # Логгируем выбранный код
        logging.info(f"Шаг 1 Завершен: Gemini предложил код '{ai_error_code}' (использована схожесть: {used_similarity}).")

        # --- Шаг 2: Ищем решение в Excel по коду от Gemini ---
        logging.info(f"Шаг 2: Поиск решения для кода '{ai_error_code}' (Gemini) и модели '{product_cleaned}' в Excel...")
        final_solution = None

        if self.panic_sheet:
            logging.info(f"Поиск в panic_codes.xlsx (код: '{ai_error_code}')...")
            final_solution = self._find_solution_by_code(self.panic_sheet, product_cleaned, ai_error_code)

        if not final_solution and self.nand_sheet:
            logging.info(f"Не найдено в panic_codes. Поиск в nand_list.xlsx (код: '{ai_error_code}')...")
            final_solution = self._find_solution_by_code(self.nand_sheet, product_cleaned, ai_error_code)

        # --- Шаг 3: Возвращаем результат --- 
        if final_solution:
            logging.info(f"Шаг 2 Завершен: Решение найдено в Excel для кода '{ai_error_code}' (предложен Gemini).")
            # Добавляем флаг used_similarity в найденное решение
            final_solution["used_similarity"] = used_similarity
            return [final_solution]
        else:
            logging.warning(f"Шаг 2 Завершен: Решение для кода '{ai_error_code}', предложенного Gemini, НЕ найдено в Excel для модели '{product_cleaned}'.")
            # Возвращаем ошибку с указанием кода, который не найден в базе
            # Флаг used_similarity берем из результата _get_ai_error_code
            return [{"solutions": ["solution_not_found_in_excel_for_ai_code"], "model": [original_product_name or "Неизвестно"], "matched_code": [ai_error_code], "ai_source": ["Gemini"], "is_full": False, "used_similarity": used_similarity}]