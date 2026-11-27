"""CSV export: what a page shows as a .csv download (UTF-8, commas, opens in Excel); several tables (a harness's pinout,
groups, connectors and parts list) as a .zip of one .csv each. ``web.sheets`` takes either back in."""
import csv
from io import BytesIO, StringIO

from django.http import HttpResponse
from django.utils.text import slugify


def download(filename, sheets):
    """``sheets``: [(title, headers, rows)]. Rows hold plain values (text, numbers, dates)."""
    name = slugify(filename) or 'osmia'
    sheets = list(sheets) or [('Empty', [], [])]
    if len(sheets) == 1:
        response = HttpResponse(table(*sheets[0]), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{name}.csv"'
        return response
    from zipfile import ZIP_DEFLATED, ZipFile
    out, used = BytesIO(), set()
    with ZipFile(out, 'w', ZIP_DEFLATED) as zipped:
        for title, headers, rows in sheets:
            member = _title(title, used)
            zipped.writestr(member + '.csv', table(title, headers, rows))
    response = HttpResponse(out.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{name}.zip"'
    return response


def table(title, headers, rows):
    """One table as CSV bytes: its headers, then its rows (UTF-8 with a byte order mark, so Excel reads its accents)."""
    out = StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow([_plain(v) for v in row])
    return out.getvalue().encode('utf-8-sig')


def _title(text, used):
    """A file name for a table in the .zip: its title without the characters a file name may not have, not used twice."""
    for ch in '<>:"/\|?*':
        text = text.replace(ch, ' ')
    base = ' '.join(text.split()) or 'Sheet'
    name, n = base, 2
    while name.lower() in used:
        name, n = f'{base} {n}', n + 1
    used.add(name.lower())
    return name


def _plain(value):
    from datetime import datetime
    from decimal import Decimal

    from django.utils import timezone
    if value is None:
        return ''
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%Y-%m-%d %H:%M')
    if hasattr(value, 'isoformat'):   # a date
        return value.isoformat()
    if isinstance(value, Decimal):   # without the zeros it is kept with: 9, 2.5
        text = format(value, 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    return str(value)
