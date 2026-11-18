"""What a setup holds (``rows``): its devices and the harnesses between them; changing it (``place``, ``take_away``,
``copy``, ``connect``, ``plug``); what is wrong with it (``problems``) and what building it needs (``needs``)."""
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Placement, Setup

FIELDS = ('kind', 'device_id', 'label', 'x', 'y', 'harness_id', 'ends', 'handles')


def spot(value):
    """Where a placed harness's end plugs in, from its placement's ``ends``: (device key, connector id); (None, None)
    when it is not plugged in. (Older rows: just the device key.)"""
    if isinstance(value, (list, tuple)):
        return (value[0], value[1]) if len(value) > 1 else (value[0], None)
    return (value or None, None)


def family_of(thing):
    """The family a harness end or a device connector is of (its item definition's, its branch's, its own), or None."""
    if thing is None:
        return None
    if thing.family_id:
        return thing.family_id
    if thing.branch_id:
        return thing.branch.family_id
    return thing.definition.family_id if thing.definition_id else None


def _row(placement):
    return {'key': placement.key, **{f: getattr(placement, f) for f in FIELDS}}


def rows(setup):
    """{key: {kind, device_id, label, x, y, harness_id, ends, handles, key}} of ``setup``, in the order they came in."""
    if setup is None:
        return {}
    return {p.key: _row(p) for p in Placement.objects.filter(setup=setup)}


@transaction.atomic
def place(setup, key=None, **fields):
    """Set what ``key`` is in ``setup`` (a new key: something added): the fields given, the rest as it is now."""
    current = rows(setup).get(key) if key else None
    if key and current is None:
        raise ValidationError('That is not in this setup.')
    values = {f: v for f, v in (current or {}).items() if f in FIELDS}
    values.update(fields)
    values.setdefault('ends', {})
    values.setdefault('handles', {})
    key = key or uuid.uuid4().hex[:12]
    Placement.objects.update_or_create(setup=setup, key=key, defaults=values)
    return key


@transaction.atomic
def take_away(setup, key):
    """``key`` is no longer in ``setup``. Harnesses plugged into a device taken away come out of it."""
    now = rows(setup)
    if key not in now:
        raise ValidationError('That is not in this setup.')
    Placement.objects.filter(setup=setup, key=key).delete()
    if now[key]['kind'] == 'device':
        for row in now.values():
            if row['kind'] == 'harness' and any(spot(v)[0] == key for v in row['ends'].values()):
                place(setup, row['key'], ends={e: v for e, v in row['ends'].items() if spot(v)[0] != key})


@transaction.atomic
def copy(setup, name, user=None):
    """A new setup in the same project with everything ``setup`` has now (the harnesses are the same ones, placed in
    both)."""
    new = Setup.objects.create(name=name, description=setup.description, in_project=setup.in_project,
                               department=setup.department, owner=user or setup.owner)
    for key, row in rows(setup).items():
        Placement.objects.create(setup=new, key=key, **{f: row[f] for f in FIELDS})
    return new


@transaction.atomic
def connect(setup, ends, name, pairs, definitions=(None, None)):
    """A new harness between two connectors in ``setup``, placed and plugged in: ``ends`` [(device key, connector)]
    its P1 and P2 (``item definitions``: what each is made of, an item definition or a family), ``pairs`` [(pin of the first, pin of the
    second)] its wires, with the signals and sets of the pins."""
    from harnesses.models import Harness, HarnessEnd, Wire
    now = rows(setup)
    if ends[0] == ends[1]:
        raise ValidationError('Pick two different connectors.')
    for key, connector in ends:
        if key not in now or now[key]['device_id'] != connector.device_id:
            raise ValidationError('That connector is not in this setup.')
    harness = Harness.objects.create(setup=setup, name=name.strip()[:200] or 'Harness')
    made = []
    for i, ((_, connector), definition) in enumerate(zip(ends, definitions)):
        end = HarnessEnd(harness=harness, designator=f'P{i + 1}', position=i)
        end.used = definition
        end.save()
        made.append(end)
    pins = [{p.number: p for p in c.pins.all()} for _, c in ends]
    for a, b in pairs:
        pa, pb = pins[0].get(a), pins[1].get(b)
        if pa is None or pb is None:
            raise ValidationError(f'There is no pin {a if pa is None else b} on that connector.')
        in_set = pa if pa.wire_set else pb
        Wire.objects.create(harness=harness, from_end=made[0], from_pin=a, to_end=made[1], to_pin=b, signal=pa.signal or pb.signal,
                            wire_set=in_set.wire_set, set_type=in_set.set_type, wire_group=pa.wire_group or pb.wire_group)
    place(setup, kind='harness', harness_id=harness.pk,
          ends={str(end.pk): [key, connector.pk] for end, (key, connector) in zip(made, ends)})
    between = {ends[0][0], ends[1][0]}
    for wanted in setup.harness_requests.filter(status='open'):   # what someone asked for between these two: made
        if {wanted.a, wanted.b} == between:
            close_request(wanted, wanted.Status.DONE, harness=harness)
    return harness


