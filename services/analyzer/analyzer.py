import json
import re

from services.tags.xlsx_reader import ExcelToDict


class LogAnalyzer:
    def __init__(self, path):
        reader = ExcelToDict("D:/PROJECTS/ios_bug_bot/data/panic_tags.xlsx")
        self.patterns = reader.generate_dict()
        self.log = self._read_log_file(path)
        self.log_dict = self.get_jsons(self.log)

    @staticmethod
    def _read_log_file(path):
        with open(path, mode="r") as file:
            return file.read()

    @staticmethod
    def get_jsons(text) -> dict:
        text = "".join(text.split("\n")[1:])
        return json.loads(text)

    def analyze(self):
        results = {
            "problems": [],
            "product": ""
        }
        panic_string = self.log_dict["panicString"]

        for pattern, description in self.patterns.items():
            if pattern:
                pattern = pattern.replace('“', "").replace("”", "")
                match = re.search(pattern + r'.*', panic_string, re.DOTALL)
                if match:
                    results["problems"].append(description)
        results["product"] = self.log_dict["product"]
        return results

    def get_model(self):
        result = re.search(r's.*', self.log, re.DOTALL)
        if result:
            return result.group()


if __name__ == "__main__":
    analyzer = LogAnalyzer("D:\\PROJECTS\\ios_bug_bot\\data\\tmp\\panic-full-2024-08-10-112544.0002.ips")
    print(analyzer.analyze())
