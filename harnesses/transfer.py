"""A harness as a file, and a file taken in as a harness: so a harness can be made outside Osmia (by hand, or by
another program or AI reading a drawing or a wire list) and brought in. ``FORMAT`` says what such a file holds."""
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Family, definition_or_family
from inventory.picker import with_gender

from .models import COLOURS, SET_TYPES, Harness, HarnessEnd, HarnessGroup, HarnessItem, Wire

KIND = 'osmia harness'   # what a file of a harness says it is

FORMAT = """# Osmia harness file

A harness for Osmia as one JSON file (UTF-8). Osmia takes it in on the harness list (⬆ Import), as a new harness
(in the setup picked there, if any). ⬇ JSON on a harness's page gives a file of this kind to compare with.

```json
{
  "kind": "osmia harness",
  "version": 1,
  "name": "Controller to load board",
  "description": "",
  "notes": "",
  "connectors": [
    {"designator": "P1", "family": "D-sub 9 / socket", "side": "left"},
    {"designator": "P2", "family": "D-sub 9 / pin", "side": "right"}
  ],
  "wires": [
    {"from": "P1", "from_pin": "1", "to": "P2", "to_pin": "1", "signal": "+24 V", "colour": "red",
     "gauge": "22 AWG", "length": 450, "group": "Power", "set": "PWR", "set_type": "Twisted"},
    {"from": "P1", "from_pin": "5", "to": "P2", "to_pin": "5", "signal": "Shield", "colour": "grey",
     "set": "DATA", "set_type": "Shield"}
  ],
  "groups": [{"name": "Power", "length": 450, "bundled": 200}],
  "items": [{"definition": "HS-6-BLK", "quantity": 0.2, "note": "heat shrink"}]
}
```

Only `wires` is needed; everything else may be left out.

## connectors

- `designator`: the connector's name on the harness (P1, J3, X12). Unique in the harness.
- `family`: its connector family, with its gender after " / " ("D-sub 9 / pin", "M12 A-coded 8 / socket"), or the
  item number of an exact part. Pin: the connector has pins; socket: it has sockets. The families this Osmia knows are
  listed at the end of this file. Leave it out when unknown: the harness is still made, without the connector's face.
- `side`: `left` or `right`, where it is drawn. Leave it out to let Osmia choose.

A connector a wire names that is not in `connectors` is made by Osmia, without a family.

## wires

One entry per wire, from a contact of a connector to a contact of a connector.

- `from`, `to`: the connectors' designators. The same one on both: a loopback.
- `from_pin`, `to_pin`: the contact numbers as printed on the connector ("1", "A", "12").
- `signal`: what the wire carries ("+24 V", "0 V", "CAN H"). `to_signal`: a loopback's signal at its other end.
- `colour`: one of COLOURS_HERE.
- `gauge`: "22 AWG", "0.5 mm²". A bare number is taken as AWG.
- `length`: in mm, a number.
- `definition`: the item number of the wire it is cut from, when known.
- `set`: a short name (at most 20 characters) shared by the wires that go together: a twisted pair, a shielded cable.
- `set_type`: how a set's wires go together: one of SET_TYPES_HERE. Give every wire of a set the same type, but
  `Shield` for a shielded set's drain or shield wire.
- `group`: a name tag over several sets (at most 40 characters): "Channel 1".

A splice is several wires from the same contact: one entry for each wire.

## groups

For each `group` named by the wires, optionally: `length` (its total length, mm) and `bundled` (how much of that,
from its left-hand connector, runs bundled together with the other sets, mm).

## items

Other things the harness is made of: `definition` (an item number Osmia knows), `quantity`, `note`.
"""


def describe():
    """``FORMAT`` with this Osmia's colours, set types and connector families filled in."""
    text = FORMAT.replace('COLOURS_HERE', ', '.join(f'`{c}`' for c in COLOURS))
    text = text.replace('SET_TYPES_HERE', ', '.join(f'`{t}`' for t in SET_TYPES))
    lines = ['', '## The connector families of this Osmia', '']
    for family in Family.objects.prefetch_related('branches').order_by('name'):
        genders = [b.name for b in family.branches.all()]
        lines.append(f'- {family.name}' + (f' (genders: {", ".join(genders)})' if genders else ''))
    if len(lines) == 3:
        lines.append('(none yet)')
    return text + '\n'.join(lines) + '\n'


