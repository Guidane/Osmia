"""An Osmia data file: one JSON file with any of Osmia's records (vendors, locations, categories, departments,
connector families, item definitions, projects, setups and what is placed in them, budgets, devices, harnesses, stock,
assets, orders), made by hand, by another program, or by an AI from screenshots of an older Osmia or anything else
(see ``web.ai``). Taken in on the Import page: all of it, or nothing when anything in it is wrong.

Each record is the one Osmia already has with its name, number, code, path or asset tag (any case): changed (what the
file gives of it), else made. Devices, harnesses and orders already there are kept as they are."""
import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from . import lookups, sheets
from .lookups import key
from .sheets import at

KIND = 'osmia data'
ORDER = ['vendors', 'locations', 'categories', 'departments', 'connector_families', 'item_definitions', 'projects', 'setups',
         'budgets', 'devices', 'harnesses', 'stock', 'assets', 'orders']   # (what each names comes before it)


def read(sent):
    """The data of the file ``sent`` (refused when it is no JSON, or no data file)."""
    if sent is None:
        raise ValidationError('Pick an Osmia data file (.json).')
    try:
        data = json.loads(sent.read().decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError):
        raise ValidationError(f'{sent.name} is not an Osmia data file (JSON).')
    if not isinstance(data, dict) or (data.get('kind') not in (None, KIND)) or not any(k in data for k in ORDER):
        raise ValidationError(f'{sent.name} is not an Osmia data file: it has none of {", ".join(ORDER)}.')
    return data


def _entries(data, section):
    value = data.get(section) or []
    if not isinstance(value, list):
        raise ValidationError(f'"{section}" is not a list.')
    out = []
    for i, e in enumerate(value, 1):
        if not isinstance(e, dict):
            raise ValidationError(f'{section} {i}: not one Osmia can read.')
        out.append((f'{section} {i}', e))
    return out


def _as_columns(entry, keys):
    """A data file's entry as a sheet's row: its names as the sheet's column headers ("vendor_number": "vendor's
    number")."""
    return {keys.get(k, k.replace('_', ' ')): v for k, v in entry.items()}


def _choice(choices, value, n, what):
    from inventory.imports import choice
    found = choice(choices, value)
    if found is None:
        raise ValidationError(f'{at(n)}: "{value}" is not a {what} ({", ".join(str(s) for s, _ in choices)}).')
    return found


def _with(e, n, field, find):
    """What the entry names in ``field`` (found with ``find``), None when it names nothing; ``...`` when it leaves the
    field out."""
    if field not in e:
        return ...
    text = sheets.text(e, field)
    return find(text, n) if text else None


def _set(item, field, value):
    if value is not ...:
        setattr(item, field, value)


def _each(entries, apply_one):
    """``apply_one(where, entry)`` for each entry (True: made), each on its own: (made, changed, notes, problems)."""
    problems, notes, made, changed = [], [], 0, 0
    for n, e in entries:
        try:
            with transaction.atomic():
                new = apply_one(n, e, notes)
                if new is not None:
                    made, changed = made + bool(new), changed + (not new)
        except ValidationError as exc:
            problems += exc.messages
    return made, changed, notes, problems


def _departments(entries):
    from accounts.models import Department
    from inventory.imports import in_tree

    def one(n, e, notes):
        if not sheets.text(e, 'path') and not isinstance(e.get('path'), list):
            raise ValidationError(f'{at(n)}: it has no path ("Engineering / Test").')
        before = len(notes)
        node = in_tree(Department, e['path'], notes, 'Department')
        if 'description' in e:
            node.description = sheets.text(e, 'description')
        _set(node, 'manager', _with(e, n, 'manager', lookups.user))
        node.save()
        return len(notes) > before
    return _each(entries, one)


def _families(data):
    from inventory.faces import FILE_KIND, import_families
    value = data.get('connector_families')
    if isinstance(value, dict):
        value = value.get('families') or []
    try:
        made, _, kept = import_families({'kind': FILE_KIND, 'version': 1, 'families': value or [],
                                         'branches': (data.get('connector_families') or {}).get('branches', []) if isinstance(data.get('connector_families'), dict) else []})
    except ValidationError as exc:
        return 0, 0, [], [f'connector_families: {m}' for m in exc.messages]
    return made, 0, [f'{kept} connector families were there already: kept as they are.'] if kept else [], []


