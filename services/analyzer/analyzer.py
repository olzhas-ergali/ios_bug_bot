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
# import google.generativeai as genai # Убрано
from google.api_core import exceptions as google_exceptions # Оставляем для возможных будущих ошибок
# import openai # Убрано, клиент OpenAI больше не нужен здесь
from datetime import datetime

# --- Функция для очистки строк с пробелами (перенесена сюда) ---
def clean_spaced_string(s):
    return re.sub(r"\s+", "", s)

# --- Улучшенная функция безопасного парсинга JSON ---
def parse_json_safely(text):
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        try:
            # Try to dump non-string input to string first
            text = json.dumps(text)
        except Exception:
            logging.error("Failed to convert non-string input to JSON string in parse_json_safely.")
            return {"panicString": str(text)} # Return original as string value

    merged_data = {}
    found_json = False
    # Regex to find {...} pairs, handling nested braces and basic string escaping
    # This regex is basic and might fail on complex nested structures or escaped braces within strings.
    json_candidates = re.findall(r'(\{((?:[^{}]|\{[^{}]*\}|\"(?:\\.|[^\\"])*\")*)\})', text)

    logging.info(f"Found {len(json_candidates)} potential JSON objects in parse_json_safely.")

    for candidate_tuple in json_candidates:
        candidate_str = candidate_tuple[0] # The full match including outer braces
        try:
            # Attempt to remove potential trailing commas before closing brace/bracket
            candidate_str_fixed = re.sub(r'\s*,(\s*[}\]])', r'\1', candidate_str)
            data = json.loads(candidate_str_fixed)
            if isinstance(data, dict):
                merged_data.update(data) # Merge dictionaries, later keys overwrite earlier ones
                found_json = True
                logging.info(f"Successfully parsed and merged JSON object: {list(data.keys())[:5]}...") # Log first few keys
            else:
                logging.warning(f"Parsed JSON candidate is not a dictionary: {type(data)}")
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse JSON candidate in parse_json_safely: {e}. Candidate start: {candidate_str[:100]}...")
        except Exception as e:
            logging.error(f"Unexpected error parsing JSON candidate in parse_json_safely: {e}")

    if found_json:
            logging.info("Successfully merged one or more JSON objects.")
            # Ensure panicString is present, using the raw text as fallback if needed
            # Check case-insensitively
            has_panic_key = any(key.lower() == 'panicstring' for key in merged_data.keys())
            if not has_panic_key:
                logging.warning("Merged JSON does not contain 'panicString'. Adding raw text as fallback.")
                merged_data['panicString'] = text # Add the original text if key is missing
            return merged_data
    else:
            logging.warning("Could not parse any valid JSON object. Falling back to structured data or raw text.")
            # Fallback: try parsing line by line as key-value
            try:
                structured_data = {}
                lines = text.splitlines()
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip()
                        value = parts[1].strip()
                        # Basic validation to avoid adding noise
                        if key and value and len(key) < 100 and not key.startswith(" "):
                            structured_data[key] = value
                if structured_data:
                    logging.info("Fallback successful: Parsed key-value pairs.")
                    # Ensure panicString is present (case-insensitive check)
                    has_panic_key = any(key.lower() == 'panicstring' for key in structured_data.keys())
                    if not has_panic_key:
                        structured_data['panicString'] = text
                    return structured_data
                else:
                    logging.warning("Fallback failed: No key-value pairs found. Returning raw text.")
                    return {"panicString": text}
            except Exception as e:
                logging.error(f"Error in key-value fallback parsing: {e}")
                return {"panicString": text}

