import openpyxl


class ExcelToDict:
    def __init__(self, file_path):
        self.file_path = file_path

    def generate_dict(self):
        workbook = openpyxl.load_workbook(self.file_path)
        sheet = workbook.active

        data_dict = {}

        for row in sheet.iter_rows(min_row=2, values_only=True):
            key = row[0]
            value = row[1]
            data_dict[key] = value

        return data_dict
