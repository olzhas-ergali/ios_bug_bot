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

            if row[model_column - 1]:
                solutions, links = self.filter_cell(row[model_column - 1])
                result["solutions"].extend(solutions)
                result["links"].extend(links)

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
            text = "".join(self.log.split("\n")[1:])
            self.log_dict = json.loads(text)
        except Exception as e:
            print(f"Error parsing IPS file: {e}")
            self.log_dict = {}

class TxtAnalyzer(BaseAnalyzer):
    """Analyzer for TXT log files with comprehensive parsing capabilities."""

    def __init__(self, lang: str, path: Optional[str] = None, username: Optional[str] = None):
        super().__init__(lang, path, username)

    def _normalize_json_content(self, content: str) -> str:
        content = re.sub(r'\s*:\s*', ':', content)  # Remove spaces around colons
        content = re.sub(r'\s*,\s*', ',', content)  # Remove spaces around commas
        content = re.sub(r'\s+', '', content)  # Remove all spaces
        return content

    def _parse_json_content(self, content: str) -> Dict:
        try:
            normalized_content = self._normalize_json_content(content)
            return json.loads(normalized_content)
        except json.JSONDecodeError:
            combined_data = {}
            try:
                if "}{" in content:
                    parts = content.split("}{")
                    first_part = parts[0] + "}"
                    second_part = "{" + parts[1]
                    combined_data.update(json.loads(self._normalize_json_content(first_part)))
                    combined_data.update(json.loads(self._normalize_json_content(second_part)))
                    return combined_data

                lines = content.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(self._normalize_json_content(line))
                        if isinstance(data, dict):
                            combined_data.update(data)
                    except json.JSONDecodeError:
                        continue
                return combined_data
            except Exception:
                return {}

    def _extract_panic_info(self, content: str) -> Dict:
        result = {}

        panic_patterns = [
            r'panic\(.*?\):\s*(.*?)(?:\n|$)',
            r'panicString["\s:]+([^"\n]+)',
            r'Panic\s+occurred["\s:]+([^"\n]+)',
            r'error["\s:]+([^"\n]+)'
        ]
        for pattern in panic_patterns:
            if match := re.search(pattern, content, re.IGNORECASE):
                result['panicString'] = match.group(1).strip()
                break

        product_patterns = [
            r'[Pp]roduct["\s:]+([^"\n]+)',
            r'[Dd]evice["\s:]+([^"\n]+)',
            r'[Mm]odel["\s:]+([^"\n]+)'
        ]
        for pattern in product_patterns:
            if match := re.search(pattern, content, re.IGNORECASE):
                result['product'] = match.group(1).strip()
                break

        return result

    def _clean_content(self, content: str) -> str:
        content = content.encode('utf-8').decode('utf-8-sig')
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        content = content.replace('\x00', '').replace('\ufeff', '')
        return content.strip()

    def load_and_parse_file(self) -> None:
        try:
            # Attempt to read the file with different encodings
            encodings = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
            content = None
            
            for encoding in encodings:
                try:
                    with open(self.path, 'r', encoding=encoding) as file:
                        content = file.read()
                    break  # Exit the loop if reading is successful
                except UnicodeDecodeError:
                    continue  # Try the next encoding

            if content is None:
                raise ValueError("Could not decode file with any supported encoding")

            # Clean and log the content
            content = self._clean_content(content)
            self.log = content

            # Attempt to parse JSON content
            json_data = self._parse_json_content(content)

            # Fallback to extracting panic information if JSON parsing fails
            if not json_data:
                json_data = self._extract_panic_info(content)

            # Handle potential missing keys in json_data
            if not json_data.get('panicString') and not json_data.get('product'):
                fallback_data = self._extract_panic_info(content)
                json_data.update(fallback_data)

            # Set the log dictionary with extracted data
            self.log_dict = json_data

            # Log the results
            if self.log_dict:
                print("Successfully parsed file content")
                print(json.dumps(self.log_dict, indent=2, ensure_ascii=False))
            else:
                print("Warning: No data could be extracted from the file")

        except Exception as e:
            print(f"Error parsing file: {e}")
            self.log_dict = {}