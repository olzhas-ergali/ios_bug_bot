import io
import json
import re
import logging
import os
import hashlib
import asyncio
import openpyxl
from openpyxl.utils import get_column_letter
from chardet import detect
from PIL import Image
import pytesseract
from services.telegram.ai.ai import analyze_file_with_ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Константа для обозначения ненайденного решения (для совместимости с хендлером)
SOLUTION_NOT_FOUND_DETAILED_KEY = "solution_not_found_detailed"

def preprocess_log_content(text):
    text = re.sub(r'<0x[0-9A-Fa-f]+>', '', text)
    
    json_candidates = re.findall(r'\{.*?\}', text, re.DOTALL)
    if json_candidates:
        return json_candidates[0]
    
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
            return json.dumps(structured_data)
        except:
            pass
    
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
        
        # --- Восстановлена загрузка Excel файлов --- 
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
        # --- Конец восстановления загрузки Excel --- 
            
        self.path = path
        self.username = username
        self.lang = lang
        self.log = ""
        self.log_dict = {}

        if path is not None:
            self.log = self._process_file(path, tesseract_path)
            if self.log:
                json_candidate = preprocess_log_content(self.log)
                if isinstance(json_candidate, dict):
                    self.log_dict = json_candidate
                else:
                    self.log_dict = fix_json_structure(json_candidate)
                
                if not self.log_dict or not self.log_dict.get("panicString"):
                    self.log_dict = self.log_dict or {}
                    _, _, extracted_panic = self.extract_product_info()
                    if "panicString" not in self.log_dict and extracted_panic:
                         self.log_dict["panicString"] = extracted_panic
                    elif "panicString" not in self.log_dict:
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
                 log_dict_cleaned_keys = { re.sub(r'\s+', '', k).lower(): v for k, v in self.log_dict.items() }
                 logging.info(f"Очищенные ключи из log_dict: {list(log_dict_cleaned_keys.keys())}")
            else:
                 logging.warning("log_dict не является словарем, поиск по ключам невозможен.")

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
            
            # Шаг 1.2: Если не нашли, пытаемся парсить значение panicstring как JSON
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

            # Шаг 1.3: Fallback - ищем старым Regex в сыром тексте лога
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
            # Берем исходное значение, очистка будет применена перед генерацией ключа/возвратом
            panic_string_value = ""
            if 'panicstring' in log_dict_cleaned_keys:
                 panic_string_value = str(log_dict_cleaned_keys['panicstring'] or "")
                 logging.info(f"Извлечено ИСХОДНОЕ значение panicString из словаря: {panic_string_value[:100]}...")
            elif self.log:
                 panic_string_value = self.log
                 logging.warning("panicString не найден в словаре, используется весь текст лога.")
            
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
            
            # Возвращаем ИСХОДНОЕ значение panic_string_value, т.к. очистка для поиска решения не нужна
            # Очищенное значение использовалось только для генерации ключа и парсинга JSON
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

    async def find_error_solutions(self):
        # 1. Проверка наличия данных
        if not self.panic_sheet and not self.nand_sheet:
            logging.error("Оба файла Excel (panic_codes, nand_list) не загружены! Поиск невозможен.")
            # Возвращаем ошибку отсутствия БД
            return [{"solutions": ["Невозможно найти решение - файлы базы знаний отсутствуют."], "is_full": False}]
            
        if not self.log_dict:
            logging.warning("log_dict пуст! Невозможно выполнить анализ.")
            return [{"solutions": ["Невозможно найти решение - ошибка анализа файла."], "is_full": False}]

        # 2. Извлечение информации (product и panic_string)
        product, _, panic_string = self.extract_product_info()
        product_cleaned = product.lower().strip().replace(" ", "") # Очищенное имя модели для поиска в Excel
        original_product_name = product if product != "Неизвестно" else None # Исходное имя для ответа

        if not product_cleaned or product_cleaned == "неизвестно":
             logging.warning(f"Не удалось извлечь 'product' для поиска в Excel...")
             # Используем ключ, который обработчик поймет как "модель неизвестна"
             return [{"solutions": [SOLUTION_NOT_FOUND_DETAILED_KEY], "model": ["Неизвестно"], "is_full": False}]

        if not panic_string:
            logging.warning("Отсутствует или пустой panicString.")
            return [{"solutions": ["Невозможно найти решение - не удалось извлечь текст ошибки (panic string)."], "is_full": False}]

        # 3. Получение ключевой строки ошибки от ИИ
        search_string_from_ai = ""
        try:
            logging.info(f"Запрос к ИИ для извлечения ключевой ошибки из panic_string (длина: {len(panic_string)}), язык: {self.lang}")
            ai_response = await analyze_file_with_ai(panic_string, language=self.lang)
            logging.info(f"Получена строка от ИИ для поиска: '{ai_response}'")

            if ai_response and not ai_response.startswith("Ошибка:") and not ai_response.startswith("Error:"):
                search_string_from_ai = ai_response # Используем ответ ИИ как строку для поиска
            else:
                # Если ИИ вернул ошибку, логируем и пытаемся искать по исходному panic_string
                logging.error(f"ИИ не смог извлечь ключевую строку, вернул ошибку: {ai_response}. Попытка поиска по полному panic_string.")
                # Очищаем исходный panic_string для поиска (как делали раньше)
                cleaned_panic_string_fallback = panic_string
                if panic_string and (re.search(r'\b[a-zA-Z] [a-zA-Z]\b', panic_string) or re.search(r'" : "', panic_string)):
                    cleaned_panic_string_fallback = re.sub(r'\s+(?=[^a-zA-Z0-9\s])|(?<=[^a-zA-Z0-9\s])\s+', '', panic_string)
                    cleaned_panic_string_fallback = re.sub(r'(?!\w)\s+(?=\w)|(?<=\w)\s+(?!\w)', '', cleaned_panic_string_fallback)
                    cleaned_panic_string_fallback = ' '.join(cleaned_panic_string_fallback.split())
                search_string_from_ai = cleaned_panic_string_fallback

        except Exception as e:
            logging.error(f"Ошибка при вызове ИИ для извлечения ключевой строки: {e}. Попытка поиска по полному panic_string.", exc_info=True)
            # Как fallback, используем очищенный panic_string
            cleaned_panic_string_fallback = panic_string
            if panic_string and (re.search(r'\b[a-zA-Z] [a-zA-Z]\b', panic_string) or re.search(r'" : "', panic_string)):
                 cleaned_panic_string_fallback = re.sub(r'\s+(?=[^a-zA-Z0-9\s])|(?<=[^a-zA-Z0-9\s])\s+', '', panic_string)
                 cleaned_panic_string_fallback = re.sub(r'(?!\w)\s+(?=\w)|(?<=\w)\s+(?!\w)', '', cleaned_panic_string_fallback)
                 cleaned_panic_string_fallback = ' '.join(cleaned_panic_string_fallback.split())
            search_string_from_ai = cleaned_panic_string_fallback

        if not search_string_from_ai:
             logging.warning("Строка для поиска в Excel пуста (ИИ не ответил, fallback тоже пуст). Поиск невозможен.")
             # Возвращаем ключ "не найдено"
             return [{"solutions": [SOLUTION_NOT_FOUND_DETAILED_KEY], "model": [original_product_name or "Неизвестно"], "is_full": False}]

        # 4. Поиск полученной строки (или fallback) в Excel
        logging.info(f"Поиск строки '{search_string_from_ai[:100]}...' в Excel для модели '{product_cleaned}'.")
        all_found_solutions = []
        if self.panic_sheet:
             logging.info(f"Поиск в panic_codes.xlsx...")
             panic_solutions = self._search_in_sheet(self.panic_sheet, product_cleaned, search_string_from_ai)
             all_found_solutions.extend(panic_solutions)

        if self.nand_sheet:
             logging.info(f"Поиск в nand_list.xlsx...")
             nand_solutions = self._search_in_sheet(self.nand_sheet, product_cleaned, search_string_from_ai)
             all_found_solutions.extend(nand_solutions)

        # 5. Выбор и возврат результата
        if not all_found_solutions:
            logging.info(f"Решение не найдено в Excel для строки '{search_string_from_ai[:100]}...' и модели '{product_cleaned}'.")
            return [{"solutions": [SOLUTION_NOT_FOUND_DETAILED_KEY], "model": [original_product_name or "Неизвестно"], "is_full": False}]

        logging.info(f"Найдено {len(all_found_solutions)} потенциальных совпадений в Excel. Выбираем лучшее.")

        # --- Простая Приоритетизация: выбираем самое длинное совпадение кода --- 
        # (Можно вернуть старую логику приоритезации по panic_core_message, если нужно)
        final_solution = max(all_found_solutions, key=lambda sol: len(sol.get("matched_code", "")))
        logging.info(f"Выбрано самое длинное совпадение из Excel (код: '{final_solution.get('matched_code')}').")

        # Добавляем модель к финальному решению перед возвратом
        final_solution["model"] = [original_product_name or "Неизвестно"]
        return [final_solution]

    # --- Восстановлен метод _search_in_sheet --- 
    def _search_in_sheet(self, sheet, product_key, search_string):
        """Ищет ВСЕ совпадения ПОДСТРОКИ error_code из Excel в search_string."""
        if not sheet:
            return []
        if not search_string:
             return []
        if not product_key or product_key == "неизвестно":
            return []
            
        model_column_index = None
        try:
            header_row = sheet[2]
        except IndexError:
             logging.warning(f"Не удалось прочитать строку заголовков (индекс 2) в листе '{sheet.title}'")
             return []

        available_platforms = []
        for cell in header_row:
            if cell.value:
                platform_id = str(cell.value).lower().strip().replace(" ", "")
                available_platforms.append(platform_id)
                if platform_id == product_key:
                    model_column_index = cell.column
                    logging.info(f"Найден столбец для модели '{product_key}' (столбец {get_column_letter(model_column_index)}) в листе '{sheet.title}'")
                    break
        
        if model_column_index is None:
            logging.warning(f"Столбец для модели '{product_key}' не найден в листе '{sheet.title}'. Доступные: {available_platforms}")
            return []

        found_solutions = []
        search_string_lower = search_string.lower()
        try:
             for row_index in range(3, sheet.max_row + 1):
                 error_code_cell = sheet.cell(row=row_index, column=1).value
                 solution_cell = sheet.cell(row=row_index, column=model_column_index).value

                 if not error_code_cell:
                     continue
                 error_code = str(error_code_cell).strip()
                 if not error_code:
                continue
                
                 # --- Ищем код ошибки из Excel (error_code) как ПОДСТРОКУ в строке поиска (search_string) --- 
                 if error_code.lower() in search_string_lower:
                     logging.info(f"Найдено ВХОЖДЕНИЕ ПОДСТРОКИ! Код '{error_code}' из Excel найден в строке поиска '{search_string[:50]}...'")
                     solution_text = str(solution_cell or "").strip()
                     if solution_text:
                          solution_data = {
                              "solutions": [solution_text],
                              "is_full": True,
                              "matched_code": error_code # Сохраняем код из Excel, который совпал
                          }
                          found_solutions.append(solution_data)
                     else:
                         logging.warning(f"Найден код '{error_code}', но текст решения пуст (строка {row_index}, лист '{sheet.title}')")

        except Exception as e:
            logging.error(f"Ошибка при итерации по строкам листа '{sheet.title}': {e}", exc_info=True)
            return found_solutions # Возвращаем то, что успели найти

        if found_solutions:
             logging.info(f"Найдено {len(found_solutions)} решений для '{product_key}' в листе '{sheet.title}' по строке поиска.")
                else:
             logging.info(f"Совпадений кодов ошибок в строке поиска не найдено для '{product_key}' в листе '{sheet.title}'.")
        
        return found_solutions