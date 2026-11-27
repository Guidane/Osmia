"""Sheet import: the rows of a table sent as a CSV file (one made by ⬇ CSV, edited, or made by hand), a .zip of them
(⬇ CSV of several tables) or an Excel file (.xlsx), each as {header: value}. See ``web.csvfile`` for the export. The same rows can come from a data file
(``web.datafile``): then each is named by where it is in the file ("item_definitions 3") instead of its row number."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

MOST_ERRORS = 15   # an import refused: at most this many of its errors shown


def at(n):
    """Where a row is, as its messages say it: "Row 4" (in a sheet), else as given ("budgets 2")."""
    return f'Row {n}' if isinstance(n, int) else str(n)


def read(sent, title):
    """The rows of the sheet ``title`` (else the first one) of the file ``sent`` (in a .zip of CSV files: ``title``.csv,
    else the first): [(row number, {header in lower case: value})], empty rows left out. Headers are matched without
    case and surrounding spaces."""
    from zipfile import BadZipFile, ZipFile

    from openpyxl import load_workbook
    if sent is None:
        raise ValidationError('Pick a CSV file (or an Excel file, .xlsx).')
    head = sent.read(4)
    sent.seek(0)
    if head[:2] != b'PK':   # not a zip: no .xlsx; a CSV file (as an AI or another program writes one)?
        if str(getattr(sent, 'name', '')).lower().endswith(('.xlsx', '.xlsm')):
            raise ValidationError(f'{sent.name} is not an Excel file (.xlsx).')
        return _csv(sent)
    try:   # a .zip of CSV files (⬇ CSV of several tables)?
        with ZipFile(sent) as zipped:
            tables = {n.rsplit('/', 1)[-1][:-4].strip().lower(): n for n in zipped.namelist() if n.lower().endswith('.csv')}
            if tables:
                from django.core.files.base import ContentFile
                member = tables.get(title.lower()) or next(iter(tables.values()))
                return _csv(ContentFile(zipped.read(member), name=getattr(sent, 'name', '')))
    except BadZipFile:
        pass
    sent.seek(0)
    try:
        book = load_workbook(sent, read_only=True, data_only=True)
    except (BadZipFile, KeyError, OSError, ValueError):
        raise ValidationError(f'{getattr(sent, "name", "That file")} is not a CSV file, a .zip of them or an Excel file (.xlsx).')
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


def _csv(sent):
    """The rows of a CSV file: UTF-8 (else Windows' Western European), its columns split by commas, semicolons or tabs."""
    import csv
    raw = sent.read()
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        content = raw.decode('cp1252', errors='replace')
    if '\x00' in content or not content.strip():
        raise ValidationError(f'{getattr(sent, "name", "That file")} is not a CSV file (or an Excel file, .xlsx).')
    first = content.splitlines()[0]
    delimiter = max(',;\t', key=first.count)
    lines = list(csv.reader(content.splitlines(), delimiter=delimiter))
    headers = [h.strip().lower() for h in lines[0]]
    out = []
    for n, values in enumerate(lines[1:], 2):
        row = {h: (v if v.strip() else None) for h, v in zip(headers, values) if h}
        if any(v is not None for v in row.values()):
            out.append((n, row))
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
        raise ValidationError(f'{at(n)}: the {what} "{value}" is not a number.')
    try:
        found = Decimal(str(value).strip().replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise ValidationError(f'{at(n)}: the {what} "{value}" is not a number.')
    if not found.is_finite():
        raise ValidationError(f'{at(n)}: the {what} "{value}" is not a number.')
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
    raise ValidationError(f'{at(n)}: the {what} "{value}" is not yes or no.')


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
    raise ValidationError(f'{at(n)}: the {what} "{value}" is not a date (2026-03-01).')


def refuse(problems):
    """Refuse an import with its problems (the first ``MOST_ERRORS``)."""
    shown = problems[:MOST_ERRORS]
    if len(problems) > len(shown):
        shown.append(f'… and {len(problems) - len(shown)} more.')
    raise ValidationError(['Nothing was imported.'] + shown)
