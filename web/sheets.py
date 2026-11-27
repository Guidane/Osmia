"""Excel import: the rows of a sheet sent as an .xlsx file (one made by ⬇ Excel, edited, or made by hand), each as
{header: value}. See ``web.excel`` for the export."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

MOST_ERRORS = 15   # an import refused: at most this many of its errors shown


def read(sent, title):
    """The rows of the sheet ``title`` (else the first one) of the file ``sent``: [(row number in Excel, {header in
    lower case: value})], empty rows left out. Headers are matched without case and surrounding spaces."""
    from zipfile import BadZipFile

    from openpyxl import load_workbook
    if sent is None:
        raise ValidationError('Pick an Excel file (.xlsx).')
    try:
        book = load_workbook(sent, read_only=True, data_only=True)
    except (BadZipFile, KeyError, OSError, ValueError):
        raise ValidationError(f'{getattr(sent, "name", "That file")} is not an Excel file (.xlsx).')
    names = {n.strip().lower(): n for n in book.sheetnames}
    sheet = book[names.get(title.lower(), book.sheetnames[0])]
    lines = sheet.iter_rows(values_only=True)
    headers = [str(h or '').strip().lower() for h in next(lines, ())]
    out = []
    for n, values in enumerate(lines, 2):
        row = {h: v for h, v in zip(headers, values) if h}
        if any(v not in (None, '') for v in row.values()):
            out.append((n, row))
    book.close()
    return out


def text(row, header, longest=None):
    """A cell as text ('' when empty); a whole number written as a number in Excel without its ``.0``."""
    value = row.get(header)
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    value = str(value).strip()
    if '\n' not in value:   # (notes keep their lines)
        value = ' '.join(value.split())
    return value[:longest] if longest else value


def number(row, header, n, what):
    """A cell as a number (None when empty): 12, 12.5, "12,5"."""
    value = row.get(header)
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValidationError(f'Row {n}: the {what} "{value}" is not a number.')
    try:
        found = Decimal(str(value).strip().replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise ValidationError(f'Row {n}: the {what} "{value}" is not a number.')
    if not found.is_finite():
        raise ValidationError(f'Row {n}: the {what} "{value}" is not a number.')
    return found


def yes(row, header, n, what):
    """A cell as yes or no (None when empty)."""
    value = row.get(header)
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        return value
    word = str(value).strip().lower()
    if word in ('yes', 'y', 'true', '1', 'x', 'ja', 'oui'):
        return True
    if word in ('no', 'n', 'false', '0', 'nee', 'non'):
        return False
    raise ValidationError(f'Row {n}: the {what} "{value}" is not yes or no.')


def day(row, header, n, what):
    """A cell as a date (None when empty): an Excel date, or text 2026-03-01 / 1-3-2026."""
    value = row.get(header)
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    word = str(value).strip()
    for form in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(word, form).date()
        except ValueError:
            pass
    raise ValidationError(f'Row {n}: the {what} "{value}" is not a date (2026-03-01).')


def refuse(problems):
    """Refuse an import with its problems (the first ``MOST_ERRORS``)."""
    shown = problems[:MOST_ERRORS]
    if len(problems) > len(shown):
        shown.append(f'… and {len(problems) - len(shown)} more.')
    raise ValidationError(['Nothing was imported.'] + shown)