def sockets(setup, now=None):
    """The device connectors of ``setup`` a harness end can plug into: [(value "key:connector id", label, device key,
    connector)], by device then connector."""
    from devices.models import Connector
    now = now if now is not None else rows(setup)
    placed = [(k, r) for k, r in now.items() if r['kind'] == 'device' and r['device_id']]
    connectors = {}
    for c in Connector.objects.filter(device_id__in={r['device_id'] for _, r in placed}).select_related('device', 'definition', 'branch'):
        connectors.setdefault(c.device_id, []).append(c)
    out = []
    for key, row in placed:
        for c in connectors.get(row['device_id'], []):
            out.append((f'{key}:{c.pk}', f'{row["label"] or c.device.number} {c.designator}{" · " + c.name if c.name else ""}', key, c))
    return out


def plug(setup, harness, wanted=None):
    """How ``harness``'s ends plug in: {end id: [device key, connector id]}. ``wanted`` ({end id: "key:connector id"})
    where given; else, for each end, the one free connector of the setup of the end's family (when there is just
    one)."""
    now = rows(setup)
    choices = sockets(setup, now)
    by_value = {value: (key, c) for value, _, key, c in choices}
    out = {}
    if wanted:
        for end_id, value in wanted.items():
            if value in by_value:
                key, c = by_value[value]
                out[str(end_id)] = [key, c.pk]
        return out
    taken = {spot(v) for r in now.values() if r['kind'] == 'harness' for v in r['ends'].values()}
    for end in harness.ends.select_related('definition', 'branch'):
        mine = family_of(end)
        fits = [(key, c) for _, _, key, c in choices if mine and family_of(c) == mine and (key, c.pk) not in taken]
        if len(fits) == 1:
            out[str(end.pk)] = [fits[0][0], fits[0][1].pk]
            taken.add((fits[0][0], fits[0][1].pk))
    return out


def problems(setup, now=None):
    """What is wrong with ``setup``: [(key, message)]: a harness end not plugged in, two in one connector, a wire on a
    pin the device connector hasn't, a wire whose signal is not the pin's."""
    from devices.models import Connector
    from harnesses.models import HarnessEnd, Wire
    now = now if now is not None else rows(setup)
    found, taken = [], {}
    for key, row in now.items():
        if row['kind'] != 'harness':
            continue
        ends = {e.pk: e for e in HarnessEnd.objects.filter(harness_id=row['harness_id']).select_related('harness')}
        plugged = {}
        for end in ends.values():
            where, connector_id = spot(row['ends'].get(str(end.pk)))
            label = f'{end.harness.number} {end.designator}'
            if where is None or where not in now:
                found.append((key, f'{label} is not plugged in.'))
                continue
            target = now[where]
            connector = Connector.objects.filter(pk=connector_id or 0, device_id=target['device_id']).select_related('device').first()
            if connector is None:
                found.append((key, f'{label} is plugged into {target["label"] or "a device"}, but not into one of its connectors.'))
                continue
            plugged[end.pk] = connector
            spot_at = (where, connector.pk)
            if spot_at in taken:
                found.append((key, f'{label} and {taken[spot_at]} both plug into {target["label"] or connector.device.number} {connector.designator}.'))
            taken[spot_at] = label
        for wire in Wire.objects.filter(harness_id=row['harness_id']):   # each wire's pins: there, and carrying what they do
            for end_id, pin in ((wire.from_end_id, wire.from_pin), (wire.to_end_id, wire.to_pin)):
                connector = plugged.get(end_id)
                if connector is None or not pin:   # no pin: a shield not joined on that side
                    continue
                device_pin = connector.pins.filter(number__iexact=pin).first()
                if device_pin is None:
                    found.append((key, f'{connector} has no pin {pin} ({ends[end_id].harness.number} {wire}).'))
                elif wire.signal and device_pin.signal and wire.signal.strip().lower() != device_pin.signal.strip().lower():
                    found.append((key, f'{ends[end_id].harness.number} {wire}: the wire carries "{wire.signal}", '
                                       f'{connector}:{pin} is "{device_pin.signal}".'))
    return found


