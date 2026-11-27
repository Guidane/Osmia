"""Budgets from an Excel file: the sheet "Budgets" as ⬇ Excel makes it (its columns that are counted, not kept, such as
what is spent, are left out). Each row is the budget with its number (with no number: the one with its name in the same
budget): changed when there is one, else made. A column left out of the sheet leaves that of each budget as it is; an
empty cell empties it. "Part of" names a budget as the list shows it ("FY26 2026"), here or in the sheet."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from accounts.models import Department, User
from setups.models import Setup
from web import sheets

from .models import Budget

SHEET = 'Budgets'


def _key(text):
    return ' '.join(str(text or '').split()).lower()


def _one(found, n, what, text):
    found = list(found[:2])
    if len(found) != 1:
        raise ValidationError(f'Row {n}: there is {"no" if not found else "more than one"} {what} "{text}".')
    return found[0]


def _setup(text, n):
    return _one(Setup.objects.filter(Q(code__iexact=text) | Q(name__iexact=text)) or
                [s for s in Setup.objects.all() if _key(s) == _key(text)], n, 'setup', text)


def _owner(text, n):
    found = User.objects.filter(Q(username__iexact=text) | Q(email__iexact=text))
    return _one(found if found.exists() else [u for u in User.objects.all() if _key(u) == _key(text)], n, 'user', text)


def _department(text, n):
    return _one([d for d in Department.objects.all() if _key(text) in (_key(d.name), _key(d.path))], n, 'department', text)


def import_budgets(sent):
    """The budgets in the Excel file ``sent``: (made, changed). All or nothing: any row that is wrong and nothing is
    imported (a ValidationError saying which rows)."""
    rows = sheets.read(sent, SHEET)
    if not rows:
        raise ValidationError(f'There are no budgets in {sent.name}.')
    if 'name' not in rows[0][1]:
        raise ValidationError(f'{sent.name} has no "Name" column (the sheet "{SHEET}", as ⬇ Excel makes it).')
    problems, placed, seen = [], [], {}
    made = changed = 0
    with transaction.atomic():
        for n, row in rows:   # each budget, without what it is part of yet
            try:
                number, name, part_of = sheets.text(row, 'number', 50), sheets.text(row, 'name', 100), sheets.text(row, 'part of')
                if not name:
                    raise ValidationError(f'Row {n}: it has no name.')
                key = _key(number) if number else _key(f'{part_of} › {name}')
                if key in seen:
                    raise ValidationError(f'Row {n}: budget {number or name} is in row {seen[key]} already.')
                seen[key] = n
                if number:
                    item = Budget.objects.filter(number__iexact=number).first()
                else:
                    item = next((b for b in Budget.objects.filter(number='', name__iexact=name).select_related('parent')
                                 if _key(b.parent or '') == _key(part_of)), None)
                new = item is None
                item = item or Budget()
                item.number, item.name = number, name
                if 'amount' in row:
                    item.amount = sheets.number(row, 'amount', n, 'amount') or 0
                if 'setup' in row:
                    item.setup = _setup(sheets.text(row, 'setup'), n) if sheets.text(row, 'setup') else None
                if 'owner' in row:
                    item.owner = _owner(sheets.text(row, 'owner'), n) if sheets.text(row, 'owner') else None
                if 'department' in row:
                    item.department = _department(sheets.text(row, 'department'), n) if sheets.text(row, 'department') else None
                for header, field in (('starts', 'starts_on'), ('ends', 'ends_on')):
                    if header in row:
                        setattr(item, field, sheets.day(row, header, n, f'{header} date'))
                if item.starts_on and item.ends_on and item.ends_on < item.starts_on:
                    raise ValidationError(f'Row {n}: it ends before it starts.')
                if 'notes' in row:
                    item.notes = sheets.text(row, 'notes')
                if sheets.yes(row, 'active', n, 'active') is not None:
                    item.active = sheets.yes(row, 'active', n, 'active')
                try:
                    item.full_clean(exclude=['parent', 'setup', 'owner', 'department'])
                except ValidationError as exc:
                    raise ValidationError([f'Row {n}: {m}' for m in exc.messages])
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
                        found = [b for b in Budget.objects.all() if _key(part_of) in (_key(b), _key(b.number) if b.number else None)]
                        parent = _one(found, n, 'budget', part_of)
                        if parent.pk == item.pk or item.pk in parent.chain_pks():
                            raise ValidationError(f'Row {n}: {item} can\'t be part of itself.')
                    Budget.objects.filter(pk=item.pk).update(parent=parent)
                except ValidationError as exc:
                    problems += exc.messages
        if problems:
            transaction.set_rollback(True)
    if problems:
        sheets.refuse(problems)
    return made, changed