def export_harness(harness):
    """``harness`` as a file's data (``import_harness`` takes it in)."""
    data = harness.snapshot()
    sides = dict(harness.ends.values_list('designator', 'side'))
    return {'kind': KIND, 'version': 1, 'number': harness.number, **({'setup': str(harness.setup)} if harness.setup else {}),
            'name': data['name'], 'description': data['description'], 'notes': data['notes'],
            'connectors': [{'designator': e['designator'], 'family': e['definition'],
                            **({'side': sides[e['designator']]} if sides.get(e['designator']) else {})} for e in data['ends']],
            'wires': [{k: v for k, v in (('from', w['from']), ('from_pin', w['from_pin']), ('to', w['to']),
                                         ('to_pin', w['to_pin']), ('signal', w['signal']), ('to_signal', w['to_signal']),
                                         ('colour', w['colour']), ('gauge', w['gauge']), ('length', _plain(w['length'])),
                                         ('definition', w['definition']), ('group', w.get('group', '')), ('set', w['set']),
                                         ('set_type', w['set_type'] if w['set'] else '')) if v not in ('', None)}
                      for w in data['wires']],
            'groups': [{k: v for k, v in (('name', g['name']), ('length', _plain(g['length'])), ('bundled', _plain(g['bundled'])))
                        if v is not None} for g in data.get('groups', [])],
            'items': [{'definition': i['definition'], 'quantity': _plain(i['quantity']), **({'note': i['note']} if i['note'] else {})}
                      for i in data['items']]}


def _plain(text):
    """A number kept as text in a snapshot, as a plain JSON number."""
    if text in (None, ''):
        return None
    value = Decimal(text).normalize()
    return int(value) if value == value.to_integral() else float(value)


_COLOUR_WORDS = {'gray': 'grey', 'purple': 'violet', 'gn/ye': 'green/yellow', 'green-yellow': 'green/yellow',
                 'green yellow': 'green/yellow', 'yellow/green': 'green/yellow', 'ge/gn': 'green/yellow', 'gnye': 'green/yellow',
                 'bk': 'black', 'bn': 'brown', 'rd': 'red', 'og': 'orange', 'ye': 'yellow', 'gn': 'green', 'bu': 'blue',
                 'vt': 'violet', 'gy': 'grey', 'wh': 'white', 'blk': 'black', 'brn': 'brown', 'red': 'red', 'org': 'orange',
                 'yel': 'yellow', 'grn': 'green', 'blu': 'blue', 'vio': 'violet', 'gry': 'grey', 'wht': 'white'}


def _colour(value):
    text = ' '.join(str(value or '').lower().split())
    if not text:
        return ''
    if text in COLOURS:
        return text
    return _COLOUR_WORDS.get(text) or _COLOUR_WORDS.get(text.replace(' ', '')) or ''


def _set_type(value):
    text = ' '.join(str(value or '').split()).lower()
    return next((t for t in SET_TYPES if t.lower() == text), None)


def _number(value, where, what):
    """A length or quantity: a number, or text such as "450 mm" / "0,5"; None when not given."""
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValidationError(f'{where}: the {what} "{value}" is not a number.')
    text = str(value).strip().replace(',', '.')
    match = re.fullmatch(r'([0-9]*\.?[0-9]+)\s*(mm)?', text, re.I)
    try:
        number = Decimal(match.group(1)) if match else Decimal(text)
    except InvalidOperation:
        raise ValidationError(f'{where}: the {what} "{value}" is not a number.')
    if not number.is_finite() or number < 0:
        raise ValidationError(f'{where}: the {what} can\'t be below zero.')
    return number


def _text(value, longest):
    return ' '.join(str(value if value is not None else '').split())[:longest]


