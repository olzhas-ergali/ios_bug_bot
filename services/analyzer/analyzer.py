import io
import json
import re
import logging
import os
import hashlib
import openpyxl
from chardet import detect
from openpyxl.utils import get_column_letter
from PIL import Image
import pytesseract

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
        
        # Загружаем panic_codes.xlsx
        try:
            panic_workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
            # Пытаемся получить лист по языку, если нет - берем активный
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
            # Предполагаем ту же логику для листов (по языку или активный)
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
                json_candidate = preprocess_log_content(self.log)
                if isinstance(json_candidate, dict):
                    self.log_dict = json_candidate
                else:
                    self.log_dict = fix_json_structure(json_candidate)
                
                if not self.log_dict or not self.log_dict.get("panicString"):
                    self.log_dict = self.log_dict or {}
                    # Пытаемся извлечь panicString при инициализации, чтобы он был доступен
                    _, _, extracted_panic = self.extract_product_info() # Вызываем extract для заполнения
                    # Не перезаписываем, если extract_product_info уже что-то нашел и записал
                    if "panicString" not in self.log_dict and extracted_panic:
                         self.log_dict["panicString"] = extracted_panic
                    elif "panicString" not in self.log_dict: # Если и extract не нашел
                         self.log_dict["panicString"] = self.log # Используем весь лог

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

    def find_error_solutions(self):
        # Проверяем наличие хотя бы одного файла
        if not self.panic_sheet and not self.nand_sheet:
            logging.error("Оба файла Excel (panic_codes, nand_list) не загружены! Поиск невозможен.")
            return [{"solutions": ["Невозможно найти решение - файлы базы знаний отсутствуют."], "is_full": False}]
            
        if not self.log_dict:
            logging.warning("log_dict пуст! Невозможно выполнить анализ.")
            return [{"solutions": ["Невозможно найти решение - ошибка анализа файла."], "is_full": False}]

        product, _, panic_string = self.extract_product_info()
        product_cleaned = product.lower().strip().replace(" ", "")
        original_product_name = product if product != "Неизвестно" else None 

        if not product_cleaned or product_cleaned == "неизвестно":
             logging.warning(f"Не удалось извлечь 'product'...")
             # Возвращаем структуру для нового сообщения об ошибке (модель неизвестна)
             return [{"solutions": ["solution_not_found_detailed"], "model": ["Неизвестно"], "is_full": False}]

        # Очищаем panic_string для поиска
        cleaned_panic_string_for_search = panic_string
        if panic_string and (re.search(r'\b[a-zA-Z] [a-zA-Z]\b', panic_string) or re.search(r'" : "', panic_string)):
            logging.info("Обнаружены пробелы в panicString, применяем очистку перед поиском...")
            original_length = len(panic_string)
            cleaned_panic_string_for_search = re.sub(r'\s+(?=[^a-zA-Z0-9\s])|(?<=[^a-zA-Z0-9\s])\s+', '', panic_string)
            cleaned_panic_string_for_search = re.sub(r'(?!\w)\s+(?=\w)|(?<=\w)\s+(?!\w)', '', cleaned_panic_string_for_search) 
            cleaned_panic_string_for_search = ' '.join(cleaned_panic_string_for_search.split())
            logging.info(f"Очищенный panicString для поиска (было {original_length}, стало {len(cleaned_panic_string_for_search)}): {cleaned_panic_string_for_search[:200]}...")
        elif not panic_string:
            logging.warning("Отсутствует или пустой panicString для поиска решения.")
            return [{"solutions": ["Невозможно найти решение - не удалось извлечь текст ошибки (panic string)."], "is_full": False}]
        else:
             logging.info("Пробелы в panicString не обнаружены или он пуст, очистка перед поиском не применялась.")

        # --- Поиск ВСЕХ совпадений во всех файлах --- 
        all_found_solutions = []
        if self.panic_sheet:
             logging.info(f"Поиск ВСЕХ совпадений для '{product_cleaned}' в panic_codes.xlsx...")
             panic_solutions = self._search_in_sheet(self.panic_sheet, product_cleaned, cleaned_panic_string_for_search)
             all_found_solutions.extend(panic_solutions)
        
        if self.nand_sheet:
             # Ищем в nand_list только если в panic_codes ничего не нашли?
             # Нет, давайте соберем из обоих и потом приоритезируем.
             logging.info(f"Поиск ВСЕХ совпадений для '{product_cleaned}' в nand_list.xlsx...")
             nand_solutions = self._search_in_sheet(self.nand_sheet, product_cleaned, cleaned_panic_string_for_search)
             all_found_solutions.extend(nand_solutions)

        if not all_found_solutions:
            logging.info(f"Решение не найдено ни в одном файле Excel для модели '{product_cleaned}'.")
            return [{"solutions": ["solution_not_found_detailed"], "model": [original_product_name or "Неизвестно"], "is_full": False}]
        
        logging.info(f"Найдено всего {len(all_found_solutions)} потенциальных совпадений. Выбор самого длинного/специфичного...")
        
        # --- НОВАЯ ЛОГИКА ВЫБОРА: по максимальной длине совпавшего кода --- 
        final_solution = None
        
        if len(all_found_solutions) == 1:
            # Если найдено только одно совпадение, берем его
            final_solution = all_found_solutions[0]
            logging.info(f"Найдено одно совпадение. Выбрано решение (код: '{final_solution.get('matched_code')}').")
        else:
            # Если найдено несколько, выбираем по самому длинному matched_code
            final_solution = max(all_found_solutions, key=lambda sol: len(sol.get("matched_code", "")))
            logging.info(f"Найдено несколько совпадений. Выбрано решение с самым длинным кодом: '{final_solution.get('matched_code')} ({len(final_solution.get('matched_code',''))} символов).")

        # Возвращаем только одно выбранное решение в виде списка
        return [final_solution]

    def _search_in_sheet(self, sheet, product_key, panic_string_cleaned):
        """Ищет ВСЕ ТОЧНЫЕ совпадения (границы слова) для product_key в ОЧИЩЕННОМ panic_string."""
        if not sheet:
            return []
        if not panic_string_cleaned:
             return []
        if not product_key or product_key == "неизвестно":
            return []
            
        model_column_index = None
        try:
            header_row = sheet[2] 
        except IndexError:
             return []
             
        available_platforms = []
        for cell in header_row:
            if cell.value:
                platform_id = str(cell.value).lower().strip().replace(" ", "")
                available_platforms.append(platform_id)
                if platform_id == product_key:
                    model_column_index = cell.column
                    break
        
        if model_column_index is None:
            return []

        found_solutions = []
        panic_string_lower = panic_string_cleaned.lower()
        try:
             # Итерирует по строкам, начиная с 3-й до последней.
             for row_index in range(3, sheet.max_row + 1):
                 # Получает значение ячейки с кодом ошибки (колонка 1, т.е. 'A').
                 error_code_cell = sheet.cell(row=row_index, column=1).value
                 # Получает значение ячейки с решением (колонка найденной модели).
                 solution_cell = sheet.cell(row=row_index, column=model_column_index).value
            
                 # Если ячейка с кодом ошибки пустая, пропускает строку.
                 if not error_code_cell:
                     continue
                 # Преобразует код ошибки в строку, удаляет пробелы по краям.
                 error_code = str(error_code_cell).strip()
                 # Если код ошибки стал пустым, пропускает строку.
                 if not error_code:
                     continue
                
                 # --- ВОЗВРАЩАЕМ ТОЧНЫЙ ПОИСК ПО ГРАНИЦАМ СЛОВА (\b) ---
                 try:
                     # Ищем ТОЧНОЕ СЛОВО/КОД (с учетом регистра) с границами \b
                     # Используем re.escape для безопасности, если код содержит спецсимволы regex
                     if re.search(r'\b' + re.escape(error_code) + r'\b', panic_string_cleaned, re.IGNORECASE):
                         logging.info(f"Найдено ТОЧНОЕ совпадение (границы слова)! Код '{error_code}' ... найден в ОЧИЩЕННОМ panic_string.")
                         solution_text = str(solution_cell or "").strip()
                         if solution_text:
                              solution_data = {
                                  "solutions": [solution_text],
                                  "is_full": True,
                                  "matched_code": error_code
                              }
                              found_solutions.append(solution_data)
                 except re.error as e:
                     logging.error(f"Ошибка regex при точном поиске кода '{error_code}': {e}")
                     # Устанавливаем правильный отступ для continue
                     continue 
        except Exception as e:
            # ...логирует ошибку с трассировкой.
            logging.error(f"Ошибка при итерации по строкам листа '{sheet.title}': {e}", exc_info=True)
            # Возвращаем то, что успели найти до ошибки.
            return found_solutions

        # Если найдены какие-либо решения в этом листе...
        if found_solutions:
             # ...логирует количество найденных решений.
             logging.info(f"Найдено {len(found_solutions)} решений для '{product_key}' в листе '{sheet.title}'")
        else:
             # ...логирует, что совпадений нет.
             logging.info(f"Совпадений кодов ошибок в panic_string не найдено для '{product_key}' в листе '{sheet.title}'.")
        
        # Возвращаем список ВСЕХ найденных решений (словарей) для этого листа.
        return found_solutions # Возвращаем ВЕСЬ список