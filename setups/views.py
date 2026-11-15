"""Setups: the list (by project), a setup's page (drawn as its devices and the harnesses between them, and what is
wrong), changing it, copying it, and what building it needs."""
import json

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Department
from devices.models import Connector, Device
from harnesses.models import Harness
from inventory.models import choices_of_parts, part_or_family
from orders import service as orders
from web import excel
from web.shortcuts import edit_page, errors
from web.forms import TreeForm, initial_for

from . import contents
from .models import HarnessRequest, Setup

GRID_X, GRID_Y = 300, 240   # where new devices go on the diagram: a grid of four across


class SetupForm(TreeForm):
    tree_fields = {'department': Department}

    class Meta:
        model = Setup
        fields = ['code', 'name', 'in_project', 'description', 'department', 'owner']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}



@login_required
def setup_list(request):
    """The setups, like the parts: the projects (and their sub-projects) as a tree on the left, the setups
    of the one picked in the middle, the details of the setup picked on the right."""
    from django.db.models import Count, Q

    from web import briefs, browse
    from work.models import Project as Work
    found = Setup.objects.select_related('owner', 'in_project').annotate(
        n_devices=Count('placements', filter=Q(placements__kind='device'), distinct=True),
        n_harnesses=Count('placements', filter=Q(placements__kind='harness'), distinct=True))
    q = request.GET.get('q', '').strip()
    if q:
        found = found.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    work = Work.objects.filter(pk=request.GET.get('work') or 0).first()
    loose = bool(request.GET.get('none')) and work is None
    if work:
        found = found.filter(in_project_id__in=work.below())
    elif loose:
        found = found.filter(in_project=None)
    own = dict(Setup.objects.exclude(in_project=None).values('in_project').annotate(n=Count('pk')).values_list('in_project', 'n'))
    kept = browse.keep(request, 'q')
    tree = [n for n in browse.nodes(Work.ordered(), own, work, lambda w: f'?work={w.pk}{kept}') if n['count']]   # projects with some
    nodes = [browse.node('All setups', f'?{kept[1:]}', Setup.objects.count(), not work and not loose)] + tree + [
        browse.node('In no project', f'?none=1{kept}', Setup.objects.filter(in_project=None).count(), loose)]
    picked = Setup.objects.filter(pk=request.GET.get('setup') or 0).first()
    return render(request, 'setups/list.html', {'setups': found, 'nodes': nodes, 'q': q, 'work': work, 'loose': loose, 'picked': picked,
                                                  'brief': briefs.of('setup', picked) if picked else None})


@login_required
def setup_form(request, pk=None):
    item = get_object_or_404(Setup, pk=pk) if pk else None
    return edit_page(request, SetupForm(request.POST or None, instance=item, initial=initial_for(item, owner=request.user.pk, in_project=request.GET.get('in_project'))),
                     'setup')


def _diagram(setup, rows, found):
    """What the diagram draws: the devices (with their connectors) and the harnesses between them."""
    device_ids = {r['device_id'] for r in rows.values() if r['kind'] == 'device'}
    devices = {d.pk: d for d in Device.objects.filter(pk__in=device_ids).prefetch_related('connectors__pins', 'connectors__part',
                                                                                        'connectors__family')}
    harnesses = {h.pk: h for h in Harness.objects.filter(pk__in={r['harness_id'] for r in rows.values() if r['harness_id']})
                 .prefetch_related('ends')}
    bad = {key for key, _ in found}
    out = {'devices': [], 'harnesses': [],
           'requests': [{'id': r.pk, 'a': r.a, 'b': r.b, 'text': r.request} for r in setup.harness_requests.filter(status='open')]}
    for key, row in rows.items():
        if row['kind'] == 'device' and row['device_id'] in devices:
            d = devices[row['device_id']]
            out['devices'].append({'key': key, 'label': row['label'] or d.number, 'number': d.number, 'name': d.name, 'colour': d.colour,
                                   'url': d.get_absolute_url(), 'x': row['x'], 'y': row['y'],
                                   'connectors': [{'id': c.pk, 'designator': c.designator, 'name': c.name, 'part': c.used_name,
                                                   'side': c.side, 'along': c.along,
                                                   'pins_url': reverse('devices:pins', args=[d.pk, c.pk]),
                                                   'pins': [[p.number, p.signal, p.wire_set, p.set_type if p.wire_set else '', p.description]
                                                            for p in c.ordered_pins()]} for c in d.connectors.all()]})
        elif row['kind'] == 'harness' and row['harness_id'] in harnesses:
            h = harnesses[row['harness_id']]
            out['harnesses'].append({'key': key, 'number': h.number, 'name': h.name, 'url': h.get_absolute_url(),
                                     'bad': key in bad, 'handles': row['handles'],
                                     'ends': [{'id': str(e.pk), 'designator': e.designator, 'device': contents.spot(row['ends'].get(str(e.pk)))[0],
                                               'connector': contents.spot(row['ends'].get(str(e.pk)))[1]} for e in h.ends.all()]})
    return out


