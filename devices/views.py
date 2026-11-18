"""Devices: the list, a device's page (its connectors and pins, versions, the records of it (built or bought) and the harnesses
plugged into it), and changing them."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.faces import drawn
from web import excel, versions
from web.shortcuts import edit_page, errors

from .forms import ConnectorForm, DeviceForm
from .models import SET_TYPES, Connector, Device, DeviceVersion, Pin, pin_order



@login_required
def device_list(request):
    """The devices, like the item definitions: where they are from on the left (made in-house, bought), the devices in the middle,
    the details of the one picked on the right."""
    q = request.GET.get('q', '').strip()
    found = Device.objects.annotate(n_connectors=Count('connectors', distinct=True), n_units=Count('records', distinct=True))
    if q:
        found = found.filter(Q(number__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q) | Q(model__icontains=q))
    origin = request.GET.get('origin', '')
    if origin in Device.Origin.values:
        found = found.filter(origin=origin)
    if request.GET.get('export'):
        return excel.download('devices', [('Devices', ['Number', 'Name', 'Origin', 'Manufacturer', 'Model', 'Version', 'Connectors', 'Units'],
                                           [(d.number, d.name, d.get_origin_display(), d.manufacturer, d.model, d.version, d.n_connectors,
                                             d.n_units) for d in found]),
                                          ('Pins', PIN_HEAD, _pin_rows(found))])
    from web import briefs, browse
    counts = dict(Device.objects.values('origin').annotate(n=Count('pk')).values_list('origin', 'n'))
    kept = browse.keep(request, 'q')
    nodes = [browse.node('All devices', f'?{kept[1:]}', sum(counts.values()), not origin)] + [
        browse.node(label, f'?origin={value}{kept}', counts.get(value, 0), origin == value) for value, label in Device.Origin.choices]
    picked = Device.objects.filter(pk=request.GET.get('device') or 0).first()
    return render(request, 'devices/list.html', {'devices': found, 'q': q, 'origin': origin, 'nodes': nodes, 'picked': picked,
                                                 'brief': briefs.of('device', picked) if picked else None})


PIN_HEAD = ['Device', 'Connector', 'Connector name', 'Connector item definition', 'Pin', 'Signal', 'Group', 'Set', 'Set type', 'Description']


def _pin_rows(devices):
    for device in devices:
        for connector in device.connectors.select_related('definition', 'family').prefetch_related('pins'):
            for pin in connector.ordered_pins():
                yield (device.number, connector.designator, connector.name, connector.used_name,
                       pin.number, pin.signal, pin.wire_group, pin.wire_set, pin.set_type if pin.wire_set else '', pin.description)


@login_required
def device_form(request, pk=None):
    item = get_object_or_404(Device, pk=pk) if pk else None
    form = DeviceForm(request.POST or None, instance=item)
    with transaction.atomic():
        return edit_page(request, form, 'device', saved=lambda device, new: form.add_unit(device))


@login_required
@require_POST
def device_delete(request, pk):
    """The device, with its connectors and versions. Not while a setup has it, nor while there are records of it
    (one built or bought: retire those)."""
    item = get_object_or_404(Device, pk=pk)
    setups = sorted({str(p.setup) for p in item.placements.select_related('setup')})
    if setups:
        messages.error(request, f'{item} is in the setup {", ".join(setups)}: take it out there first.')
        return redirect('devices:list')
    made = list(item.records.values_list('tag', flat=True)[:5])
    if made:
        messages.error(request, f'There are records of {item} ({", ".join(t or "?" for t in made)}): it stays.')
        return redirect(item)
    with transaction.atomic():
        item.delete()
    messages.success(request, f'{item} is deleted.')
    return redirect('devices:list')


def _plugged(connectors):
    """{connector id: [harness ends plugged into it]}, from the setups."""
    from harnesses.models import HarnessEnd
    from setups.contents import spot
    from setups.models import Placement
    plugged, mine = {}, {c.pk for c in connectors}
    for p in Placement.objects.filter(kind='harness').exclude(harness=None):
        for end_id, value in (p.ends or {}).items():
            connector_id = spot(value)[1]
            if connector_id in mine:
                plugged.setdefault(connector_id, set()).add(int(end_id))
    ends = {e.pk: e for e in HarnessEnd.objects.filter(pk__in={e for found in plugged.values() for e in found}).select_related('harness__setup')}
    return {c: sorted((ends[e] for e in found if e in ends), key=lambda e: (e.harness.number, e.designator)) for c, found in plugged.items()}


def _face(c, pins=None):
    pins = c.ordered_pins() if pins is None else pins
    return {'face': drawn(c.used, [p.number for p in pins]), 'pins': [[p.number, p.signal] for p in pins]}


@login_required
def device(request, pk):
    """A device as a tree (the device, its connectors, its assets) on the left; in the middle its connectors, the pins of
    the connector picked (?connector=) or its assets (?show=assets); on the right the device itself (picture, details,
    versions, notes, files), the connector (its face, what is plugged into it) or the row picked."""
    from web import browse
    item = get_object_or_404(Device.objects.select_related('definition', 'family'), pk=pk)
    if request.GET.get('export'):
        return excel.download(item.number, [('Pins', PIN_HEAD, _pin_rows([item]))])
    connectors = list(item.connectors.select_related('definition', 'family', 'branch').prefetch_related('pins'))
    plugged = _plugged(connectors)
    pins = {c.pk: c.ordered_pins() for c in connectors}
    picked = next((c for c in connectors if str(c.pk) == request.GET.get('connector')), None)
    show = 'connector' if picked else 'assets' if request.GET.get('show') == 'assets' else 'device'
    units = list(item.records.select_related('location', 'keeper', 'holder'))
    nodes = [browse.node(item.number, '?', len(connectors), show == 'device', open=True)]
    nodes += [browse.node(f'{c.designator} {c.name}'.strip(), f'?connector={c.pk}', len(pins[c.pk]), picked == c, 1) for c in connectors]
    nodes.append(browse.node('Assets', '?show=assets', len(units), show == 'assets'))
    context = {'device': item, 'show': show, 'nodes': nodes, 'picked': picked,
               'connectors': [(c, pins[c.pk], plugged.get(c.pk, [])) for c in connectors],
               'versions': item.versions.select_related('created_by'), 'changed': versions.changed(item), 'units': units}
    if picked:
        context.update({'pins': pins[picked.pk], 'ends': plugged.get(picked.pk, []), 'face': _face(picked, pins[picked.pk])})
    elif show == 'device' and request.GET.get('c'):
        one = next((c for c in connectors if str(c.pk) == request.GET['c']), None)
        if one:
            context['row'] = one
            context['row_brief'] = {'connector': one, 'pins': pins[one.pk], 'ends': plugged.get(one.pk, []), 'face': _face(one, pins[one.pk])}
    elif show == 'assets' and request.GET.get('asset'):
        from records.views import _brief
        one = next((u for u in units if str(u.pk) == request.GET['asset']), None)
        if one:
            context['row'] = one
            context['asset_brief'] = _brief(one)
    return render(request, 'devices/device.html', context)


@login_required
def connector_brief(request, pk, connector):
    """A connector beside the device's list of connectors (fetched when one is picked): its face, its details, what is
    plugged into it."""
    c = get_object_or_404(Connector.objects.select_related('device', 'definition', 'family', 'branch'), pk=connector, device_id=pk)
    pins = c.ordered_pins()
    return render(request, 'devices/_connector.html', {'connector': c, 'pins': pins, 'ends': _plugged([c]).get(c.pk, []),
                                                       'face': _face(c, pins)})


@login_required
def connector_form(request, pk, connector=None):
    item = get_object_or_404(Device, pk=pk)
    current = get_object_or_404(Connector, pk=connector, device=item) if connector else Connector(device=item)
    form = ConnectorForm(request.POST or None, instance=current)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            if not saved.pk:
                saved.position = item.connectors.count()
            saved.save()
            Pin.objects.bulk_create(Pin(connector=saved, number=n) for n in form.cleaned_data.get('pins') or [])
        return redirect(f'{item.get_absolute_url()}?connector={saved.pk}')
    return render(request, 'web/form.html', {'form': form, 'back': item.get_absolute_url(),
                                                   'title': f'Change {current}' if current.pk else f'New connector on {item}'})


def free_designator(device, wanted):
    """``wanted`` if the device has no connector of that name yet, else the next free one (J1 taken: J2, J3, …)."""
    import re
    taken = {d.lower() for d in device.connectors.values_list('designator', flat=True)}
    if wanted.lower() not in taken:
        return wanted
    stem, number = re.match(r'^(.*?)(\d*)$', wanted).groups()
    n = int(number or 1) + 1
    while f'{stem}{n}'.lower() in taken:
        n += 1
    return f'{stem}{n}'[:30]


@login_required
def connectors_copy(request, pk):
    """Connectors of other devices, picked from a tree (device, then its connectors), copied here with their pins."""
    item = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        copied = []
        with transaction.atomic():
            for source in Connector.objects.filter(pk__in=request.POST.getlist('connector')).exclude(device=item).prefetch_related('pins'):
                made = Connector.objects.create(device=item, designator=free_designator(item, source.designator), name=source.name,
                                                definition=source.definition, family=source.family, branch=source.branch, position=item.connectors.count())
                Pin.objects.bulk_create(Pin(connector=made, number=p.number, signal=p.signal, wire_set=p.wire_set, set_type=p.set_type, wire_group=p.wire_group,
                                            description=p.description) for p in source.pins.all())
                copied.append(made.designator if made.designator == source.designator else f'{source.designator} (as {made.designator})')
        messages.success(request, f'Copied: {", ".join(copied)}.' if copied else 'Nothing was picked.')
        return redirect(item)
    others = Device.objects.exclude(pk=item.pk).filter(connectors__isnull=False).distinct().prefetch_related(
        'connectors__pins', 'connectors__definition', 'connectors__family', 'connectors__branch')
    return render(request, 'devices/copy.html', {'device': item, 'others': others})


@login_required
@require_POST
def connector_delete(request, pk, connector):
    item = get_object_or_404(Connector, pk=connector, device_id=pk)
    item.delete()
    messages.success(request, f'{item.designator} is taken away.')
    return redirect('devices:device', pk)


@login_required
def pins(request, pk, connector):
    """A connector's pins as one form: numbers, signals, groups (a name tag over sets: "Channel 1"), sets (from a list,
    or a new one), descriptions; new rows add pins, ✕ takes one away. The pins of a set are all of one type and in one
    group: the one changed, else the one it had."""
    item = get_object_or_404(Connector.objects.select_related('device'), pk=connector, device_id=pk)
    rows = item.ordered_pins()
    if request.method == 'POST':
        try:
            with transaction.atomic():
                post = request.POST
                had = {p.wire_set: p.set_type for p in rows if p.wire_set}   # each set's type before
                typed = {}                                                   # each set's type, where it was changed
                was = {p.wire_set: p.wire_group for p in rows if p.wire_set}  # each set's group before
                grouped = {}                                                 # each set's group, where it was changed
                for pin in rows:
                    if post.get(f'gone_{pin.pk}'):
                        pin.delete()
                        continue
                    before, before_group = pin.set_type, pin.wire_group
                    pin.number = post.get(f'number_{pin.pk}', pin.number).strip() or pin.number
                    pin.signal = post.get(f'signal_{pin.pk}', '').strip()[:100]
                    pin.wire_set, pin.set_type = _set(post, pin.pk)
                    pin.wire_group = post.get(f'group_{pin.pk}', '').strip()[:40]
                    pin.description = post.get(f'description_{pin.pk}', '').strip()[:200]
                    pin.save()
                    if pin.wire_set and pin.set_type != before:
                        typed[pin.wire_set] = pin.set_type
                    if pin.wire_set and pin.wire_group != before_group:
                        grouped[pin.wire_set] = pin.wire_group
                for i in range(int(post.get('new', 0) or 0)):
                    number = post.get(f'number_new{i}', '').strip()
                    if number:
                        wire_set, set_type = _set(post, f'new{i}')
                        group = post.get(f'group_new{i}', '').strip()[:40]
                        Pin.objects.create(connector=item, number=number[:20], signal=post.get(f'signal_new{i}', '').strip()[:100],
                                           wire_set=wire_set, set_type=set_type, wire_group=group,
                                           description=post.get(f'description_new{i}', '').strip()[:200])
                        if wire_set and wire_set not in had:
                            typed.setdefault(wire_set, set_type)
                            grouped.setdefault(wire_set, group)
                for wire_set in set(item.pins.exclude(wire_set='').values_list('wire_set', flat=True)):
                    one = typed.get(wire_set) or had.get(wire_set)
                    if one:
                        item.pins.filter(wire_set=wire_set).update(set_type=one)
                    if wire_set in grouped or wire_set in was:
                        item.pins.filter(wire_set=wire_set).update(wire_group=grouped.get(wire_set, was.get(wire_set, '')))
        except IntegrityError:
            messages.error(request, 'Two pins have the same number: nothing was saved.')
            return redirect(request.path)
        messages.success(request, f'The pins of {item} are saved.')
        return redirect(f'{item.device.get_absolute_url()}?connector={item.pk}')
    return render(request, 'devices/pins.html', {'connector': item, 'pins': rows, 'new': range(5), 'set_types': SET_TYPES,
                                                 'groups': sorted(set(Pin.objects.filter(connector__device=item.device).exclude(wire_group='')
                                                                      .values_list('wire_group', flat=True)), key=pin_order),
                                                 'sets': sorted({p.wire_set for p in rows if p.wire_set}, key=pin_order)})


def _set(post, row):
    """A pins form row's set and set type."""
    set_type = post.get(f'set_type_{row}', '')
    wire_set = post.get(f'set_{row}', '').strip()[:20]
    return ('' if wire_set == '+' else wire_set), set_type if set_type in SET_TYPES else 'Straight'


@login_required
@require_POST
def save_version(request, pk):
    item = get_object_or_404(Device, pk=pk)
    try:
        version = versions.save(item, request.user, request.POST.get('note', ''))
        messages.success(request, f'{item.number} is saved as v{version.number}.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
def version(request, pk, number):
    item = get_object_or_404(Device, pk=pk)
    saved = get_object_or_404(DeviceVersion, device=item, number=number)
    for c in saved.data.get('connectors', []):
        c['pins'] = sorted(c.get('pins', []), key=lambda p: pin_order(p['number']))
    return render(request, 'devices/version.html', {'device': item, 'version': saved, 'data': saved.data})


@login_required
@require_POST
def restore(request, pk, number):
    item = get_object_or_404(Device, pk=pk)
    saved = get_object_or_404(DeviceVersion, device=item, number=number)
    versions.restore(item, saved)
    messages.success(request, f'{item.number} is as it was in v{number}: save a version to keep it.')
    return redirect(item)
