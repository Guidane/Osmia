"""Item definitions, vendors, locations and categories brought in: from a CSV or Excel file (the table "Item
definitions" as ⬇ CSV makes it; its other tables, and its columns that are counted, not kept, are left out) or from
a data file (``web.datafile``).

Each item definition is the one with its item number: changed when there is one, else made. A column left out leaves
that of each item definition as it is; an empty cell empties it. Categories ("Connectors / D-sub") and vendors not
here yet are made."""
from django.core.exceptions import ValidationError
from django.db import transaction

from web import sheets
from web.sheets import at

from .models import Category, ItemDefinition, Location, Vendor

SHEET = 'Item definitions'
TEXTS = [('description', 'description'), ('manufacturer', 'manufacturer'), ('manufacturer part number', 'mpn'),
         ("vendor's number", 'vendor_number'), ('datasheet', 'datasheet'), ('notes', 'notes')]
KEYS = {'number': 'item number', 'mpn': 'manufacturer part number', 'vendor_number': "vendor's number", 'price': 'last price',
        'reorder_quantity': 'reorder quantity', 'is_asset': 'is asset'}   # a data file's names for the sheet's columns


def choice(choices, value):
    """The stored value of a choice given as it is stored or as it is shown ("pcs", "pieces"); None when it is none."""
    word = str(value).strip().lower().replace(' ', '_')
    for stored, shown in choices:
        if word in (stored.lower(), str(shown).lower().replace(' ', '_')):
            return stored
    return None


def in_tree(model, path, made, what, **extra):
    """The node of a tree (categories, locations) at ``path`` ("Store / Shelf 3", or a list of names), made (with
    those above it) when it isn't there; None for no path."""
    names = path if isinstance(path, list) else str(path or '').replace('›', '/').split('/')
    node = None
    for name in [' '.join(str(p).split()) for p in names if str(p).strip()]:
        found = model.objects.filter(parent=node, name__iexact=name).first()
        if found is None:
            found = model.objects.create(parent=node, name=name[:100], **extra)
            made.append(f'{what} {found.path} was made.')
        node = found
    return node


def vendor(name, made):
    found = Vendor.objects.filter(name__iexact=name).first()
    if found is None:
        found = Vendor.objects.create(name=name[:200])
        made.append(f'Vendor {found.name} was made.')
    return found


def apply_definitions(rows):
    """``rows`` ([(where, {column: value})]) as item definitions: (made, changed, notes, problems)."""
    problems, notes, seen = [], [], {}
    made = changed = 0
    for n, row in rows:
        try:
            with transaction.atomic():
                number = sheets.text(row, 'item number', 100)
                if not number:
                    raise ValidationError(f'{at(n)}: it has no item number.')
                if number.lower() in seen:
                    raise ValidationError(f'{at(n)}: item number {number} is in {at(seen[number.lower()]).lower()} already.')
                seen[number.lower()] = n
                item = ItemDefinition.objects.filter(number__iexact=number).first()
                new = item is None
                item = item or ItemDefinition(number=number)
                for header, field in TEXTS:
                    if header in row:
                        setattr(item, field, sheets.text(row, header, ItemDefinition._meta.get_field(field).max_length))
                for header, field, choices in (('kind', 'kind', ItemDefinition.Kind.choices), ('unit', 'unit', ItemDefinition.Unit.choices)):
                    if sheets.text(row, header):
                        found = choice(choices, sheets.text(row, header))
                        if found is None:
                            raise ValidationError(f'{at(n)}: "{sheets.text(row, header)}" is not a {header} '
                                                  f'({", ".join(str(shown) for _, shown in choices)}).')
                        setattr(item, field, found)
                if 'category' in row:
                    item.category = in_tree(Category, row['category'], notes, 'Category') if sheets.text(row, 'category') else None
                if 'vendor' in row:
                    item.vendor = vendor(sheets.text(row, 'vendor', 200), notes) if sheets.text(row, 'vendor') else None
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
                    raise ValidationError([f'{at(n)}: {m}' for m in exc.messages])
                item.save()
                made, changed = made + new, changed + (not new)
        except ValidationError as exc:
            problems += exc.messages
    return made, changed, notes, problems


def import_definitions(sent):
    """The item definitions in the CSV or Excel file ``sent``: (made, changed, notes). All or nothing: any row that is
    wrong and nothing is imported (a ValidationError saying which rows)."""
    rows = sheets.read(sent, SHEET)
    if not rows:
        raise ValidationError(f'There are no item definitions in {sent.name}.')
    if 'item number' not in rows[0][1]:
        raise ValidationError(f'{sent.name} has no "Item number" column (the table "{SHEET}", as ⬇ CSV makes it).')
    with transaction.atomic():
        made, changed, notes, problems = apply_definitions(rows)
        if problems:
            transaction.set_rollback(True)
    if problems:
        sheets.refuse(problems)
    return made, changed, notes


def apply_vendors(entries):
    """A data file's vendors ([(where, {field: value})]), each the one with its name (any case), else made:
    (made, changed, notes, problems)."""
    problems, made, changed = [], 0, 0
    fields = ('code', 'website', 'email', 'phone', 'address', 'account_number', 'notes')
    for n, e in entries:
        try:
            with transaction.atomic():
                name = sheets.text(e, 'name', 200)
                if not name:
                    raise ValidationError(f'{at(n)}: it has no name.')
                item = Vendor.objects.filter(name__iexact=name).first()
                new = item is None
                item = item or Vendor(name=name)
                for field in fields:
                    if field in e:
                        setattr(item, field, sheets.text(e, field, Vendor._meta.get_field(field).max_length))
                if sheets.yes(e, 'active', n, 'active') is not None:
                    item.active = sheets.yes(e, 'active', n, 'active')
                try:
                    item.full_clean()
                except ValidationError as exc:
                    raise ValidationError([f'{at(n)}: {m}' for m in exc.messages])
                item.save()
                made, changed = made + new, changed + (not new)
        except ValidationError as exc:
            problems += exc.messages
    return made, changed, [], problems


def apply_tree(model, what, fields):
    """For a data file's locations or categories ([(where, {"path", field: value})]): each the node at its path
    (made, with those above it, when it isn't there), its ``fields`` set."""
    def apply(entries):
        problems, notes, made, changed = [], [], 0, 0
        for n, e in entries:
            try:
                with transaction.atomic():
                    if not sheets.text(e, 'path') and not isinstance(e.get('path'), list):
                        raise ValidationError(f'{at(n)}: it has no path ("Store / Shelf 3").')
                    before = len(notes)
                    node = in_tree(model, e['path'], notes, what)
                    made, changed = made + (len(notes) > before), changed + (len(notes) == before)
                    for field in fields:
                        if field in e:
                            setattr(node, field, sheets.text(e, field, model._meta.get_field(field).max_length))
                    node.save()
            except ValidationError as exc:
                problems += exc.messages
        return made, changed, [], problems
    return apply


apply_locations = apply_tree(Location, 'Location', ('description', 'notes'))
apply_categories = apply_tree(Category, 'Category', ())