def _harness_choices(setup):
    """The harnesses that can be placed in ``setup``: its own and those of the other setups of its project."""
    mine = Q(setup=setup) | (Q(setup__in_project=setup.in_project) if setup.in_project_id else Q())
    return Harness.objects.filter(mine).exclude(status=Harness.Status.OBSOLETE).select_related('setup').order_by('number')


@login_required
def setup(request, pk):
    item = get_object_or_404(Setup.objects.select_related('in_project'), pk=pk)
    rows = contents.rows(item)
    found = contents.problems(item, rows)
    placed_devices = [(key, r) for key, r in rows.items() if r['kind'] == 'device']
    device_names = {d.pk: d for d in Device.objects.filter(pk__in=[r['device_id'] for _, r in placed_devices])}
    harness_rows = []
    for key, r in rows.items():
        if r['kind'] == 'harness':
            h = Harness.objects.filter(pk=r['harness_id']).prefetch_related('ends').first()
            if h:   # each end, and where it plugs in ("device key:connector id")
                harness_rows.append((key, h, [(e, '{}:{}'.format(*contents.spot(r['ends'].get(str(e.pk)))) if contents.spot(r['ends'].get(str(e.pk)))[1] else '')
                                              for e in h.ends.all()]))
    siblings = Setup.objects.filter(in_project=item.in_project).exclude(pk=item.pk) if item.in_project_id else Setup.objects.none()
    return render(request, 'setups/setup.html', {
        'setup': item, 'siblings': siblings, 'problems': [text for _, text in found], 'diagram': _diagram(item, rows, found),
        'placed_devices': [(key, r, device_names.get(r['device_id'])) for key, r in placed_devices],
        'harness_rows': harness_rows, 'sockets': [(value, label) for value, label, _, _ in contents.sockets(item, rows)],
        'devices': Device.objects.all(), 'harnesses': _harness_choices(item),
        'part_choices': choices_of_parts(), 'people': get_user_model().objects.filter(is_active=True),
        'requests': [(r, contents.label_of(rows, r.a), contents.label_of(rows, r.b)) for r in
                     item.harness_requests.select_related('created_by', 'ask', 'harness')[:20]]})


@login_required
@require_POST
def copy(request, pk):
    """A copy of the setup, a setup of its own in the same project."""
    item = get_object_or_404(Setup, pk=pk)
    made = contents.copy(item, request.POST.get('name', '').strip()[:200] or f'{item.name} (copy)', request.user)
    messages.success(request, f'{made} is a copy of {item}.')
    return redirect(made)


