import json
import re

import openpyxl
from openpyxl.cell import Cell


class LogAnalyzer:
    def __init__(self, path):
        workbook = openpyxl.load_workbook("./data/panic_codes.xlsx")
        self.sheet = workbook["Лист1"]
        self.log = self._read_log_file(path)
        self.log_dict = self.get_jsons(self.log)

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

    def find_error_solutions(self):
        results = {
            "solutions": [],
            "links": []
        }

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
                panic_string = self.log_dict.get("panicString", "")
                have_panic = re.search(re.escape(str(error_code)), panic_string)
                if have_panic:
                    answer = row[model_column - 1]
                    results["solutions"], results["links"] = self.filter_cell(
                        answer)

        return results

    def get_model(self) -> list:
        header_row = self.sheet[1]
        model_row = self.sheet[2]

        for header_cell, model_cell in zip(header_row[3:], model_row[3:]):
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
