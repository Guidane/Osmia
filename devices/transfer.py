"""A device as a file, and a file taken in as a device: so a device (its connectors and their pins) can be described
outside Osmia (by hand, or by another program or AI reading a datasheet or a schematic) and brought in. ``FORMAT``
says what such a file holds."""
from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Family, definition_or_family
from inventory.picker import with_gender

from .models import COLOURS, SET_TYPES, Connector, Device, Pin

KIND = 'osmia device'   # what a file of a device says it is
SIDES = ('top', 'right', 'bottom', 'left')

FORMAT = """# Osmia device file

A device for Osmia (a board, an instrument, a power supply: anything harnesses plug into) as one JSON file (UTF-8),
with its connectors and their pins. Osmia takes it in on the device list (⬆ Import) as a new device. ⬇ JSON on a
device's page gives a file of this kind to compare with.

```json
{
  "kind": "osmia device",
  "version": 1,
  "number": "LOAD-2",
  "name": "Load board",
  "origin": "in_house",
  "manufacturer": "",
  "model": "",
  "description": "",
  "notes": "",
  "connectors": [
    {"designator": "J1", "name": "Bus in", "family": "D-sub 9 / socket", "side": "left",
     "pins": [
       {"number": "1", "signal": "+24 V"},
       {"number": "6", "signal": "0 V"},
       {"number": "2", "signal": "CAN H", "set": "CAN", "set_type": "Twisted", "group": "Bus"},
       {"number": "7", "signal": "CAN L", "set": "CAN", "set_type": "Twisted", "group": "Bus"},
       {"number": "5", "signal": "Shield", "description": "to the case"}
     ]}
  ]
}
```

Only `number` and `name` are needed; everything else may be left out.

## The device

- `number`: its device number, unique in Osmia (at most 100 characters). A file with a number Osmia has already is
  refused.
- `name`: what it is called.
- `origin`: `in_house` (designed and made here) or `external` (bought). Left out: `in_house`.
- `manufacturer`, `model`: for one that is bought.
- `definition`: the item number it is bought or stocked as, when Osmia knows it.
- `description`, `notes`: free text.

## connectors

- `designator`: the connector's name on the device (J1, X3, CN2). Unique on the device.
- `name`: what it is for ("Bus in", "Mains").
- `family`: its connector family, with its gender after " / " ("D-sub 9 / socket", "M12 A-coded 8 / pin"), or the
  item number of an exact part. Pin: the connector has pins; socket: it has sockets. The families this Osmia knows are
  listed at the end of this file. Leave it out when unknown: the device is still made, without the connector's face.
- `side`: where it sits on the device as drawn: one of SIDES_HERE. Leave it out to let Osmia place it.
- `pins`: its contacts that are used (or all of them).

## pins

- `number`: the contact number as printed on the connector ("1", "A", "12"). Unique on the connector.
- `signal`: what it carries ("+24 V", "0 V", "CAN H").
- `set`: a short name (at most 20 characters) shared by pins whose wires go together: a twisted pair, a shielded pair.
- `set_type`: how a set's wires go together: one of SET_TYPES_HERE. The same for every pin of a set.
- `group`: a name tag over several sets (at most 40 characters): "Channel 1".
- `description`: anything else about the pin.
"""


def describe():
    """``FORMAT`` with this Osmia's set types, sides and connector families filled in."""
    text = FORMAT.replace('SET_TYPES_HERE', ', '.join(f'`{t}`' for t in SET_TYPES))
    text = text.replace('SIDES_HERE', ', '.join(f'`{s}`' for s in SIDES))
    lines = ['', '## The connector families of this Osmia', '']
    for family in Family.objects.prefetch_related('branches').order_by('name'):
        genders = [b.name for b in family.branches.all()]
        lines.append(f'- {family.name}' + (f' (genders: {", ".join(genders)})' if genders else ''))
    if len(lines) == 3:
        lines.append('(none yet)')
    return text + '\n'.join(lines) + '\n'


def _keep(pairs):
    return {k: v for k, v in pairs if v not in ('', None)}


def export_device(device):
    """``device`` as a file's data (``import_device`` takes it in)."""
    return {'kind': KIND, 'version': 1, **_keep((
        ('number', device.number), ('name', device.name), ('origin', device.origin), ('manufacturer', device.manufacturer),
        ('model', device.model), ('definition', device.used_name), ('description', device.description), ('notes', device.notes))),
        'connectors': [{**_keep((('designator', c.designator), ('name', c.name), ('family', c.used_name), ('side', c.side))),
                        'pins': [_keep((('number', p.number), ('signal', p.signal), ('set', p.wire_set),
                                        ('set_type', p.set_type if p.wire_set else ''), ('group', p.wire_group),
                                        ('description', p.description))) for p in c.ordered_pins()]}
                       for c in device.connectors.select_related('definition', 'family').prefetch_related('pins')]}


