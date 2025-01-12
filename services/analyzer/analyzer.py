import io
import json
import re
from typing import Dict, List, Tuple, Optional

import openpyxl
from openpyxl.workbook import Workbook
from pytesseract import pytesseract
from PIL import Image
from openpyxl.utils import get_column_letter

class BaseAnalyzer:
    def __init__(self, lang: str, path: Optional[str] = None, username: Optional[str] = None):
        """Initialize base analyzer with common attributes."""
        self.lang = lang
        self.path = path
        self.username = username
        self.log = ""
        self.log_dict: Dict = {}
        
        # Load Excel workbook
        workbook: Workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
        self.sheet = workbook[lang]
        self._images = {}

        if path:
            self.load_and_parse_file()

    def load_and_parse_file(self) -> None:
        """Load and parse the input file."""
        raise NotImplementedError

    def read_images(self) -> None:
        """Read images from Excel sheet."""
        sheet_images = self.sheet._images
        for image in sheet_images:
            row = image.anchor._from.row + 1
            col = get_column_letter(image.anchor._from.col)
            self._images[f'{col}{row}'] = image._data

    def get_image(self, cell: str) -> Image.Image:
        """Get image from cell."""
        if cell not in self._images:
            raise ValueError(f"Cell {cell} doesn't contain an image")
        image = io.BytesIO(self._images[cell]())
        return Image.open(image)

    def get_model(self) -> Optional[List[str]]:
        """Get device model information."""
        if not self.log_dict.get("product"):
            return None

        product = self.log_dict["product"].lower().replace(" ", "")
        for header_cell, model_cell in zip(self.sheet[1][1:], self.sheet[2][1:]):
            if isinstance(model_cell.value, str):
                if model_cell.value.lower().replace(" ", "") == product:
                    return [header_cell.value, model_cell.value]
        return None

    @staticmethod
    def filter_cell(text: str) -> Tuple[List[str], List[str]]:
        """Filter cell content into solutions and links."""
        solutions = []
        links = []
        if text:
            for value in text.split(";"):
                if (value := value.strip()).startswith("http"):
                    links.append(value)
                elif value:
                    solutions.append(value)
        return solutions, links

    def find_error_solutions(self, is_photo: bool = False, error: Optional[str] = None, 
                           model: Optional[str] = None) -> List[Dict]:
        """Find error solutions based on log content."""
        results = []
        self.read_images()
        
        # Find model column
        model_column = None
        for cell in self.sheet[2]:
            product = model if model is not None else self.log_dict.get("product")
            if product and isinstance(cell.value, str):
                if cell.value.lower().replace(" ", "") == product.lower().replace(" ", ""):
                    model_column = cell.column
                    break

        if not model_column:
            return results

        rows = self.sheet.iter_rows(min_row=1, max_col=model_column, values_only=True)
        is_mini = False

        for index, row in enumerate(rows, start=1):
            if not row[0]:
                continue

            result = {
                "solutions": [],
                "links": [],
                "is_full": True,
                "error_code": None
            }

            error_code = str(row[0]).replace('"', '').replace('"', '')
            
            if error is None and model is None:
                if " mini" in error_code:
                    error_code = error_code[:error_code.find(" mini")]
                    result['is_full'] = False
                    result['error_code'] = error_code

                if is_mini:
                    is_mini = False
                    continue
                elif not result['is_full']:
                    is_mini = True

                panic_string = self.log_dict.get("panicString", "")
            else:
                panic_string = error

            if not panic_string or not re.search(re.escape(error_code), panic_string):
                continue

            # Process solutions and links
            if row[model_column - 1]:
                solutions, links = self.filter_cell(row[model_column - 1])
                result["solutions"].extend(solutions)
                result["links"].extend(links)

            # Process images
            try:
                cell = f'{get_column_letter(model_column - 1)}{index}'
                image = self.get_image(cell)
                path = f'./{self.username}{cell}.png'
                image.save(path)
                result["image"] = path
            except Exception as ex:
                print(f"Image processing error: {ex}")

            if error is not None:
                return result

            if result["solutions"] or result["links"]:
                results.append(result)

        return results

class LogAnalyzer(BaseAnalyzer):
    """Analyzer for IPS log files."""
    def load_and_parse_file(self) -> None:
        """Load and parse IPS log file."""
        try:
            with open(self.path, "r", encoding='utf-8') as file:
                self.log = file.read()
            # Parse JSON content after first line
            text = "".join(self.log.split("\n")[1:])
            self.log_dict = json.loads(text)
        except Exception as e:
            print(f"Error parsing IPS file: {e}")
            self.log_dict = {}

class TxtAnalyzer(BaseAnalyzer):
    def load_and_parse_file(self) -> None:
        try:
            with open(self.path, "r", encoding='utf-8') as file:
                self.log = file.read()

            lines = self.log.split('\n')
            self.log_dict = {}

            for line in lines:
                try:
                    cleaned_line = line.replace(' ', '').replace('\\', '\\\\')

                    # Поиск ключей (например, "product") и значений
                    if ':' in cleaned_line and '"' in cleaned_line:
                        key, value = cleaned_line.split(':', 1)

                        # Удаляем пробелы вокруг значений и извлекаем данные внутри кавычек
                        value = value.strip().strip('"').rstrip(',')  # Убираем запятую, если она есть
                        value = value.rstrip('"')  # Убираем кавычку, если она есть в конце

                        # Используем ключ как есть, включая кавычки
                        if key.lower() == '"product"':
                            self.log_dict['product'] = value  # Сохраняем продукт
                        elif key.lower() == '"panicstring"':
                            self.log_dict.setdefault('panicString', []).append(value)
                except Exception as e:
                    print(f"Warning: Error processing line: {e}")
                    continue

            # Объединение panicString, если найдено
            if 'panicString' in self.log_dict:
                self.log_dict['panicString'] = ' '.join(self.log_dict['panicString'])

            # Отладочный вывод
            print(f"Found product: {self.log_dict.get('product')}")

        except Exception as e:
            print(f"Error parsing TXT file: {e}")
            self.log_dict = {}
