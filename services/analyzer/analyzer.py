import json
import re

import openpyxl
from openpyxl.cell import Cell
from openpyxl.workbook import Workbook
from pytesseract import pytesseract
from PIL import Image, ImageGrab, ImageOps


class LogAnalyzer:
    def __init__(self, path, tesseract_path=None):
        workbook: Workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
        self.sheet = workbook.active
        self.log = self._read_log_file(path) if tesseract_path is None else self._read_photo(path, tesseract_path)
        self.log_dict = self.get_jsons(self.log) if tesseract_path is None else {}

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
        results = {
            "solutions": [],
            "links": []
        }
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
            for row in rows:
                if row[0] is not None:
                    error_code = row[0].replace('“', '').replace('”', '')
                    panic_string = "".join(self.log_dict.get("panicString", "").split("\n")[0:11])
                    have_panic = re.search(re.escape(str(error_code)), panic_string)
                    if have_panic:
                        answer = row[model_column - 1]
                        solution, links = self.filter_cell(answer)
                        results["solutions"].extend(solution)
                        results["links"].extend(links)

            return results
        else:
            results = {}
            models = []
            for cell in self.sheet[2]:
                if (isinstance(cell.value, str) and
                        cell.value.lower().replace(" ", "") != "кодошибки"):
                    results[cell.value.lower().replace(" ", "")] = {
                         "solutions": [],
                         "links": []
                    }
                    models.append(cell.value.lower().replace(" ", ""))
            rows = self.sheet.iter_rows(
                min_row=1,
                values_only=True)

            for row in rows:
                if row[0] is not None:
                    error_code = row[0].replace('“', '').replace('”', '')
                    have_panic = re.search(re.escape(str(error_code)), self.log)
                    if have_panic:
                        for i in range(len(models)):
                            answer = row[i+1].value.lower().replace(" ", "")
                            solution, links = self.filter_cell(answer)
                            results[models[i]]["solutions"].extend(solution)
                            results[models[i]]["links"].extend(links)
                        break
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
