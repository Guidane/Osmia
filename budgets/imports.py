"""Budgets brought in: from an Excel or CSV file (the sheet "Budgets" as ⬇ Excel makes it; its columns that are
counted, not kept, such as what is spent, are left out) or from a data file (``web.datafile``).

Each row is the budget with its number (with no number: the one with its name in the same budget): changed when there
is one, else made. A column left out leaves that of each budget as it is; an empty cell empties it. "Part of" names a
budget as the list shows it ("FY26 2026"), here or in the sheet."""
from django.core.exceptions import ValidationError
from django.db import transaction

from web import lookups, sheets
from web.lookups import key
from web.sheets import at

from .models import Budget

SHEET = 'Budgets'
KEYS = {'part_of': 'part of', 'starts_on': 'starts', 'ends_on': 'ends'}   # a data file's names for the sheet's columns


def apply_budgets(rows):
    """``rows`` ([(where, {column: value})]) as budgets: (made, changed, notes, problems)."""
    problems, placed, seen = [], [], {}
    made = changed = 0
    for n, row in rows:   # each budget, without what it is part of yet
        try:
            with transaction.atomic():
                number, name, part_of = sheets.text(row, 'number', 50), sheets.text(row, 'name', 100), sheets.text(row, 'part of')
                if not name:
                    raise ValidationError(f'{at(n)}: it has no name.')
                k = key(number) if number else key(f'{part_of} › {name}')
                if k in seen:
                    raise ValidationError(f'{at(n)}: budget {number or name} is in {at(seen[k]).lower()} already.')
                seen[k] = n
                if number:
                    item = Budget.objects.filter(number__iexact=number).first()
                else:
                    item = next((b for b in Budget.objects.filter(number='', name__iexact=name).select_related('parent')
                                 if key(b.parent or '') == key(part_of)), None)
                new = item is None
                item = item or Budget()
                item.number, item.name = number, name
                if 'amount' in row:
                    item.amount = sheets.number(row, 'amount', n, 'amount') or 0
                for header, find in (('setup', lookups.setup), ('owner', lookups.user), ('department', lookups.department)):
                    if header in row:
                        setattr(item, header, find(sheets.text(row, header), n) if sheets.text(row, header) else None)
                for header, field in (('starts', 'starts_on'), ('ends', 'ends_on')):
                    if header in row:
                        setattr(item, field, sheets.day(row, header, n, f'{header} date'))
                if item.starts_on and item.ends_on and item.ends_on < item.starts_on:
                    raise ValidationError(f'{at(n)}: it ends before it starts.')
                if 'notes' in row:
                    item.notes = sheets.text(row, 'notes')
                if sheets.yes(row, 'active', n, 'active') is not None:
                    item.active = sheets.yes(row, 'active', n, 'active')
                try:
                    item.full_clean(exclude=['parent', 'setup', 'owner', 'department'])
                except ValidationError as exc:
                    raise ValidationError([f'{at(n)}: {m}' for m in exc.messages])
                item.save()
                placed.append((n, item, part_of if 'part of' in row else None))
                made, changed = made + new, changed + (not new)
        except ValidationError as exc:
            problems += exc.messages
    if not problems:   # then what each is part of: a budget here or in the sheet, as the list shows it
        for n, item, part_of in placed:
            if part_of is None:
                continue
            try:
                parent = None
                if part_of:
                    found = [b for b in Budget.objects.all() if key(part_of) in (key(b), key(b.number) if b.number else None)]
                    parent = lookups.one(found, n, 'budget', part_of)
                    if parent.pk == item.pk or item.pk in parent.chain_pks():
                        raise ValidationError(f'{at(n)}: {item} can\'t be part of itself.')
                Budget.objects.filter(pk=item.pk).update(parent=parent)
            except ValidationError as exc:
                problems += exc.messages
    return made, changed, [], problems


def import_budgets(sent):
    """The budgets in the Excel or CSV file ``sent``: (made, changed). All or nothing: any row that is wrong and
    nothing is imported (a ValidationError saying which rows)."""
    rows = sheets.read(sent, SHEET)
    if not rows:
        raise ValidationError(f'There are no budgets in {sent.name}.')
    if 'name' not in rows[0][1]:
        raise ValidationError(f'{sent.name} has no "Name" column (the sheet "{SHEET}", as ⬇ Excel makes it).')
    with transaction.atomic():
        made, changed, _, problems = apply_budgets(rows)
        if problems:
            transaction.set_rollback(True)
    if problems:
        sheets.refuse(problems)
    return made, changed
