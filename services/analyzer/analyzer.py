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
        try:
            workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
            self.sheet = workbook[lang]
        except Exception as e:
            logging.error(f"Ошибка загрузки таблицы кодов паники: {e}")
            self.sheet = None
            
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
                
                # Если log_dict пуст или не содержит panicString, используем весь текст как panicString
                if not self.log_dict or not self.log_dict.get("panicString"):
                    self.log_dict = self.log_dict or {}
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
        try:
            model = (
                self.log_dict.get("product") or
                self.log_dict.get("header", {}).get("product") or
                self.log_dict.get("model") or
                "Неизвестно"
            )

            crash_key = (
                self.log_dict.get("crashReporterKey") or
                hashlib.md5(self.log.encode()).hexdigest()
            )

            panic_string = self.log

            return model.strip(), crash_key, panic_string
        except Exception as e:
            logging.error(f"extract_product_info: {e}", exc_info=True)
            return "Неизвестно", None, self.log


    def find_error_solutions(self):
        if not self.sheet:
            logging.warning("Таблица кодов отсутствует! Невозможно выполнить анализ.")
            return [{"solutions": ["Невозможно найти решение - таблица кодов отсутствует."], "is_full": False}]
            
        if not self.log_dict:
            logging.warning("log_dict пуст! Невозможно выполнить анализ.")
            return [{"solutions": ["Невозможно найти решение - ошибка анализа файла."], "is_full": False}]

        product = self.log_dict.get("product", "").lower().replace(" ", "")
        panic_string = self.log_dict.get("panicString", "")

        if not panic_string and self.log:
            # ксли panicString не найден, используем весь лог
            panic_string = self.log

        if not panic_string:
            logging.warning("Отсутствует поле `panicString`.")
            return [{"solutions": ["Невозможно найти решение - в файле не найдена информация об ошибке."], "is_full": False}]

        solutions = self._search_solutions_in_xlsx(product, panic_string)
        
        # ксли не нашли по модели, попробуем поискать по common решениям
        if not solutions and product != "common":
            solutions = self._search_solutions_in_xlsx("common", panic_string)
            
        return solutions if solutions else [{"solutions": ["Решение не найдено. Рекомендуется обратиться в службу поддержки."], "is_full": False}]

    def _search_solutions_in_xlsx(self, product, panic_string):
        if not self.sheet:
            return []
            
        # сначала ищем колонку для указанной модели
        model_column = None
        for cell in self.sheet[2]:  # Предполагаем, что названия моделей во второй строке
            if cell.value and isinstance(cell.value, str) and cell.value.lower().replace(" ", "") == product:
                model_column = cell.column
                break
        
        # если не нашли модель, ищем common решения
        if model_column is None and product != "common":
            for cell in self.sheet[2]:
                if cell.value and isinstance(cell.value, str) and "common" in cell.value.lower():
                    model_column = cell.column
                    break
        
        if model_column is None:
            return []

        solutions = []
        # проходим по всем строкам и ищем соответствие кода ошибки
        for row in range(3, self.sheet.max_row + 1):  # начинаем с 3-й строки, т.к. первые две - заголовки
            error_code = self.sheet.cell(row=row, column=1).value
            solution = self.sheet.cell(row=row, column=model_column).value
            
            if not error_code or not solution:
                continue
                
            error_code = str(error_code).replace('"', '')
            if re.search(re.escape(error_code), panic_string, re.IGNORECASE):
                if isinstance(solution, str):
                    solutions.append({"solutions": [solution], "is_full": True})
                else:
                    solutions.append({"solutions": [str(solution)], "is_full": True})
        
        return solutions