@login_required
@require_POST
def change(request, pk):
    """A change to the setup: add, move, rename, swap or take away a device; add, plug in or take away a harness, or
    make one between two connectors. Moves come from the diagram (JSON back)."""
    item = get_object_or_404(Setup, pk=pk)
    post, action, key = request.POST, request.POST.get('action'), request.POST.get('key') or None
    try:
        if action == 'move':
            contents.place(item, key, x=int(float(post.get('x', 0))), y=int(float(post.get('y', 0))))
            return JsonResponse({'ok': True})
        if action == 'handle':   # a harness line pinned at (x, y), or let go (no x)
            handles = dict(contents.rows(item)[key]['handles'])
            if post.get('x'):
                handles[post['end']] = [round(float(post['x'])), round(float(post['y']))]
            else:
                handles.pop(post.get('end'), None)
            contents.place(item, key, handles=handles)
            return JsonResponse({'ok': True})
        if action == 'place_connector':   # a connector's place on its device's outline
            side = post.get('side')
            if side not in ('top', 'right', 'bottom', 'left'):
                raise ValueError(side)
            Connector.objects.filter(pk=post.get('connector')).update(side=side, along=min(max(float(post.get('along', 0.5)), 0), 1))
            return JsonResponse({'ok': True})
        if action == 'add_device':
            device = get_object_or_404(Device, pk=post.get('device'))
            n = sum(1 for r in contents.rows(item).values() if r['kind'] == 'device')
            same = sum(1 for r in contents.rows(item).values() if r['device_id'] == device.pk)
            contents.place(item, kind='device', device_id=device.pk, label=post.get('label', '').strip()[:100]
                          or (f'{device.number} {same + 1}' if same else device.number),
                          x=40 + (n % 4) * GRID_X, y=40 + (n // 4) * GRID_Y)
        elif action == 'rename':
            contents.place(item, key, label=post.get('label', '').strip()[:100])
        elif action == 'swap':
            contents.place(item, key, device_id=get_object_or_404(Device, pk=post.get('device')).pk)
        elif action == 'connect':
            ends = [(post.get(side), get_object_or_404(Connector, pk=post.get(f'{side}_connector') or 0)) for side in 'ab']
            parts = []
            for side in 'ab':
                text = post.get(f'{side}_part', '').strip()
                parts.append(part_or_family(text))
                if text and parts[-1] is None:
                    raise ValidationError(f'There is no part or family "{text}".')
            harness = contents.connect(item, ends, post.get('name', ''), [json.loads(w) for w in post.getlist('wire')], parts)
            messages.success(request, f'{harness} is made, with {harness.wires.count()} wires.')
        elif action == 'request_harness':
            ask = get_user_model().objects.filter(pk=post.get('ask') or 0, is_active=True).first()
            contents.ask_harness(item, post.get('a', ''), post.get('b', ''), post.get('request', ''), ask, request.user)
            messages.success(request, f'Asked for: {ask or "the administrators"} will make it.')
        elif action in ('request_done', 'request_cancel'):
            wanted = get_object_or_404(HarnessRequest, pk=post.get('request_id'), setup=item)
            made = _harness_choices(item).filter(pk=post.get('harness') or 0).first()
            contents.close_request(wanted, wanted.Status.DONE if action == 'request_done' else wanted.Status.CANCELLED, request.user, made)
        elif action == 'add_harness':
            harness = get_object_or_404(_harness_choices(item), pk=post.get('harness'))
            contents.place(item, kind='harness', harness_id=harness.pk, ends=contents.plug(item, harness))
        elif action == 'plug':
            harness = get_object_or_404(Harness, pk=contents.rows(item)[key]['harness_id'])
            wanted = {k[4:]: v for k, v in post.items() if k.startswith('end_') and v}
            contents.place(item, key, ends=contents.plug(item, harness, wanted) if wanted else {})
        elif action == 'remove':
            contents.take_away(item, key)
        else:
            raise ValidationError('What should change?')
    except (ValidationError, KeyError, ValueError, TypeError) as exc:
        if action in ('move', 'handle', 'place_connector'):
            return JsonResponse({'ok': False}, status=400)
        errors(request, exc if isinstance(exc, ValidationError) else ValidationError('That is not in this setup.'))
    return redirect(item)


@login_required
def needs(request, pk):
    item = get_object_or_404(Setup, pk=pk)
    devices, harnesses, parts = contents.needs(item)
    count = request.GET.get('count', '')
    count = int(count) if count.isdigit() and 0 < int(count) <= 10000 else 1   # how many of it to build
    parts = [(p, q * count, have, coming, max(q * count - have - coming, 0)) for p, q, have, coming in parts]
    if request.method == 'POST':   # order what is missing
        ordered = []
        for part, _, _, _, missing in parts:
            buy = getattr(part, 'chosen', part)   # a family: the part of it ordered
            if missing and buy and buy.vendor_id:
                orders.reorder(buy, request.user, missing)
                ordered.append(buy.number)
        messages.success(request, f'On the draft orders: {", ".join(ordered)}.' if ordered else 'Nothing missing could be ordered.')
        return redirect(f'{request.path}?count={count}')
    if request.GET.get('export'):
        return excel.download(str(item), [
            ('Parts', ['Part', 'Description', 'Needed', 'Unit', 'On hand', 'On order', 'Missing'],
             [(p.number, p.description, q, p.unit, have, coming, missing) for p, q, have, coming, missing in parts]),
            ('Devices', ['Device', 'Name', 'How many'], [(d.number, d.name, n * count) for d, n in devices]),
            ('Harnesses', ['Harness', 'Name', 'How many'], [(h.number, h.name, n * count) for h, n in harnesses])])
    return render(request, 'setups/needs.html', {'setup': item, 'devices': devices, 'harnesses': harnesses,
                                                 'parts': parts, 'count': count})
