import json
import re

import openpyxl
from openpyxl.cell import Cell
from openpyxl.workbook import Workbook
from pytesseract import pytesseract
from PIL import Image, ImageGrab, ImageOps
from openpyxl_image_loader import SheetImageLoader
from openpyxl.utils import get_column_letter


class LogAnalyzer:
    def __init__(self, path, username, tesseract_path=None):
        workbook: Workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
        self.sheet = workbook.active
        self.log = self._read_log_file(path) if tesseract_path is None else self._read_photo(path, tesseract_path)
        self.log_dict = self.get_jsons(self.log) if tesseract_path is None else {}
        self.username = username

    @staticmethod
    def _read_log_file(path):
        with open(path, mode="r") as file:
            return file.read()

    @staticmethod
    def get_jsons(text) -> dict:
        try:
            text = "".join(text.split("\n")[1:])
            return json.loads(text)
        except:
            print("asdasdasdasd")

    @staticmethod
    def _read_photo(path, tesseract_path):
        img = Image.open(path)
        pytesseract.tesseract_cmd = tesseract_path
        text = ' '.join(pytesseract.image_to_string(img, lang='eng').split())
        print(text)
        return text

    def find_error_solutions(self, is_photo=False):
        results = []
        image_loader = SheetImageLoader(self.sheet)
        if not is_photo:
            model_column = None

            for cell in self.sheet[2]:
                if isinstance(cell.value, str):
                    if cell.value.lower().replace(" ", "") == \
                            self.log_dict["product"].lower().replace(" ", ""):
                        model_column = cell.column
                        break
            if model_column is None:
                return results
            rows = self.sheet.iter_rows(
                min_row=1,
                max_col=model_column,
                values_only=True)
            for index, row in enumerate(rows, start=1):
                if row[0] is not None:
                    result = {
                        "solutions": [],
                        "links": []
                    }
                    error_code = row[0].replace('“', '').replace('”', '')
                    panic_string = "".join(self.log_dict.get("panicString", "").split("\n")[0:11])
                    if re.search(re.escape(str(error_code)), panic_string):
                        answer = row[model_column - 1]
                        solutions, links = self.filter_cell(answer)

                        result["solutions"].extend(solutions)
                        result["links"].extend(links)

                        try:
                            cell = f'{get_column_letter(model_column)}{index}'
                            image = image_loader.get(cell)
                            path = f'./{self.username}{cell}.png'

                            image.save(path)
                            result["image"] = path
                        except:
                            ...

                        results.append(result)
            return results
        else:
            models = []
            for cell in self.sheet[2]:
                if (isinstance(cell.value, str) and
                        cell.value.lower().replace(" ", "") != "кодошибки"):
                    models.append({"name": cell.value.lower().replace(" ", ""),
                                   "num": cell.column})
            rows = self.sheet.iter_rows(
                min_row=1,
                values_only=True)

            for index, row in enumerate(rows, start=1):
                models_result = {}
                if row[0] is not None:
                    error_code = row[0].replace('“', '').replace('”', '')
                    have_panic = re.search(re.escape(str(error_code)), self.log)
                    if have_panic:
                        model_result = { "solutions": [], "links": [] }
                        for i, model in enumerate(models, start=0):
                            answer = row[model["num"] - 1].value.lower().replace(" ", "")
                            solution, links = self.filter_cell(answer)

                            model_result["solutions"].extend(solution)
                            model_result["links"].extend(links)

                            try:
                                cell = f'{get_column_letter(model["num"])}{index}'
                                image = image_loader.get(cell)
                                path = f'./{self.username}{cell}.png'

                                image.save(path)
                                model_result["image"] = path
                            except:
                                ...

                            models_result[model["name"]] = model_result
                results.append(models_result)
            return results

    def get_model(self) -> list:
        header_row = self.sheet[1]
        model_row = self.sheet[2]

        for header_cell, model_cell in zip(header_row[3:], model_row[3:]):
            if isinstance(model_cell.value, str):
                if model_cell.value.lower().replace(" ", "") == \
                        self.log_dict["product"].lower().replace(" ", ""):
                    return [header_cell.value, model_cell.value]

    @staticmethod
    def filter_cell(text: str):
        solutions = []
        links = []
        for value in text.split(";"):
            if (value := value.strip()).startswith("http"):
                links.append(value)
            elif value:
                solutions.append(value)
        return solutions, links
