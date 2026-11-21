from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .services import display_name

HEADER_FILL = PatternFill('solid', start_color='DDE3EA')
GREEN = PatternFill('solid', start_color='D1E7DD')
YELLOW = PatternFill('solid', start_color='FFF3CD')
RED = PatternFill('solid', start_color='F8D7DA')


def _force_text(ws):
    """
    Защита от «формул»: openpyxl считает текст, начинающийся с «=», формулой.
    Принудительно помечаем такие ячейки как обычный текст.
    """
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith('='):
                cell.data_type = 's'


def _naive_local(dt):
    """Excel не умеет часовые пояса: переводим в местное время и убираем зону."""
    return timezone.localtime(dt).replace(tzinfo=None) if dt else None


def _style_header(ws, columns_count):
    for col in range(1, columns_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def _fit_columns(ws, first_width=None):
    for col_cells in ws.columns:
        longest = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(longest + 2, 10), 45)
    if first_width:
        ws.column_dimensions['A'].width = first_width


def build_workbook(data):
    """Делает Excel-файл из результата services.build_results(). Возвращает байты файла."""
    tests = data['tests']
    wb = Workbook()

    # --- Лист 1: сводная таблица ---
    ws = wb.active
    ws.title = 'Результаты'
    ws.append(['Ученик', 'Группы'] + [t.title for t in tests] + ['Всего баллов', 'Из возможных', 'Долгов'])
    _style_header(ws, 2 + len(tests) + 3)

    for row in data['rows']:
        values = [row['name'], row['groups']]
        fills = [None, None]
        for cell in row['cells']:
            status = cell['status']
            if cell['attempt']:
                values.append(round(cell['attempt'].score, 2))
                fills.append(YELLOW if status == 'late' else GREEN)
            elif status == 'debt':
                values.append('долг')
                fills.append(RED)
            elif status == 'waiting':
                values.append('не сдан')
                fills.append(None)
            else:
                values.append(None)
                fills.append(None)
        values += [row['total'], row['total_max'], row['debts']]
        fills += [None, None, None]

        ws.append(values)
        excel_row = ws.max_row
        for col, fill in enumerate(fills, start=1):
            if fill:
                ws.cell(row=excel_row, column=col).fill = fill
            if col > 2:
                ws.cell(row=excel_row, column=col).alignment = Alignment(horizontal='center')

    _force_text(ws)
    ws.freeze_panes = 'C2'
    _fit_columns(ws, first_width=28)

    # Легенда под таблицей
    legend_row = ws.max_row + 2
    ws.cell(row=legend_row, column=1, value='Зелёный: сдано вовремя').fill = GREEN
    ws.cell(row=legend_row + 1, column=1, value='Жёлтый: сдано с опозданием').fill = YELLOW
    ws.cell(row=legend_row + 2, column=1, value='Красный: долг (срок прошёл)').fill = RED

    # --- Лист 2: все попытки списком ---
    ws2 = wb.create_sheet('Попытки')
    ws2.append(['Ученик', 'Тест', 'Баллы', 'Максимум', '%', 'Сдан', 'Срок', 'С опозданием'])
    _style_header(ws2, 8)
    for at in data['attempts']:
        due = at.assignment.due_date if at.assignment_id else None
        ws2.append([
            display_name(at.user) if at.user_id else at.student_name,
            at.test.title,
            round(at.score, 2),
            round(at.max_score, 2),
            at.percent,
            _naive_local(at.created_at),
            _naive_local(due),
            'да' if at.is_late else 'нет',
        ])
        ws2.cell(row=ws2.max_row, column=6).number_format = 'DD.MM.YYYY HH:MM'
        ws2.cell(row=ws2.max_row, column=7).number_format = 'DD.MM.YYYY HH:MM'
    _force_text(ws2)
    ws2.freeze_panes = 'A2'
    _fit_columns(ws2)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
