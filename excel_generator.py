import io
from openpyxl import Workbook

def generate_excel(data) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active

    # Если данные не пустые, добавляем заголовки и строки
    if data:
        headers = list(data[0].keys())
        ws.append(headers)
        for record in data:
            ws.append([record.get(header) for header in headers])
    else:
        ws.append(["Нет данных для отображения"])

    # Сохраняем рабочую книгу в BytesIO
    excel_io = io.BytesIO()
    wb.save(excel_io)
    excel_io.seek(0)
    return excel_io