def _projects(entries):
    from work.models import Project
    placed = []

    def one(n, e, notes):
        code, name = sheets.text(e, 'code', 50), sheets.text(e, 'name', 200)
        if not name:
            raise ValidationError(f'{at(n)}: it has no name.')
        found = Project.objects.filter(code__iexact=code).first() if code else Project.objects.filter(code='', name__iexact=name).first()
        item = found or Project()
        item.code, item.name = code, name
        if sheets.text(e, 'status'):
            item.status = _choice(Project.Status.choices, sheets.text(e, 'status'), n, 'status')
        for field in ('description', 'notes'):
            if field in e:
                setattr(item, field, sheets.text(e, field))
        _set(item, 'owner', _with(e, n, 'owner', lookups.user))
        _set(item, 'department', _with(e, n, 'department', lookups.department))
        item.save()
        if 'part_of' in e:
            placed.append((n, item, sheets.text(e, 'part_of')))
        return found is None
    out = _each(entries, one)
    for n, item, part_of in placed:   # then what each is part of (here, or further down the file)
        try:
            parent = lookups.project(part_of, n) if part_of else None
            if parent is not None and (parent.pk == item.pk or item.pk in [p.pk for p in parent.chain()]):
                raise ValidationError(f'{at(n)}: {item} can\'t be part of itself.')
            Project.objects.filter(pk=item.pk).update(parent=parent)
        except ValidationError as exc:
            out[3].extend(exc.messages)
    return out


def _setups(entries):
    from setups.models import Setup

    def one(n, e, notes):
        code, name = sheets.text(e, 'code', 50), sheets.text(e, 'name', 200)
        if not name:
            raise ValidationError(f'{at(n)}: it has no name.')
        found = Setup.objects.filter(code__iexact=code).first() if code else Setup.objects.filter(code='', name__iexact=name).first()
        item = found or Setup()
        item.code, item.name = code, name
        if 'description' in e:
            item.description = sheets.text(e, 'description')
        _set(item, 'owner', _with(e, n, 'owner', lookups.user))
        _set(item, 'department', _with(e, n, 'department', lookups.department))
        _set(item, 'in_project', _with(e, n, 'project', lookups.project))
        item.save()
        return found is None
    return _each(entries, one)