# --- СПИСОК ИЗВЕСТНЫХ КОДОВ ОШИБОК (ОБНОВЛЕННЫЙ) ---
KNOWN_ERROR_CODES = [
    "apcie[0:s3e]",
    "nvme", # Добавлено
    "ANS2 Recoverable Panic",
    "ANS2 DATA ABORT",
    "bluetooth-pcie mini", # Добавлено
    "bluetooth-pcie", # Добавлено
    "AppleBCMWLAN mini", # Добавлено
    "AppleBCMWLAN",
    "apcie[0:wlan] mini", # Добавлено
    "apcie[0:wlan]",
    "apcie[1:wlan] mini", # Добавлено
    "apcie[1:wlan]",
    "apcie[2:wlan] mini", # Добавлено
    "apcie[2:wlan]",
    "apcie[3:wlan] mini", # Добавлено
    "apcie[3:wlan]",
    "AppleBaseband mini", # Добавлено
    "AppleBaseband",
    "baseband-pcie mini", # Добавлено
    "baseband-pcie",
    "AppleCS42L75Audio mini", # Добавлено
    "AppleCS42L75Audio",
    "AppleCS42L77Audio mini", # Добавлено
    "AppleCS42L77Audio",
    "SEP Memory Protection Module error mini", # Добавлено
    "SEP Memory Protection Module error",
    "AppleOLYHAL mini", # Добавлено
    "AppleOLYHAL", # Добавлено
    "AppleOLYHALPortInterfacePCIe mini", # Добавлено
    "AppleOLYHALPortInterfacePCIe",
    "port enable failed: mini", # Добавлено
    "port enable failed:",
    "ApplePMGR",
    "BMSTask", # Добавлено
    "Missing sensor(s): TG0B mini", # Добавлено
    "Missing sensor(s): TG0B",
    "0x0, 0x400, mini", # Добавлено
    "0x0, 0x400,",
    "0x0, 0x800,",
    "0x0, 0x1000,",
    "0x0, 0x1800,",
    "0x0, 0x4000,",
    "0x0, 0x4800,", # Добавлено
    "0x0, 0x5000,", # Добавлено
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
    "0x0, 0x600000,", # Добавлено
    "0x0, 0x700000,", # Добавлено
    "0x0, 0x40000000,",
    "0xa1, 0x0,",
    "0x41, 0x0",
    "0x0, 0xc0000,",
    "0x0, 0x1c0000,",
    "is 169", # Добавлено
    "524288", # Добавлено
    "1048576", # Добавлено
    "1572864", # Добавлено
    "2097152", # Добавлено
    "2621440", # Добавлено
    "3145728", # Добавлено
    "3670016", # Добавлено
    "4194304", # Добавлено
    "AOP PANIC - [Eiger",
    "AOP PANIC - SCMto:0 - prox mini", # Добавлено
    "AOP PANIC - SCMto:0 - prox",
    "AOP PANIC - SCMto:1 - prox mini", # Добавлено
    "AOP PANIC - SCMto:1 - prox",
    "Meru", # Добавлено
    "nEiger", # Добавлено
    "AOP PANIC - No pulse on",
    "AOP PANIC - moly: bad data",
    "AOP PANIC - !pulse pearl@",
    "AOP PANIC - !pulse main@",
    "Pressure queue blocked", # Добавлено
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
    "AOP PREFETCH ABORT", # Добавлено
    "AMCC PLANE2 MCC", # Добавлено
    "AMCC PLANE0 MCC", # Добавлено
    "AppleSocHot: Hot Hot Hot",
    "AOP PANIC - SCMErr:0x0",
    "AOP PANIC - SCMto:",
    "aop-spmi0",
    "aop-spmi1",
    "@PIODMA",
    "for device display-eeprom",
    "for device roswell",
    "@AppleSynopsysMIPIDSIController",
    "apt firmware", # Добавлено
    "IOMFB", # Добавлено
    "IOMFB int_handler",
    "Can't find valid timing element for display",
    "DCP PANIC - ASSERT",
    "DCP PANIC - EDP aggressor table mismatch!",
    "iomfb_ap_callee_0",
    "iomfb_bic_proc_async",
    "DCP PANIC - IOMFB",
    "MTP DATA ABORT",
    "MTP PANIC",
    "SIGNAL, code 6", # Убрано \nservice:
    "userspace watchdog timeout: no successful checkins from SpringBoard",
    "userspace watchdog timeout: no successful checkins from wifid since wake",
    "userspace watchdog timeout: no successful checkins from logd in 180",
    "userspace watchdog timeout: no successful checkins from backboardd", # Добавлено
    "Port-Lightning",
    "AppleKraken:",
    "AppleHydra:",
    "AppleTriStar2",
    "smc-charger",
    "smc-orion-charger", # Добавлено
    "i2c0",
    "i2c1",
    "i2c2",
    "i2c3" # Добавлено
]
KNOWN_ERROR_CODES_LOWER = {code.lower() for code in KNOWN_ERROR_CODES} # Для быстрой проверки ответа ИИ