def needs(setup):
    """What building ``setup`` once takes: (devices [(device, count)], harnesses [(harness, count)],
    item definitions [(item definition, needed, on hand, on order)])."""
    from devices.models import Device
    from harnesses.models import Harness
    from orders.service import on_order
    device_count, harness_count = {}, {}
    for row in rows(setup).values():
        if row['kind'] == 'device' and row['device_id']:
            device_count[row['device_id']] = device_count.get(row['device_id'], 0) + 1
        elif row['kind'] == 'harness' and row['harness_id']:
            harness_count[row['harness_id']] = harness_count.get(row['harness_id'], 0) + 1
    devices = [(d, device_count[d.pk]) for d in Device.objects.filter(pk__in=device_count).select_related('definition', 'family')]
    harnesses = [(h, harness_count[h.pk]) for h in Harness.objects.filter(pk__in=harness_count)]
    definitions = {}
    for device, n in devices:
        if device.used is not None:
            definitions[device.used] = definitions.get(device.used, Decimal(0)) + n
    for harness, n in harnesses:
        for definition, quantity in harness.parts_list():
            definitions[definition] = definitions.get(definition, Decimal(0)) + quantity * n
    return devices, harnesses, [(definition, quantity, definition.on_hand, on_order(definition))
                                for definition, quantity in sorted(definitions.items(), key=lambda pq: pq[0].number)]


# -- Asking for a harness between two devices ----------------------------------------------------------------------

def ask_harness(setup, a, b, text, ask, user):
    """``user`` asks for a harness between the devices ``a`` and ``b`` of ``setup``; who is asked (else the
    administrators) hears of it."""
    from django.contrib.auth import get_user_model
    from web.notify import notify
    from .models import HarnessRequest
    now = rows(setup)
    if not text.strip():
        raise ValidationError('Say what is needed.')
    if any(now.get(k, {}).get('kind') != 'device' for k in (a, b)):
        raise ValidationError('Pick two devices of this setup.')
    wanted = HarnessRequest.objects.create(setup=setup, a=a, b=b, request=text.strip(), ask=ask, created_by=user)
    people = [ask] if ask else list(get_user_model().objects.filter(is_superuser=True, is_active=True))
    people = [p for p in people if p != user] or people
    notify(people, f'{user or "Someone"} asks for a harness between {label_of(now, a)} and {label_of(now, b)}: {wanted.request[:200]}',
           wanted.get_absolute_url())
    return wanted


def close_request(wanted, status, user=None, harness=None):
    """A harness request made (with ``harness``) or cancelled; who asked hears."""
    from django.utils import timezone
    from web.notify import notify
    if wanted.status != wanted.Status.OPEN:
        raise ValidationError('That request is closed already.')
    wanted.status, wanted.harness, wanted.closed_at = status, harness, timezone.now()
    wanted.save(update_fields=['status', 'harness', 'closed_at'])
    if wanted.created_by and wanted.created_by != user:
        what = f'{harness} is made' if harness else (f'{user} made it' if status == wanted.Status.DONE else f'{user or "Someone"} won\'t make it')
        notify([wanted.created_by], f'The harness you asked for: {what}.', wanted.get_absolute_url())


def label_of(now, key):
    from devices.models import Device
    row = now.get(key) or {}
    device = Device.objects.filter(pk=row.get('device_id')).first()
    return row.get('label') or (device.number if device else '?')