def _placed_devices(entries):
    """Each setup's devices (``"devices": [{"key", "device", "label"}]``): placed in it (its diagram) under its key."""
    from setups.contents import rows
    from setups.models import Placement

    def one(n, e, notes):
        if not e.get('devices'):
            return None
        setup = lookups.setup(sheets.text(e, 'code') or sheets.text(e, 'name'), n)
        if not isinstance(e['devices'], list):
            raise ValidationError(f'{at(n)}: its "devices" is not a list.')
        now = rows(setup)
        for i, d in enumerate(e['devices'], 1):
            where = f'{n}, device {i}'
            if not isinstance(d, dict) or not sheets.text(d, 'key') or not sheets.text(d, 'device'):
                raise ValidationError(f'{where}: give its "key" (its name in the setup, D1) and its "device" (a device number).')
            k = sheets.text(d, 'key', 40)
            device = lookups.device(sheets.text(d, 'device'), where)
            spot = now.get(k)
            if spot and spot['kind'] != 'device':
                raise ValidationError(f'{where}: {k} is a harness in {setup} already.')
            if spot:
                Placement.objects.filter(setup=setup, key=k).update(device=device, label=sheets.text(d, 'label', 100))
            else:   # (side by side, four to a row)
                Placement.objects.create(setup=setup, key=k, kind='device', device=device, label=sheets.text(d, 'label', 100),
                                         x=60 + 300 * (len(now) % 4), y=60 + 220 * (len(now) // 4))
            now = rows(setup)
        return None
    return _each(entries, one)


def _devices(entries):
    from devices.models import Device
    from devices.transfer import import_device

    def one(n, e, notes):
        number = sheets.text(e, 'number')
        if number and Device.objects.filter(number__iexact=number).exists():
            notes.append(f'Device {number} is there already: kept as it is.')
            return None
        try:
            device, said = import_device({**e, 'kind': None})
        except ValidationError as exc:
            raise ValidationError([f'{at(n)}: {m}' for m in exc.messages])
        notes.extend(said)
        return True
    return _each(entries, one)


def _harnesses(entries):
    from harnesses.models import Harness
    from harnesses.transfer import import_harness
    from setups.contents import rows
    from setups.models import Placement

    def one(n, e, notes):
        setup = _with(e, n, 'setup', lookups.setup)
        setup = None if setup is ... else setup
        name = sheets.text(e, 'name', 200)
        if name and Harness.objects.filter(setup=setup, name__iexact=name).exists():
            notes.append(f'Harness {name}{" in " + str(setup) if setup else ""} is there already: kept as it is.')
            return None
        try:
            harness, said = import_harness({**e, 'kind': None}, setup)
        except ValidationError as exc:
            raise ValidationError([f'{at(n)}: {m}' for m in exc.messages])
        notes.extend(said)
        plugs = e.get('plugs') or {}
        if plugs and setup is None:
            raise ValidationError(f'{at(n)}: it plugs into devices of a setup: give its "setup".')
        if setup is not None:   # placed in its setup, plugged into its devices
            now, ends = rows(setup), {}
            designators = {h.designator.lower(): h for h in harness.ends.all()}
            for designator, target in (plugs.items() if isinstance(plugs, dict) else []):
                end = designators.get(str(designator).strip().lower())
                if end is None:
                    raise ValidationError(f'{at(n)}: it has no connector {designator} to plug in.')
                device_key, connector = (str(target).split(':', 1) + [''])[:2] if not isinstance(target, list) else (target + [''])[:2]
                spot = now.get(str(device_key).strip())
                if spot is None or spot['kind'] != 'device':
                    raise ValidationError(f'{at(n)}: {setup} has no device "{device_key}" for {designator} to plug into.')
                plug = None
                if str(connector).strip():
                    plug = next((c for c in _device_connectors(spot['device_id']) if c.designator.lower() == str(connector).strip().lower()), None)
                    if plug is None:
                        raise ValidationError(f'{at(n)}: device "{device_key}" has no connector {connector}.')
                ends[str(end.pk)] = [str(device_key).strip(), plug.pk] if plug else str(device_key).strip()
            k, i = f'H{harness.pk}', 1
            while k in now:
                k, i = f'H{harness.pk}-{i}', i + 1
            Placement.objects.create(setup=setup, key=k, kind='harness', harness=harness, ends=ends)
        return True
    return _each(entries, one)


def _device_connectors(device_id):
    from devices.models import Connector
    return Connector.objects.filter(device_id=device_id)


def _stock(entries, user):
    from inventory import stock

    def one(n, e, notes):
        definition = lookups.definition(sheets.text(e, 'item'), n)
        if not definition.physical or definition.is_asset:
            raise ValidationError(f'{at(n)}: {definition} is {"an asset: give it under assets" if definition.physical else "no thing kept in stock"}.')
        location = _location(sheets.text(e, 'location'), n)
        quantity = sheets.number(e, 'quantity', n, 'quantity')
        if quantity is None or quantity < 0:
            raise ValidationError(f'{at(n)}: give the quantity there (0 or more).')
        stock.count(definition, location, quantity, user, note='imported')
        return None
    return _each(entries, one)


def _location(text, n):
    from inventory.models import Location
    return lookups.one([l for l in Location.objects.all() if key(text) in (key(l.path), key(l.path.replace(' / ', '/')))], n, 'location', text)


def _assets(entries, user):
    from records.models import Record, RecordEvent
    from records.service import next_tag

    def one(n, e, notes):
        tag = sheets.text(e, 'tag', 100)
        item = Record.objects.filter(tag__iexact=tag).first() if tag else None
        if item is None:
            definition = lookups.definition(sheets.text(e, 'item'), n) if sheets.text(e, 'item') else None
            if definition is None:
                raise ValidationError(f'{at(n)}: give the asset\'s "item" (its item number) or the "tag" of one Osmia has.')
            if not definition.is_asset:
                raise ValidationError(f'{at(n)}: {definition} is not kept as assets (give it "is_asset": true under item_definitions).')
            item = Record(definition=definition, quantity=1, tag=tag or next_tag(definition.number), price=definition.price)
            new = True
        else:
            new = False
        for field in ('serial', 'asset_number', 'notes'):
            if field in e:
                setattr(item, field, sheets.text(e, field, 100 if field != 'notes' else None))
        if sheets.text(e, 'status'):
            item.status = _choice(Record.Status.choices, sheets.text(e, 'status'), n, 'status')
        _set(item, 'location', _with(e, n, 'location', _location))
        _set(item, 'keeper', _with(e, n, 'keeper', lookups.user))
        if 'price' in e:
            item.price = sheets.number(e, 'price', n, 'price')
        if 'calibrated_on' in e:
            item.calibrated_on = sheets.day(e, 'calibrated_on', n, 'calibration date')
        if 'calibration_months' in e:
            months = sheets.number(e, 'calibration_months', n, 'months between calibrations')
            item.calibration_months = int(months) if months else None
        if item.definition and item.definition.physical and item.location is None:
            raise ValidationError(f'{at(n)}: say where it is ("location").')
        item.save()
        if new:
            RecordEvent.objects.create(record=item, kind=RecordEvent.Kind.NOTE, user=user, note='imported')
        return new
    return _each(entries, one)


def _orders(entries, user):
    from orders.models import Order, OrderLine

    def one(n, e, notes):
        number = sheets.text(e, 'number', 20)
        if number and Order.objects.filter(number__iexact=number).exists():
            notes.append(f'Order {number} is there already: kept as it is.')
            return None
        order = Order(number=number, created_by=user)
        if sheets.text(e, 'status'):
            order.status = _choice(Order.Status.choices, sheets.text(e, 'status'), n, 'status')
        _set(order, 'vendor', _with(e, n, 'vendor', lookups.vendor))
        _set(order, 'budget', _with(e, n, 'budget', lookups.budget))
        _set(order, 'in_project', _with(e, n, 'project', lookups.project))
        order.vendor_reference = sheets.text(e, 'vendor_reference', 100)
        order.notes = sheets.text(e, 'notes')
        for field, what in (('ordered_on', 'order date'), ('expected_on', 'expected date'), ('received_on', 'received date')):
            setattr(order, field, sheets.day(e, field, n, what))
        if order.status != Order.Status.DRAFT and order.vendor is None:
            raise ValidationError(f'{at(n)}: an order that is placed has a vendor.')
        lines = e.get('lines') or []
        if not isinstance(lines, list) or not lines:
            raise ValidationError(f'{at(n)}: give its "lines" (each an item number, a quantity, a price).')
        order.save()
        for i, line in enumerate(lines, 1):
            where = f'{n}, line {i}'
            if not isinstance(line, dict):
                raise ValidationError(f'{where}: not one Osmia can read.')
            quantity = sheets.number(line, 'quantity', where, 'quantity')
            if not quantity or quantity <= 0:
                raise ValidationError(f'{where}: give how many ("quantity").')
            received = sheets.number(line, 'received', where, 'quantity received')
            if received is None:
                received = quantity if order.status == Order.Status.RECEIVED else Decimal(0)
            OrderLine.objects.create(order=order, definition=lookups.definition(sheets.text(line, 'item'), where), quantity=quantity,
                                     price=sheets.number(line, 'price', where, 'price'), received=min(received, quantity))
        return True
    return _each(entries, one)


def import_data(data, user):
    """Everything in a data file's ``data`` taken in: {section: (made, changed)} and the notes (what was made on the
    way, kept as it was). All or nothing: a ValidationError saying what is wrong, and nothing is imported."""
    from budgets.imports import KEYS as BUDGET_KEYS, apply_budgets
    from inventory.imports import KEYS as DEFINITION_KEYS, apply_categories, apply_definitions, apply_locations, apply_vendors
    done, notes, problems = {}, [], []
    with transaction.atomic():
        placed = False
        for section in ORDER:
            if section in ('harnesses', 'stock') and 'setups' in data and not placed and not problems:
                placed = True   # the setups' devices, once the devices are here (before the harnesses plugged into them)
                problems += _placed_devices(_entries(data, 'setups'))[3]
            if section not in data:
                continue
            try:
                entries = _entries(data, section) if section != 'connector_families' else None
            except ValidationError as exc:
                problems += exc.messages
                continue
            if section == 'item_definitions':
                result = apply_definitions([(n, _as_columns(e, DEFINITION_KEYS)) for n, e in entries])
            elif section == 'budgets':
                result = apply_budgets([(n, _as_columns(e, BUDGET_KEYS)) for n, e in entries])
            elif section == 'connector_families':
                result = _families(data)
            elif section in ('stock', 'assets', 'orders'):
                result = {'stock': _stock, 'assets': _assets, 'orders': _orders}[section](entries, user)
            else:
                result = {'vendors': apply_vendors, 'locations': apply_locations, 'categories': apply_categories,
                          'departments': _departments, 'projects': _projects, 'setups': _setups, 'devices': _devices,
                          'harnesses': _harnesses}[section](entries)
            made, changed, said, wrong = result
            done[section] = (made, changed)
            notes += said
            problems += wrong
        if problems:
            transaction.set_rollback(True)
    if problems:
        sheets.refuse(problems)
    return done, notes
