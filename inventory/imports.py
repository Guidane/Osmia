"""Item definitions from an Excel file: the sheet "Item definitions" as ⬇ Excel makes it (its other sheets, and its
columns that are counted, not kept, are left out). Each row is the item definition with its item number: changed when
there is one, else made. A column left out of the sheet leaves that of each item definition as it is; an empty cell
empties it. Categories ("Connectors / D-sub") and vendors not here yet are made."""
from django.core.exceptions import ValidationError
from django.db import transaction

from web import sheets

from .models import Category, ItemDefinition, Vendor

SHEET = 'Item definitions'
TEXTS = [('description', 'description'), ('manufacturer', 'manufacturer'), ('manufacturer part number', 'mpn'),
         ("vendor's number", 'vendor_number'), ('datasheet', 'datasheet'), ('notes', 'notes')]


def _choice(choices, value):
    """The stored value of a choice given as it is stored or as it is shown ("pcs", "pieces"); None when it is none."""
    word = value.strip().lower()
    for stored, shown in choices:
        if word in (stored.lower(), str(shown).lower()):
            return stored
    return None


def _category(path, made):
    """The category at ``path`` ("Connectors / D-sub"), made (with those above it) when it isn't there."""
    node = None
    for name in [p.strip() for p in path.split('/') if p.strip()]:
        found = Category.objects.filter(parent=node, name__iexact=name).first()
        if found is None:
            found = Category.objects.create(parent=node, name=name[:100])
            made.append(f'Category {found.path} was made.')
        node = found
    return node


def _vendor(name, made):
    found = Vendor.objects.filter(name__iexact=name).first()
    if found is None:
        found = Vendor.objects.create(name=name[:200])
        made.append(f'Vendor {found.name} was made.')
    return found


def import_definitions(sent):
    """The item definitions in the Excel file ``sent``: (made, changed, notes). All or nothing: any row that is wrong
    and nothing is imported (a ValidationError saying which rows)."""
    rows = sheets.read(sent, SHEET)
    if not rows:
        raise ValidationError(f'There are no item definitions in {sent.name}.')
    if 'item number' not in rows[0][1]:
        raise ValidationError(f'{sent.name} has no "Item number" column (the sheet "{SHEET}", as ⬇ Excel makes it).')
    problems, notes, seen = [], [], {}
    made = changed = 0
    with transaction.atomic():
        for n, row in rows:
            try:
                number = sheets.text(row, 'item number', 100)
                if not number:
                    raise ValidationError(f'Row {n}: it has no item number.')
                if number.lower() in seen:
                    raise ValidationError(f'Row {n}: item number {number} is in row {seen[number.lower()]} already.')
                seen[number.lower()] = n
                item = ItemDefinition.objects.filter(number__iexact=number).first()
                new = item is None
                item = item or ItemDefinition(number=number)
                for header, field in TEXTS:
                    if header in row:
                        setattr(item, field, sheets.text(row, header, ItemDefinition._meta.get_field(field).max_length))
                for header, field, choices in (('kind', 'kind', ItemDefinition.Kind.choices), ('unit', 'unit', ItemDefinition.Unit.choices)):
                    if sheets.text(row, header):
                        found = _choice(choices, sheets.text(row, header))
                        if found is None:
                            raise ValidationError(f'Row {n}: "{sheets.text(row, header)}" is not a {header} '
                                                  f'({", ".join(str(shown) for _, shown in choices)}).')
                        setattr(item, field, found)
                if 'category' in row:
                    item.category = _category(sheets.text(row, 'category'), notes) if sheets.text(row, 'category') else None
                if 'vendor' in row:
                    item.vendor = _vendor(sheets.text(row, 'vendor', 200), notes) if sheets.text(row, 'vendor') else None
                if 'last price' in row:
                    item.price = sheets.number(row, 'last price', n, 'last price')
                for header, field in (('minimum', 'minimum'), ('reorder quantity', 'reorder_quantity')):
                    if header in row:
                        setattr(item, field, sheets.number(row, header, n, header) or 0)
                for header, field in (('active', 'active'), ('is asset', 'is_asset')):
                    if sheets.yes(row, header, n, header) is not None:
                        setattr(item, field, sheets.yes(row, header, n, header))
                try:
                    item.full_clean(exclude=['category', 'vendor', 'family', 'branch'])
                except ValidationError as exc:
                    raise ValidationError([f'Row {n}: {m}' for m in exc.messages])
                item.save()
                made, changed = made + new, changed + (not new)
            except ValidationError as exc:
                problems += exc.messages
        if problems:
            transaction.set_rollback(True)
    if problems:
        sheets.refuse(problems)
    return made, changed, notes
