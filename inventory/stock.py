"""The only way stock changes: stock is the records of an item definition (``records``), each change keeps a Movement,
and quantities never go below zero. What comes in is a record of its own (a delivery: from its order line); what goes
out is taken from the oldest records in that location first; moving part of a record splits it.

An item definition that is an asset is kept one by one, each piece a record with its asset tag: those come in with
``add_tagged`` and are moved, sent away or retired one by one, on their own page (``records.service``)."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Movement


def amount(value, allow_zero=False):
    """A quantity from a form: a positive number (or zero, if ``allow_zero``)."""
    try:
        n = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise ValidationError(f'"{value}" is not a number.')
    if not n.is_finite() or n < 0 or (n == 0 and not allow_zero):
        raise ValidationError('Give a quantity above zero.' if not allow_zero else 'Give a quantity of zero or more.')
    return n


def _records(definition, location):
    """The untagged records of ``definition`` in ``location`` that hold something, oldest first, locked."""
    from records.models import Record
    return list(Record.objects.select_for_update().filter(definition=definition, location=location, tag=None, quantity__gt=0)
                .order_by('created_at', 'pk'))


def _counted(definition):
    if definition.is_asset:
        raise ValidationError(f'{definition} is an asset: each one is a record of its own, moved or retired on its page.')
    if not definition.physical:
        raise ValidationError(f'{definition} is a {definition.get_kind_display().lower()}: it is not kept in stock.')


def _take(definition, location, quantity):
    """Take ``quantity`` out of the records in ``location``, the oldest first: [(record, taken)]."""
    rows = _records(definition, location)
    have = sum(r.quantity for r in rows)
    if have < quantity:
        raise ValidationError(f'There are only {Decimal(have).normalize():f} {definition.unit} of {definition} in {location}.')
    taken = []
    for row in rows:
        part = min(row.quantity, quantity)
        row.quantity -= part
        row.save(update_fields=['quantity'])
        taken.append((row, part))
        quantity -= part
        if not quantity:
            break
    return taken


def _tidy(definition, location):
    """Records used up are gone (their movements stay)."""
    from records.models import Record
    Record.objects.filter(definition=definition, location=location, tag=None, quantity=0).delete()


def _new(definition, quantity, location, order_line=None, price=None, **fields):
    from records.models import Record
    return Record.objects.create(definition=definition, quantity=quantity, location=location, order_line=order_line,
                                 price=price, **fields)


@transaction.atomic
def add(definition, quantity, location, user, note='', kind=Movement.Kind.ADDED, reference='', url='', order_line=None):
    """Stock coming in, as a record of its own: found, made, or received for an order (``kind`` RECEIVED, ``order_line``)."""
    _counted(definition)
    quantity = amount(quantity)
    if location is None:
        raise ValidationError(f'Say where the {definition} goes.')
    _new(definition, quantity, location, order_line, order_line.price if order_line else None)
    return Movement.objects.create(definition=definition, kind=kind, quantity=quantity, target=location, note=note[:300],
                                   reference=reference, url=url, user=user)


def tags(text):
    """The asset tags in ``text``: separated by commas, spaces or lines."""
    return [t for t in (x.strip() for x in str(text or '').replace(',', ' ').split()) if t]


@transaction.atomic
def add_tagged(definition, given, location, user, note='', kind=Movement.Kind.ADDED, reference='', url='', order_line=None):
    """Pieces of an asset coming in: a record each, with its asset tag (``given``: a list, or text of them). Returns them."""
    from records.models import Record, RecordEvent
    given = tags(given) if isinstance(given, str) else list(given)
    if not given:
        raise ValidationError(f'Give each {definition} its asset tag.')
    if len({t.lower() for t in given}) != len(given):
        raise ValidationError('An asset tag is given twice.')
    taken = [t for t in given if Record.objects.filter(tag__iexact=t).exists()]
    if taken:
        raise ValidationError(f'There is already an asset {", ".join(taken)}.')
    if definition.physical and location is None:
        raise ValidationError(f'Say where the {definition} goes.')
    made = [_new(definition, Decimal(1), location if definition.physical else None, order_line,
                 order_line.price if order_line else definition.price, tag=t[:100]) for t in given]
    for record in made:
        RecordEvent.objects.create(record=record, kind=RecordEvent.Kind.RECEIVED if order_line else RecordEvent.Kind.NOTE, user=user,
                                   note=(f'{reference}' + (f', location {location.path}' if location else '')) if order_line else (note or 'added')[:300])
    if definition.physical:
        Movement.objects.create(definition=definition, kind=kind, quantity=len(made), target=location, note=note[:300],
                                reference=reference, url=url, user=user)
    return made


def add_other(definition, quantity, user, order_line=None):
    """Something bought that is no thing (a service, a subscription, a licence): a record of it, never stock."""
    return _new(definition, amount(quantity), None, order_line, order_line.price if order_line else definition.price)


@transaction.atomic
def move(definition, quantity, source, target, user, note=''):
    _counted(definition)
    quantity = amount(quantity)
    if source == target:
        raise ValidationError('Pick another location to move it to.')
    for row, part in _take(definition, source, quantity):
        if row.quantity == 0:              # all of it: the record goes
            row.quantity, row.location = part, target
            row.save(update_fields=['quantity', 'location'])
        else:                              # part of it: split off, as of the same delivery
            _new(definition, part, target, row.order_line, row.price, created_at=row.created_at)
    return Movement.objects.create(definition=definition, kind=Movement.Kind.MOVED, quantity=quantity, source=source, target=target,
                                   note=note[:300], user=user)


@transaction.atomic
def use(definition, quantity, source, user, note=''):
    """Stock going out: used, scrapped, sent away."""
    _counted(definition)
    quantity = amount(quantity)
    _take(definition, source, quantity)
    _tidy(definition, source)
    return Movement.objects.create(definition=definition, kind=Movement.Kind.USED, quantity=quantity, source=source, note=note[:300], user=user)


@transaction.atomic
def use_any(family, quantity, source, user, note=''):
    """Stock of a family (or a branch of one) going out: from the item definitions of it in ``source``, the most stocked first."""
    from django.db.models import Sum
    from records.models import Record
    quantity = amount(quantity)
    have = (Record.objects.filter(definition__in=family.members(), location=source, tag=None).values('definition')
            .annotate(n=Sum('quantity')).filter(n__gt=0).order_by('-n'))
    if sum(h['n'] for h in have) < quantity:
        raise ValidationError(f'There are only {Decimal(sum(h["n"] for h in have)).normalize():f} {family.unit} of {family} in {source}.')
    members = {d.pk: d for d in family.members()}
    for h in have:
        taken = min(h['n'], quantity)
        use(members[h['definition']], taken, source, user, note)
        quantity -= taken
        if not quantity:
            break


@transaction.atomic
def count(definition, location, quantity, user, note=''):
    """What is really there after counting: the stock in ``location`` becomes ``quantity`` (what is missing is taken from the
    oldest records, what is more is a record of its own); the movement keeps the difference."""
    _counted(definition)
    quantity = amount(quantity, allow_zero=True)
    difference = quantity - sum(r.quantity for r in _records(definition, location))
    if difference > 0:
        _new(definition, difference, location)
    elif difference < 0:
        _take(definition, location, -difference)
        _tidy(definition, location)
    return Movement.objects.create(definition=definition, kind=Movement.Kind.COUNTED, quantity=difference, target=location,
                                   note=note[:300], user=user)


def in_stock(definition):
    """[(location, quantity)] where ``definition`` is, the most first."""
    from django.db.models import Sum
    from records.models import Record
    from .models import Location
    rows = (Record.objects.filter(definition=definition, quantity__gt=0).exclude(location=None).values('location')
            .annotate(n=Sum('quantity')).order_by('-n'))
    places = Location.objects.in_bulk([r['location'] for r in rows])
    return [(places[r['location']], r['n']) for r in rows]