# --- СЛОВАРЬ ИДЕНТИФИКАТОРОВ МОДЕЛЕЙ ---
KNOWN_MODEL_IDENTIFIERS = {
    "iphone17,2": "iPhone 16 Pro Max",
    "iphone17,1": "iPhone 16 Pro",
    "iphone17,4": "iPhone 16 Plus",
    "iphone17,3": "iPhone 16",
    "iphone16,2": "iPhone 15 Pro Max",
    "iphone16,1": "iPhone 15 Pro",
    "iphone15,5": "iPhone 15 Plus",
    "iphone15,4": "iPhone 15",
    "iphone15,3": "iPhone 14 Pro Max",
    "iphone15,2": "iPhone 14 Pro",
    "iphone14,8": "iPhone 14 Plus",
    "iphone14,7": "iPhone 14",
    "iphone14,6": "iPhone SE (3-го поколения)",
    "iphone14,3": "iPhone 13 Pro Max",
    "iphone14,2": "iPhone 13 Pro",
    "iphone14,5": "iPhone 13",
    "iphone14,4": "iPhone 13 mini",
    "iphone13,4": "iPhone 12 Pro Max",
    "iphone13,3": "iPhone 12 Pro",
    "iphone13,2": "iPhone 12",
    "iphone13,1": "iPhone 12 mini",
    "iphone12,5": "iPhone 11 Pro Max",
    "iphone12,3": "iPhone 11 Pro",
    "iphone12,8": "iPhone SE (2-го поколения)",
    "iphone12,1": "iPhone 11",
    "iphone11,6": "iPhone Xs Max",
    "iphone11,4": "iPhone Xs Max (China)",
    "iphone11,2": "iPhone Xs",
    "iphone11,8": "iPhone XR",
    "iphone10,3": "iPhone X (Global)",
    "iphone10,6": "iPhone X (GSM)",
    "iphone10,5": "iPhone 8 Plus (GSM)",
    "iphone10,2": "iPhone 8 Plus (Global)",
    "iphone10,4": "iPhone 8 (GSM)",
    "iphone10,1": "iPhone 8 (Global)",
    "iphone9,4": "iPhone 7 Plus (GSM)",
    "iphone9,2": "iPhone 7 Plus (Global)",
    "iphone9,3": "iPhone 7 (GSM)",
    "iphone9,1": "iPhone 7 (Global)",
    "iphone8,2": "iPhone 6s Plus",
    "iphone8,1": "iPhone 6s",
    "iphone8,4": "iPhone SE (1-го поколения)",
    "ipad4,1": "iPad Air (WiFi)",
    "ipad4,2": "iPad Air (Cellular)",
    "ipad4,3": "iPad Air (China)",
    "ipad4,6": "iPad mini 2 (China)",
    "ipad4,7": "iPad mini 3 (WiFi)",
    "ipad4,8": "iPad mini 3 (Cellular)",
    "ipad4,9": "iPad mini 3 (China)",
    "ipad5,3": "iPad Air 2 (WiFi)",
    "ipad5,4": "iPad Air 2 (Cellular)",
    "ipad5,1": "iPad mini 4 (WiFi)",
    "ipad5,2": "iPad mini 4 (Cellular)",
    "ipad6,7": "iPad Pro 12.9-inch (WiFi)",
    "ipad6,8": "iPad Pro 12.9-inch (Cellular)",
    "ipad6,4": "iPad Pro 9.7-inch (Cellular)",
    "ipad6,3": "iPad Pro 9.7-inch (WiFi)",
    "ipad6,11": "iPad 5 (WiFi)",
    "ipad6,12": "iPad 5 (Cellular)",
    "ipad7,2": "iPad Pro 2 (12.9-inch, Cellular)",
    "ipad7,4": "iPad Pro (10.5-inch, Cellular)",
    "ipad7,3": "iPad Pro (10.5-inch, WiFi)",
    "ipad7,1": "iPad Pro 2 (12.9-inch, WiFi)",
    "ipad14,3": "iPad Pro (11-inch, WiFi) (4th generation)"
}
# --- Конец словаря ---