def _text(value, longest):
    return ' '.join(str(value if value is not None else '').split())[:longest]


def import_device(data):
    """A device made from a file's data (see ``FORMAT``). Returns (device, notes): notes say what was not taken in as it
    was (a family or item number this Osmia doesn't know). Refused, with nothing made, when the file is not a device,
    its number is taken, or a connector or pin can't be read."""
    if not isinstance(data, dict) or data.get('kind') not in (None, KIND) or not isinstance(data.get('connectors', []), list):
        raise ValidationError('That is not a device file.')
    number, name = _text(data.get('number'), 100), _text(data.get('name'), 200)
    if not number or not name:
        raise ValidationError('A device file gives the device\'s "number" and "name".')
    if Device.objects.filter(number__iexact=number).exists():
        raise ValidationError(f'There is already a device {number}.')
    unknown = {}

    def used(text, where):
        text = _text(text, 100)
        if not text:
            return None
        found = definition_or_family(with_gender(text))
        if found is None:
            unknown.setdefault(text, where)
        return found

    origin = str(data.get('origin') or '').strip().lower().replace('-', '_').replace(' ', '_')
    origin = {'in_house': 'in_house', 'inhouse': 'in_house', 'external': 'external', 'bought': 'external'}.get(origin, 'in_house')
    with transaction.atomic():
        device = Device(number=number, name=name, origin=origin, manufacturer=_text(data.get('manufacturer'), 200),
                        model=_text(data.get('model'), 200), description=str(data.get('description') or ''),
                        notes=str(data.get('notes') or ''), colour=COLOURS[Device.objects.count() % len(COLOURS)])
        device.used = used(data.get('definition'), 'the device')
        device.save()
        taken = set()
        for i, c in enumerate(data.get('connectors') or [], 1):
            if not isinstance(c, dict):
                raise ValidationError(f'Connector {i}: not one Osmia can read.')
            designator = _text(c.get('designator'), 30)
            if not designator:
                raise ValidationError(f'Connector {i}: give its "designator" (J1, X3).')
            if designator.lower() in taken:
                raise ValidationError(f'Connector {designator} is there twice.')
            taken.add(designator.lower())
            side = str(c.get('side') or '').strip().lower()
            connector = Connector(device=device, designator=designator, name=_text(c.get('name'), 200), position=i - 1,
                                  side=side if side in SIDES else '')
            connector.used = used(c.get('family') or c.get('definition'), f'connector {designator}')
            connector.save()
            numbers, sets = set(), {}
            pins = c.get('pins') or []
            if not isinstance(pins, list):
                raise ValidationError(f'Connector {designator}: its "pins" are a list.')
            for j, p in enumerate(pins, 1):
                if not isinstance(p, dict):
                    p = {'number': p}   # (just its numbers)
                where = f'Connector {designator}, pin {j}'
                pin = _text(p.get('number'), 20)
                if not pin:
                    raise ValidationError(f'{where}: give its "number".')
                if pin.lower() in numbers:
                    raise ValidationError(f'Connector {designator}: pin {pin} is there twice.')
                numbers.add(pin.lower())
                wire_set = _text(p.get('set'), 20)
                kind = next((t for t in SET_TYPES if t.lower() == _text(p.get('set_type'), 30).lower()), None)
                if p.get('set_type') and kind is None:
                    raise ValidationError(f'{where}: "{p.get("set_type")}" is not a set type ({", ".join(SET_TYPES)}).')
                kind = kind or 'Straight'
                if wire_set and sets.setdefault(wire_set, kind) != kind:
                    raise ValidationError(f'Connector {designator}, set {wire_set}: its pins go together in one way, '
                                          f'not {sets[wire_set]} and {kind}.')
                Pin.objects.create(connector=connector, number=pin, signal=_text(p.get('signal'), 100),
                                   wire_set=wire_set, set_type=kind if wire_set else 'Straight',
                                   wire_group=_text(p.get('group'), 40), description=_text(p.get('description'), 200))
    notes = [f'"{text}" ({where}) is no family or item number Osmia knows; left out.' for text, where in unknown.items()]
    return device, notes