def import_harness(data, setup):
    """A harness made from a file's data (see ``FORMAT``) in ``setup`` (None: in no setup). Returns (harness, notes): notes say what was
    not taken in as it was (a family or item number this Osmia doesn't know, a colour it has not). Refused, with
    nothing made, when the file is not a harness or a wire can't be read."""
    if not isinstance(data, dict) or not isinstance(data.get('wires'), list) or (data.get('kind') not in (None, KIND)):
        raise ValidationError('That is not a harness file: it has no list of "wires".')
    notes = []
    unknown = {}

    def used(name, where):
        name = _text(name, 100)
        if not name:
            return None
        found = definition_or_family(with_gender(name))
        if found is None:
            unknown.setdefault(name, where)
        return found

    with transaction.atomic():
        name = _text(data.get('name'), 200) or 'Imported harness'
        harness = Harness.objects.create(setup=setup, name=name, description=str(data.get('description') or ''),
                                         notes=str(data.get('notes') or ''))
        ends = {}

        def end(designator, where):
            designator = _text(designator, 30)
            if not designator:
                raise ValidationError(f'{where}: which connector?')
            key = designator.lower()
            if key not in ends:
                ends[key] = HarnessEnd.objects.create(harness=harness, designator=designator, position=len(ends))
            return ends[key]

        for i, c in enumerate(data.get('connectors') or data.get('ends') or [], 1):
            if not isinstance(c, dict):
                raise ValidationError(f'Connector {i}: not one Osmia can read.')
            where = f'Connector {i}'
            e = end(c.get('designator') or c.get('name'), where)
            e.used = used(c.get('family') or c.get('definition') or c.get('part'), f'connector {e.designator}')
            side = str(c.get('side') or '').lower()
            e.side = side if side in ('left', 'right') else ''
            e.save()
        joined = {}
        for i, w in enumerate(data['wires'], 1):
            where = f'Wire {i}'
            if not isinstance(w, dict):
                raise ValidationError(f'{where}: not one Osmia can read.')
            a, b = end(w.get('from'), where), end(w.get('to'), where)
            from_pin, to_pin = _text(w.get('from_pin'), 20), _text(w.get('to_pin'), 20)
            kind = _set_type(w.get('set_type'))
            if w.get('set_type') and kind is None:
                raise ValidationError(f'{where}: "{w.get("set_type")}" is not a set type ({", ".join(SET_TYPES)}).')
            if not (from_pin or to_pin) or (not (from_pin and to_pin) and kind != 'Shield'):
                raise ValidationError(f'{where}: a wire goes from a contact to a contact (give "from_pin" and "to_pin").')
            if a == b and from_pin.lower() == to_pin.lower():
                raise ValidationError(f'{where}: a loopback goes to another contact.')
            pair = frozenset(((a.pk, from_pin.lower()), (b.pk, to_pin.lower())))
            if pair in joined:
                raise ValidationError(f'{where}: {a}:{from_pin} and {b}:{to_pin} are joined already (wire {joined[pair]}).')
            joined[pair] = i
            colour = _colour(w.get('colour') or w.get('color'))
            if (w.get('colour') or w.get('color')) and not colour:
                notes.append(f'{where}: the colour "{w.get("colour") or w.get("color")}" is not one Osmia has; left out.')
            gauge = _text(w.get('gauge'), 20)
            wire_set = _text(w.get('set'), 20)
            wire = Wire(harness=harness, from_end=a, from_pin=from_pin, to_end=b, to_pin=to_pin,
                        signal=_text(w.get('signal'), 100), to_signal=_text(w.get('to_signal'), 100),
                        wire_group=_text(w.get('group'), 40), wire_set=wire_set,
                        set_type=(kind or 'Straight') if wire_set else 'Straight', colour=colour,
                        gauge=f'{gauge} AWG' if gauge.isdigit() else gauge, length=_number(w.get('length'), where, 'length'))
            if kind == 'Shield' and not wire_set:
                raise ValidationError(f'{where}: a shield wire is the shield of a set: give its "set".')
            wire.used = used(w.get('definition'), f'wire {i}')
            wire.save()
        sets = {}
        for wire in harness.wires.exclude(wire_set=''):   # a set goes together one way; its group is its first wire's
            sets.setdefault(wire.wire_set, []).append(wire)
        for name, wires in sets.items():
            types = {w.set_type for w in wires if w.set_type != 'Shield'}
            if len(types) > 1:
                raise ValidationError(f'Set {name}: its wires go together in one way, not {" and ".join(sorted(types))}.')
            group = next((w.wire_group for w in wires if w.wire_group), '')
            harness.wires.filter(wire_set=name).update(wire_group=group)
        named = set(harness.wires.exclude(wire_group='').values_list('wire_group', flat=True))
        for i, g in enumerate(data.get('groups') or [], 1):
            if not isinstance(g, dict) or _text(g.get('name'), 40) not in named:
                continue
            length, bundled = _number(g.get('length'), f'Group {i}', 'length'), _number(g.get('bundled'), f'Group {i}', 'bundled length')
            if length is not None and bundled is not None and bundled > length:
                raise ValidationError(f'Group {g["name"]}: it can\'t run bundled for longer than it is.')
            HarnessGroup.objects.update_or_create(harness=harness, name=_text(g['name'], 40), defaults={'length': length, 'bundled': bundled})
        for i, it in enumerate(data.get('items') or [], 1):
            if not isinstance(it, dict):
                continue
            found = used(it.get('definition'), f'item {i}')
            quantity = _number(it.get('quantity'), f'Item {i}', 'quantity')
            if found is None or not quantity:
                continue
            line = HarnessItem(harness=harness, quantity=quantity, note=_text(it.get('note'), 200))
            line.used = found
            line.save()
    for name, where in unknown.items():
        notes.append(f'"{name}" ({where}) is no family or item number Osmia knows; left out.')
    return harness, notes