# --- Конец списков ---

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class LogAnalyzer:
    # Simplified __init__ to only load Excel sheets based on language
    def __init__(self, lang):
        self.panic_sheet = None
        self.nand_sheet = None
        self.lang = lang
        logging.info(f"Initializing LogAnalyzer for language: {lang}")

        # Load panic_codes.xlsx
        try:
            panic_workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
            try:
                 self.panic_sheet = panic_workbook[lang]
                 logging.info(f"Loaded sheet '{lang}' from panic_codes.xlsx")
            except KeyError:
                 # Fallback to active sheet if language sheet not found
                 self.panic_sheet = panic_workbook.active
                 logging.warning(f"Sheet '{lang}' not found in panic_codes.xlsx, using active sheet: '{self.panic_sheet.title}'")
        except FileNotFoundError:
            logging.error("File ./data/panic_codes.xlsx not found!")
        except Exception as e:
            logging.error(f"Error loading panic_codes.xlsx: {e}")

        # Load nand_list.xlsx - Assuming single sheet with language columns
        try:
            nand_workbook = openpyxl.load_workbook("./data/nand_list.xlsx")
            # Use the active sheet as there's only one relevant sheet expected
            self.nand_sheet = nand_workbook.active
            logging.info(f"Loaded active sheet '{self.nand_sheet.title}' from nand_list.xlsx")
        except FileNotFoundError:
            logging.warning("File ./data/nand_list.xlsx not found! NAND info search will not be possible.")
            self.nand_sheet = None # Ensure nand_sheet is None if file not found
        except Exception as e:
            logging.error(f"Error loading nand_list.xlsx: {e}")
            self.nand_sheet = None # Ensure nand_sheet is None on other errors

    # Keep _read_log_file as a static method
    @staticmethod
    def _read_log_file(path):
        """Reads a file with automatic encoding detection"""
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

    # Keep _read_photo as a static method
    @staticmethod
    def _read_photo(path, tesseract_path):
        """Processes an image file using Tesseract OCR"""
        try:
            img = Image.open(path)
            if tesseract_path:
                pytesseract.tesseract_cmd = tesseract_path
            return pytesseract.image_to_string(img, lang='eng')
        except Exception as e:
            logging.error(f"Ошибка обработки изображения {path}: {e}")
            return ""

    # Keep _find_solution_by_code to search Excel sheets
    def _find_solution_by_code(self, sheet, product_key, error_code_to_find):
        """
        Searches for an exact match of error_code_to_find in column 'A' of the sheet
        and returns the solution for the given product_key.
        Returns only the solution text or None.
        """
        if not sheet:
            logging.warning(f"_find_solution_by_code: Sheet is None, cannot search.")
            return None
        if not product_key or product_key.lower() == "неизвестно":
            logging.warning(f"_find_solution_by_code: Invalid product_key ('{product_key}'), cannot search.")
            return None
        if not error_code_to_find:
            logging.warning(f"_find_solution_by_code: error_code_to_find is empty or None, cannot search.")
            return None

        model_column_index = None
        try:
            # Assuming model headers are in the second row
            header_row = sheet[2]
        except IndexError:
            logging.error(f"Could not read header row (2) in sheet '{sheet.title}'")
            return None

        # Find the column index for our model identifier
        product_key_cleaned = clean_spaced_string(str(product_key).lower())
        for cell in header_row:
            if cell.value:
                platform_id_in_sheet = clean_spaced_string(str(cell.value).lower())
                if platform_id_in_sheet == product_key_cleaned:
                    model_column_index = cell.column
                    logging.info(f"Found column {get_column_letter(model_column_index)} for model '{product_key}' in sheet '{sheet.title}'.")
                    break
        
        if model_column_index is None:
            logging.warning(f"Column for model '{product_key}' (cleaned key: '{product_key_cleaned}') not found in sheet '{sheet.title}'.")
            return None

        # Search for the error code in column 'A' (starting from row 3)
        logging.info(f"Searching for code '{error_code_to_find}' in column 'A' of sheet '{sheet.title}'...")
        found_solution_text = None
        error_code_lower = error_code_to_find.lower()

        for row_index in range(3, sheet.max_row + 1):
            error_code_cell = sheet.cell(row=row_index, column=1).value
            if not error_code_cell:
                continue
                
            error_code_in_sheet = str(error_code_cell).strip().lower()
            # Case-insensitive comparison
            if error_code_in_sheet == error_code_lower:
                solution_cell = sheet.cell(row=row_index, column=model_column_index).value
                solution_text = str(solution_cell or "").strip()
                if solution_text:
                    logging.info(f"Found exact match for code '{error_code_to_find}' in row {row_index}. Solution found.")
                    found_solution_text = solution_text
                    break # Found the first non-empty solution, exit loop
                else:
                    # Found the code, but the cell for this model is empty. Continue searching just in case?
                    # For exact match, we should probably stop, but logging helps.
                    logging.warning(f"Found code '{error_code_to_find}' in row {row_index}, but solution cell for model '{product_key}' is empty. Stopping search for this code.")
                    # If multiple rows could have the same code, we might want to continue search.
                    # For now, assume first match (even if empty) is definitive for this code.
                    break # Stop searching once the code is found, even if solution is empty

        if found_solution_text:
            logging.info(f"Returning solution for code '{error_code_to_find}' and model '{product_key}'.")
        else:
            # This log includes cases where code was found but solution was empty, or code not found at all
            logging.info(f"Solution not found for code '{error_code_to_find}' and model '{product_key}' in sheet '{sheet.title}'.")

        return found_solution_text # Returns the solution text or None

    # --- New method for NAND lookup ---
    def _find_nand_info_by_model(self, nand_model_to_find, lang='ru'):
        """
        Searches for an exact match of nand_model_to_find in column 'A' of the nand_sheet
        and returns the description from column 'B' (ru) or 'C' (en).
        Returns the description text or None. Case-insensitive search for model.
        Assumes header is in row 1, data starts from row 2.
        Column A: Model, Column B: ru Description, Column C: en Description
        """
        if not self.nand_sheet:
            logging.warning(f"_find_nand_info_by_model: nand_sheet is None (likely file not found or failed to load), cannot search.")
            return None
        if not nand_model_to_find:
            logging.warning(f"_find_nand_info_by_model: nand_model_to_find is empty or None, cannot search.")
            return None

        # Determine column index based on language
        if lang.lower() == 'en':
            info_column_index = 3 # Column C
            lang_name = 'en'
        else:
            info_column_index = 2 # Column B (default to 'ru')
            lang_name = 'ru'

        logging.info(f"Searching for NAND model '{nand_model_to_find}' in sheet '{self.nand_sheet.title}', lang='{lang_name}' (column {get_column_letter(info_column_index)})...")
        found_info_text = None
        search_model_lower = str(nand_model_to_find).strip().lower()

        try:
            # Iterate rows starting from row 2 (assuming row 1 is header)
            for row_index in range(2, self.nand_sheet.max_row + 1):
                model_cell = self.nand_sheet.cell(row=row_index, column=1).value # Column A
                if not model_cell:
                    continue # Skip empty model cells

                model_in_sheet = str(model_cell).strip().lower()

                # Case-insensitive comparison
                if model_in_sheet == search_model_lower:
                    info_cell = self.nand_sheet.cell(row=row_index, column=info_column_index).value
                    info_text = str(info_cell or "").strip()
                    if info_text:
                        logging.info(f"Found exact match for NAND model '{nand_model_to_find}' in row {row_index}. Info found for lang='{lang_name}'.")
                        found_info_text = info_text
                        break # Found the first match, exit loop
                    else:
                        # Found the model, but the description for this lang is empty.
                        logging.warning(f"Found NAND model '{nand_model_to_find}' in row {row_index}, but info cell for lang='{lang_name}' is empty.")
                        # Should we return None or keep searching? For exact match, stop.
                        break # Stop searching once the model is found, even if info is empty for this lang

            if not found_info_text:
                # This covers model not found, or model found but info empty for the language
                 logging.info(f"NAND Information not found for model '{nand_model_to_find}' with lang='{lang_name}' in sheet '{self.nand_sheet.title}'.")

        except Exception as e:
            logging.error(f"Error searching NAND info in sheet '{self.nand_sheet.title}': {e}")
            return None # Return None on error during search

        return found_info_text # Returns the description text or None