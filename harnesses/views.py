"""Harnesses: the list, a harness's page (ends, pinout, items, parts list, what is wrong, versions, the harnesses
built: records with an asset tag, each with a checklist), editing its ends, pinout and items as tables."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from devices.models import SET_TYPES as PIN_SET_TYPES, Connector, pin_order
from inventory import stock
from inventory.faces import drawn, face_of
from inventory.models import Location, ItemDefinition, DefinitionGroup, choices_of_definitions, definition_or_family
from setups.models import Setup
from records.service import next_tag
from web import excel, rows, versions
from web.shortcuts import edit_page, errors
from web.templatetags.osmia import qty

from . import purposes
from web.forms import initial_for

from .models import COLOURS, SET_TYPES, Harness, HarnessEnd, HarnessItem, HarnessMark, HarnessVersion, Wire, parts_of


class HarnessForm(forms.ModelForm):
    class Meta:
        model = Harness
        fields = ['setup', 'name', 'description', 'status', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 3})}



@login_required
def harness_list(request):
    """The harnesses, like the item definitions: the projects and their setups as a tree on the left, the harnesses of the
    one picked in the middle (found by number or name, by status), the details of the harness picked on the right."""
    from django.db.models import Count, Q

    from work.models import Project as Work
    found = Harness.objects.select_related('setup').annotate(n_wires=Count('wires', distinct=True), n_ends=Count('ends', distinct=True))
    q = request.GET.get('q', '').strip()
    if q:
        found = found.filter(Q(number__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))
    status = request.GET.get('status', '')
    if status in Harness.Status.values:
        found = found.filter(status=status)
    alone = request.GET.get('setup') == 'none'   # those in no setup
    setup = None if alone else Setup.objects.filter(pk=request.GET.get('setup') or 0).first()
    work = Work.objects.filter(pk=request.GET.get('work') or 0).first() if not (setup or alone) else None
    if alone:
        found = found.filter(setup__isnull=True)
    elif setup:
        found = found.filter(setup=setup)
    elif work:
        found = found.filter(setup__in_project=work)
    counts = dict(Harness.objects.values('setup').annotate(n=Count('pk')).values_list('setup', 'n'))
    setups = list(Setup.objects.select_related('in_project').order_by('name'))
    tree = []   # (kind, thing, depth, count): a project, then its setups; setups in no project after
    for w in Work.objects.filter(setups__isnull=False).distinct().order_by('code', 'name'):
        mine = [d for d in setups if d.in_project_id == w.pk]
        tree.append(('work', w, 0, sum(counts.get(d.pk, 0) for d in mine)))
        tree += [('setup', d, 1, counts.get(d.pk, 0)) for d in mine]
    tree += [('setup', d, 0, counts.get(d.pk, 0)) for d in setups if d.in_project_id is None]
    picked = Harness.objects.filter(pk=request.GET.get('harness') or 0).first()
    return render(request, 'harnesses/list.html', {
        'setups': setups, 'harnesses': found, 'setup': setup, 'work': work, 'tree': tree, 'q': q, 'status': status,
        'statuses': Harness.Status.choices, 'every': Harness.objects.count(), 'picked': picked,
        'alone': alone, 'n_alone': counts.get(None, 0),
        'brief': _brief(picked) if picked else None})


def _brief(harness):
    """What the details beside the harness list show of ``harness``."""
    wires = harness.ordered_wires()
    return {'harness': harness, 'ends': harness.ends.select_related('definition', 'family', 'branch'),
            'wires': wires, 'definitions': harness.parts_list(), 'problems': [text for _, text in harness.problems()]}


@login_required
def harness_brief(request, pk):
    """The details of a harness beside the harness list (fetched when one is picked)."""
    return render(request, 'harnesses/_brief.html', _brief(get_object_or_404(Harness.objects.select_related('setup'), pk=pk)))


@login_required
def harness_form(request, pk=None):
    item = get_object_or_404(Harness, pk=pk) if pk else None
    return edit_page(request, HarnessForm(request.POST or None, instance=item, initial=initial_for(item, setup=request.GET.get('setup'))),
                     'harness')


def _sheets(harness):
    wires = harness.ordered_wires()
    return [('Pinout', ['From', 'Pin', 'To', 'Pin', 'Signal', 'Group', 'Set', 'Set type', 'Colour', 'Gauge', 'Length (mm)', 'Wire item definition'],
             [(w.from_end.designator, w.from_pin, w.to_end.designator, w.to_pin, w.signal, w.wire_group, w.wire_set, w.set_type, w.colour,
               w.gauge, w.length, w.used_name) for w in wires]),
            ('Groups', ['Group', 'Total length (mm)', 'Bundled together (mm)'],
             [(g.name, g.length, g.bundled) for g in _groups(harness, wires)]),
            ('Connectors', ['Connector', 'Item definition'],
             [(e.designator, e.used_name) for e in harness.ends.select_related('definition', 'family')]),
            ('Parts list', ['Item definition', 'Description', 'Quantity', 'Unit'],
             [(p.number, p.description, q, p.unit) for p, q in harness.parts_list()])]


@login_required
def harness(request, pk):
    item = get_object_or_404(Harness.objects.select_related('setup'), pk=pk)
    if request.GET.get('export'):
        return excel.download(f'{item.number} {item.name}', _sheets(item))
    if request.GET.get('json'):   # as a file to take in again (here, or into another Osmia)
        from .transfer import export_harness
        response = JsonResponse(export_harness(item), json_dumps_params={'indent': 1, 'ensure_ascii': False})
        response['Content-Disposition'] = f'attachment; filename="{item.number} {_safe(item.name)}.json"'
        return response
    wires = item.ordered_wires()
    groups = []
    for w in wires:
        between = f'{w.from_end.designator} → {w.to_end.designator}'
        if not groups or groups[-1][0] != between:
            groups.append((between, []))
        groups[-1][1].append(w)
    found = item.problems()
    from inventory import picker
    return render(request, 'harnesses/harness.html', {'drawing': _drawing(item, wires), 'family_picker': picker.dialog(),
        'wire_groups': _groups(item, wires),
        'harness': item, 'ends': item.ends.select_related('definition', 'family', 'branch'), 'groups': groups, 'wire_count': len(wires),
        'items': item.items.select_related('definition'), 'definitions': item.parts_list(),
        'problems': [text for _, text in found], 'bad_wires': {thing.pk for thing, _ in found if isinstance(thing, Wire)},
        'versions': item.versions.select_related('created_by'), 'changed': versions.changed(item),
        'units': item.records.all(), 'locations': Location.ordered(), 'next_serial': next_tag(item.number),
        **_bundle(item, wires)})


def _splices(wires):
    """The contacts with several wires (splices), as "P1:1", in the order of the wires."""
    seen = {}
    for w in wires:
        for end, pin in ((w.from_end, w.from_pin), (w.to_end, w.to_pin)):
            if pin:
                key = f'{end.designator}:{pin}'
                seen[key] = seen.get(key, 0) + 1
    return [k for k, n in seen.items() if n > 1]


def _path(a, b):
    """How long a wire between ends ``a`` and ``b`` is along the bundle: down a's branch, along the trunk, up b's (None
    when either has no place on the trunk, or it is a loopback)."""
    if a.pk == b.pk or a.along is None or b.along is None:
        return None
    return (a.reach or 0) + abs(a.along - b.along) + (b.reach or 0)


def _bundle(harness, wires):
    """What the Bundle tab shows: the drawing's data, the marks to edit (and blank rows for new ones), and how long each
    pair of connectors' wires are along the bundle."""
    ends = list(harness.ends.all())
    marks = list(harness.marks.select_related('on', 'definition', 'family', 'branch'))
    sets = {}
    for w in wires:
        if w.wire_set and 'shielded' in w.set_type.lower():
            sets[w.wire_set] = True
    pairs = {}
    for w in wires:
        key = (w.from_end_id, w.to_end_id) if w.from_end.position <= w.to_end.position else (w.to_end_id, w.from_end_id)
        if key not in pairs:
            pairs[key] = {'between': f'{w.from_end.designator} – {w.to_end.designator}', 'length': _path(w.from_end, w.to_end), 'wires': 0}
        pairs[key]['wires'] += 1
    drawing = {'trunk': qty(harness.trunk), 'ends': [{'id': e.pk, 'designator': e.designator, 'what': e.used_name, 'along': qty(e.along),
                                                       'reach': qty(e.reach)} for e in ends],
               'marks': [{'kind': m.kind, 'label': m.get_kind_display(), 'on': m.on_id, 'start': qty(m.start), 'end': qty(m.end),
                          'text': m.text, 'set': m.wire_set, 'what': m.used_name} for m in marks]}
    return {'bundle': drawing, 'bundle_ends': ends, 'marks': marks + [None] * 4, 'mark_kinds': HarnessMark.Kind.choices,
            'splice_contacts': _splices(wires), 'shielded_sets': sorted(sets, key=pin_order), 'paths': list(pairs.values()),
            'definition_numbers': choices_of_definitions()}


def _mm(text, who, what):
    """A length in mm typed in (None when empty)."""
    try:
        return _number(str(text or '').strip(), 0, what)
    except ValidationError as exc:
        raise ValidationError(exc.messages[0].replace('Row 0', who))


@login_required
@require_POST
def bundle_save(request, pk):
    """The bundle as filled in on the Bundle tab: the trunk's length, where each connector breaks out and its branch's
    length, and the marks along it (a row emptied of its position, or ticked to go, is taken away)."""
    item = get_object_or_404(Harness, pk=pk)
    post = request.POST
    ends = {e.pk: e for e in item.ends.all()}
    try:
        with transaction.atomic():
            item.trunk = _mm(post.get('trunk', ''), 'The trunk', 'length')
            item.save(update_fields=['trunk'])
            for e in ends.values():
                e.along = _mm(post.get(f'along_{e.pk}', ''), e.designator, 'breakout')
                e.reach = _mm(post.get(f'reach_{e.pk}', ''), e.designator, 'branch length')
                if e.along is not None and item.trunk is not None and e.along > item.trunk:
                    raise ValidationError(f'{e.designator}: it breaks out past the end of the trunk ({qty(item.trunk)} mm).')
                e.save(update_fields=['along', 'reach'])
            kept = {m.pk: m for m in item.marks.all()}
            kinds = dict(HarnessMark.Kind.choices)
            splices = {s.lower() for s in _splices(item.ordered_wires())}
            for i in range(int(post.get('mark_rows') or 0)):
                f = lambda name: post.get(f'm{i}_{name}', '').strip()   # noqa: E731
                mark = kept.get(int(f('id') or 0)) if f('id').isdigit() else None
                start = _mm(f('start'), f'Mark {i + 1}', 'position')
                if f('gone') or start is None:
                    if mark:
                        mark.delete()
                    continue
                kind = f('kind') if f('kind') in kinds else ''
                if not kind:
                    raise ValidationError(f'Mark {i + 1}: what is it?')
                on = ends.get(int(f('on'))) if f('on').isdigit() else None
                end = _mm(f('end'), f'Mark {i + 1}', 'end') if kind in HarnessMark.STRETCHES else None
                if kind in HarnessMark.STRETCHES and (end is None or end <= start):
                    raise ValidationError(f'Mark {i + 1}: a {kinds[kind].lower()} goes from one place to a further one.')
                longest = (on.reach if on else item.trunk)
                where = f"{on.designator}'s branch" if on else 'the trunk'
                if longest is not None and max(start, end or start) > longest:
                    raise ValidationError(f'Mark {i + 1}: past the end of {where} ({qty(longest)} mm).')
                if kind == 'strip' and on is None:
                    raise ValidationError(f'Mark {i + 1}: a shield is stripped back from a connector: pick its branch.')
                text = ' '.join(f('text').split())[:100]
                if kind == 'splice' and text.lower() not in splices:
                    raise ValidationError(f'Mark {i + 1}: pick which splice.')
                mark = mark or HarnessMark(harness=item)
                mark.kind, mark.on, mark.start, mark.end, mark.text = kind, on, start, end, text
                mark.wire_set = f('set')[:20] if kind == 'strip' else ''
                mark.used = _definition(f('definition'), i + 1) if kind in ('tie', 'sleeve', 'shrink') else None
                mark.save()
        messages.success(request, 'The bundle is saved.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item.get_absolute_url() + '#bundle')


def _marks_on_line(item, a, b, post):
    """A mark put on the bundle between connectors ``a`` and ``b``, ``from`` (and ``to``) mm from ``a``: on a's branch,
    the trunk or b's branch, as far along as that is (a stretch over more than one of them: a piece on each)."""
    kinds = dict(HarnessMark.Kind.choices)
    kind = post.get('kind', '')
    if kind not in kinds:
        raise ValidationError('What is it?')
    length = _path(a, b)
    if length is None:
        raise ValidationError(f'Give {a.designator} and {b.designator} their places along the trunk first (the Bundle tab).')
    start = _mm(post.get('from'), 'It', 'place')
    if start is None:
        raise ValidationError('How far along is it?')
    stretch = kind in HarnessMark.STRETCHES
    end = _mm(post.get('to'), 'It', 'end') if stretch else None
    if stretch and (end is None or end <= start):
        raise ValidationError(f'A {kinds[kind].lower()} goes from one place to a further one.')
    if max(start, end or start) > length:
        raise ValidationError(f'{a.designator} to {b.designator} is {qty(length)} mm long.')
    ra, rb, span = a.reach or 0, b.reach or 0, abs(b.along - a.along)
    sign = 1 if b.along >= a.along else -1

    def at(d):   # (on, place) of the point ``d`` mm from a
        if d < ra:
            return a, d
        if d <= ra + span:
            return None, a.along + sign * (d - ra)
        return b, length - d
    if stretch:   # cut where the line goes from one part to the next
        cuts = sorted({start, end} | {c for c in (ra, ra + span) if start < c < end})
        pieces = []
        for lo, hi in zip(cuts, cuts[1:]):
            on, p0 = at(lo + (hi - lo) / 2)   # (the piece's part: by its middle)
            q0, q1 = (lo, hi)
            if on is a:
                pieces.append((on, q0, q1))
            elif on is b:
                pieces.append((on, length - q1, length - q0))
            else:
                t0, t1 = a.along + sign * (q0 - ra), a.along + sign * (q1 - ra)
                pieces.append((None, min(t0, t1), max(t0, t1)))
    else:
        on, place = at(start)
        pieces = [(on, place, None)]
    text = ' '.join(post.get('text', '').split())[:100]
    if kind == 'splice' and text.lower() not in {x.lower() for x in _splices(item.ordered_wires())}:
        raise ValidationError('Which splice?')
    if kind == 'strip' and pieces[0][0] is None:
        raise ValidationError('A shield is stripped back on a connector\'s branch, from the connector.')
    found = _definition(post.get('definition', '').strip(), 1) if kind in ('tie', 'sleeve', 'shrink') else None
    for on, p0, p1 in pieces:
        mark = HarnessMark(harness=item, kind=kind, on=on, start=p0, end=p1, text=text,
                           wire_set=post.get('set', '')[:20] if kind == 'strip' else '')
        mark.used = found
        mark.save()


@login_required
@require_POST
def bundle_lengths(request, pk):
    """Each wire's length set from the bundle: down its connectors' branches and along the trunk between them."""
    item = get_object_or_404(Harness, pk=pk)
    done = 0
    for w in item.ordered_wires():
        length = _path(w.from_end, w.to_end)
        if length is not None and w.length != length:
            Wire.objects.filter(pk=w.pk).update(length=length)
            done += 1
    messages.success(request, f'{done} wire{"" if done == 1 else "s"} given {"its" if done == 1 else "their"} length from the bundle.')
    return redirect(item.get_absolute_url() + '#bundle')


def _safe(name):
    """``name`` as part of a file's name."""
    return ''.join(c for c in name if c not in '\\/:*?"<>|').strip()[:80]


@login_required
@require_POST
def harness_import(request):
    """A harness made from a file (``transfer.FORMAT``: from ⬇ JSON, by hand, by another program), in the setup
    picked (or none)."""
    import json

    from .transfer import import_harness
    setup = Setup.objects.filter(pk=request.POST.get('setup') or 0).first()
    sent = request.FILES.get('file')
    try:
        if sent is None:
            raise ValidationError('Pick a harness file.')
        try:
            data = json.loads(sent.read().decode('utf-8-sig'))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError('That is not a harness file (JSON).')
        harness, notes = import_harness(data, setup)
    except ValidationError as exc:
        errors(request, exc)
        return redirect(reverse('harnesses:list') + (f'?setup={setup.pk}' if setup else ''))
    messages.success(request, f'{harness.number} {harness.name} is made from {sent.name}.')
    for note in notes:
        messages.warning(request, note)
    return redirect(harness)


@login_required
def harness_format(request):
    """What a harness file holds (to give to whoever, or whatever, makes one), with this Osmia's families."""
    from .transfer import describe
    response = HttpResponse(describe(), content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="osmia harness format.md"'
    return response


def _groups(harness, wires):
    """The groups its wires are in (natural order), each with its lengths: [HarnessGroup, saved or not]."""
    from .models import HarnessGroup
    kept = {g.name: g for g in harness.groups.all()}
    names = sorted({w.wire_group for w in wires if w.wire_group}, key=pin_order)
    return [kept.get(n) or HarnessGroup(harness=harness, name=n) for n in names]


@login_required
@require_POST
def group_lengths(request, pk):
    """Each group's total length and how much of it runs bundled together with the other sets (from the form of the
    harness's Groups); a group no wire is in any more goes."""
    from .models import HarnessGroup
    item = get_object_or_404(Harness, pk=pk)
    groups = _groups(item, item.ordered_wires())
    try:
        with transaction.atomic():
            for i, g in enumerate(groups):
                g.length = _number(request.POST.get(f'length_{i}', '').strip(), i + 1, 'total length')
                g.bundled = _number(request.POST.get(f'bundled_{i}', '').strip(), i + 1, 'bundled length')
                if g.length is not None and g.bundled is not None and g.bundled > g.length:
                    raise ValidationError(f'{g.name}: it can\'t run bundled for longer than it is.')
                g.save()
            item.groups.exclude(name__in=[g.name for g in groups]).delete()
        messages.success(request, 'The lengths of the groups are saved.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item.get_absolute_url() + '#groups')


def _picked_as(found):
    """What the family popup shows as picked for an end: its family or gender (an item definition: the gender or family it is in)."""
    if found is None:
        return ''
    if isinstance(found, ItemDefinition):
        return (found.branch or found.family or found).number
    return found.number


def _drawing(harness, wires):
    """What the pinout drawing draws: each end (the pins its wires use, in the layout of its item definition or family) and the
    wires between their contact numbers. (What it plugs into is its setup's to say.)"""
    from devices.models import pin_order
    ends = harness.ends.select_related('definition__family', 'family', 'branch__family')
    out = []
    for end in ends:
        pins = {}
        for w in wires:
            for at, pin in ((w.from_end_id, w.from_pin), (w.to_end_id, w.to_pin)):
                if at == end.pk and pin:   # (a shield joined on one side only has no pin on the other)
                    pins.setdefault(pin, '')
        numbers = sorted(pins, key=pin_order)
        out.append({'id': end.pk, 'designator': end.designator, 'what': end.used_name, 'along': qty(end.along), 'reach': qty(end.reach),
                    'side': end.side, 'used': _picked_as(end.used), 'face': drawn(end.used, numbers), 'pins': [[n, pins[n]] for n in numbers]})
    lengths = {g.name: {'length': qty(g.length), 'bundled': qty(g.bundled), 'breakout': g.breakout} for g in harness.groups.all()}
    bundle = {'kinds': HarnessMark.Kind.choices, 'splices': _splices(wires),   # the bundle mode: what is along it
              'marks': [{'id': m.pk, 'kind': m.kind, 'label': m.get_kind_display(), 'on': m.on_id, 'start': qty(m.start), 'end': qty(m.end),
                         'text': m.text, 'set': m.wire_set, 'what': m.used_name} for m in harness.marks.select_related('definition', 'family', 'branch')]}
    return {'colours': COLOURS, 'set_types': PIN_SET_TYPES, 'purposes': purposes.tree(), 'ends': out, 'groups': lengths, 'bundle': bundle, 'wires': [{'id': w.pk, 'from': w.from_end_id, 'from_pin': w.from_pin, 'to': w.to_end_id, 'to_pin': w.to_pin, 'signal': w.signal,
                                    'to_signal': w.to_signal, 'group': w.wire_group, 'set': w.wire_set, 'type': w.set_type, 'colour': w.colour, 'gauge': w.gauge, 'length': qty(w.length)} for w in wires]}


@login_required
@require_POST
def pinout_draw(request, pk):
    """The pinout edited in its drawing: a wire added between two pins (its signal and set from the device's pin), a
    wire put in a set (an existing one, a new one, or as a shielded set's shield), a set's type changed (all its
    wires; or a wire made its shield), a set put in a group (a name tag over sets: "Channel 1"; a wire in no set on its
    own), coloured, labelled, its gauge given, or taken away; connectors added on a side, changed, taken away.
    Answers with the drawing as it is now."""
    item = get_object_or_404(Harness, pk=pk)
    post, action = request.POST, request.POST.get('action')
    if action in ('end_add', 'end_set', 'end_delete'):   # a connector added on a side, its family changed, taken away
        from inventory.picker import with_gender
        found = definition_or_family(with_gender(post.get('used'))) if post.get('used') else None
        if action != 'end_delete' and post.get('used') and found is None:
            return JsonResponse({'error': f'There is no family "{post.get("used")}".'}, status=400)
        if action == 'end_add':
            taken, n = {d.upper() for d in item.ends.values_list('designator', flat=True)}, 1
            while f'P{n}' in taken:
                n += 1
            end = HarnessEnd(harness=item, designator=f'P{n}', side=post.get('side') if post.get('side') in ('left', 'right') else '',
                             position=(item.ends.aggregate(n=Max('position'))['n'] or 0) + 1)
            end.used = found
            end.save()
        else:
            end = get_object_or_404(HarnessEnd, pk=post.get('end') or 0, harness=item)
            if action == 'end_delete':
                end.delete()   # with its wires
            else:
                end.used = found
                end.save()
        return JsonResponse(_drawing(item, item.ordered_wires()))
    if action == 'shield':   # a shielded set's shield wire joined to a contact on each side ('' on a side: not there)
        name = post.get('set', '').strip()[:20]
        a = item.ends.filter(pk=post.get('a_end') or 0).first()
        b = item.ends.filter(pk=post.get('b_end') or 0).first()
        if not (name and a and b and item.wires.filter(wire_set=name).exists()):
            return JsonResponse({'error': "A set's shield goes from one of its ends to the other."}, status=400)
        a_pin, b_pin = post.get('a_pin', '').strip()[:20], post.get('b_pin', '').strip()[:20]
        shield = item.wires.filter(wire_set=name, set_type='Shield').first()
        if not (a_pin or b_pin):
            if shield:
                shield.delete()
        else:
            group = item.wires.filter(wire_set=name).exclude(set_type='Shield').values_list('wire_group', flat=True).first() or ''
            shield = shield or Wire(harness=item, wire_set=name, set_type='Shield', signal='Shield', colour='grey', wire_group=group)
            shield.from_end, shield.from_pin, shield.to_end, shield.to_pin = a, a_pin, b, b_pin
            shield.save()
        return JsonResponse(_drawing(item, item.ordered_wires()))
    if action in ('mark_add', 'mark_set', 'mark_delete'):   # the bundle mode: put along the bundle between two connectors
        try:
            with transaction.atomic():
                if action != 'mark_add':
                    get_object_or_404(HarnessMark, pk=post.get('mark') or 0, harness=item).delete()
                if action != 'mark_delete':
                    a = get_object_or_404(HarnessEnd, pk=post.get('a_end') or 0, harness=item)
                    b = get_object_or_404(HarnessEnd, pk=post.get('b_end') or 0, harness=item)
                    _marks_on_line(item, a, b, post)
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        return JsonResponse(_drawing(item, item.ordered_wires()))
    if action == 'add':
        a = item.ends.filter(pk=post.get('from_end') or 0).first()
        b = item.ends.filter(pk=post.get('to_end') or 0).first()
        from_pin, to_pin = post.get('from_pin', '').strip()[:20], post.get('to_pin', '').strip()[:20]
        if not (a and b and from_pin and to_pin):
            return JsonResponse({'error': "A wire goes from a connector's pin to a connector's pin."}, status=400)
        if a == b and from_pin.lower() == to_pin.lower():
            return JsonResponse({'error': 'A loopback goes to another pin.'}, status=400)
        Wire.objects.create(harness=item, from_end=a, from_pin=from_pin, to_end=b, to_pin=to_pin)
    else:
        wire = get_object_or_404(Wire, pk=post.get('wire') or 0, harness=item)
        if action == 'delete':
            wire.delete()
        elif action == 'colour':
            wire.colour = post.get('colour') if post.get('colour') in COLOURS else ''
            wire.save()
        elif action == 'signal':   # what it is for: PWR, GND, TX+, …; a loopback's other end its own (TX: RX)
            value = ' '.join(post.get('signal', '').split())[:100]
            if post.get('end') == 'to':
                wire.to_signal = value
            else:
                if wire.from_end_id == wire.to_end_id and wire.to_signal in ('', purposes.mate(wire.signal)):
                    wire.to_signal = purposes.mate(value)
                wire.signal = value
            wire.save()
        elif action == 'gauge':   # a bare number is taken as AWG
            value = ' '.join(post.get('gauge', '').split())
            wire.gauge = (f'{value} AWG' if value.isdigit() else value)[:20]
            wire.save()
        elif action == 'set':
            value = post.get('set', '').strip()
            if value.startswith('new:'):
                taken, n = set(item.wires.values_list('wire_set', flat=True)), 1
                while str(n) in taken:
                    n += 1
                kind = value[4:]
                wire.wire_set, wire.set_type = str(n), kind if kind in PIN_SET_TYPES else 'Straight'
            elif value.startswith('shield:'):
                wire.wire_set, wire.set_type = value[7:][:20], 'Shield'
            elif wire.wire_set == value:
                pass
            elif value:
                mate = item.wires.filter(wire_set=value).exclude(pk=wire.pk).exclude(set_type='Shield').first()
                wire.wire_set, wire.set_type = value[:20], mate.set_type if mate else 'Straight'
                if mate:   # into the set's group too
                    wire.wire_group = mate.wire_group
            else:
                wire.wire_set, wire.set_type = '', 'Straight'
            wire.save()
        elif action == 'group':   # a name tag over sets: the wire's whole set goes into it (a wire in no set: just it)
            value = ' '.join(post.get('group', '').split())[:40]
            if wire.wire_set:
                item.wires.filter(wire_set=wire.wire_set).update(wire_group=value)
            else:
                Wire.objects.filter(pk=wire.pk).update(wire_group=value)
        elif action == 'set_type':   # the whole set goes together so now; or this wire is the set's shield
            kind = post.get('type', '')
            if not wire.wire_set or kind not in SET_TYPES:
                return JsonResponse({'error': 'A wire in a set, and a set type.'}, status=400)
            if kind == 'Shield':
                wire.set_type = 'Shield'
                wire.save()
            else:
                Wire.objects.filter(pk=wire.pk).update(set_type=kind)
                item.wires.filter(wire_set=wire.wire_set).exclude(set_type='Shield').update(set_type=kind)
        else:
            return JsonResponse({'error': 'Nothing to do.'}, status=400)
    return JsonResponse(_drawing(item, item.ordered_wires()))


# -- Editing as tables -------------------------------------------------------------------------------

def _definition(number, row):
    """The item definition (or family) a row names."""
    if not number:
        return None
    definition = definition_or_family(number)
    if definition is None:
        raise ValidationError(f'Row {row}: there is no item definition or family "{number}".')
    return definition


def _number(text, row, what):
    if not text:
        return None
    try:
        value = Decimal(text.replace(',', '.'))
    except InvalidOperation:
        raise ValidationError(f'Row {row}: the {what} "{text}" is not a number.')
    if not value.is_finite() or value < 0:
        raise ValidationError(f'Row {row}: the {what} can\'t be below zero.')
    return value


def _edit(request, harness, title, columns, records, values, apply):
    """A page editing ``records`` of ``harness`` as a table: ``apply(row, record or None, values)`` saves one row."""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for row, record_id, gone, cells in rows.read(request.POST, columns):
                    record = next((r for r in records if r.pk == record_id), None) if record_id else None
                    if record_id and record is None:
                        continue
                    if gone:
                        record.delete()
                    else:
                        apply(row, record, cells)
        except ValidationError as exc:
            errors(request, exc)
            return redirect(request.path)
        messages.success(request, f'{title} of {harness.number} is saved.')
        return redirect(harness)
    return render(request, 'harnesses/edit.html', {
        'harness': harness, 'title': title, 'columns': columns, 'rows': rows.rows(records, values, blank=5),
        'definition_numbers': choices_of_definitions()})


@login_required
def ends(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    columns = [rows.Column('designator', 'Connector', width='80px'), rows.Column('definition', 'Connector item definition or family', datalist='definitions', width='220px')]
    records = list(item.ends.select_related('definition', 'family'))

    def apply(row, end, cells):
        if not cells['designator']:
            raise ValidationError(f'Row {row}: give the connector a name, e.g. P1.')
        clash = item.ends.filter(designator__iexact=cells['designator']).exclude(pk=getattr(end, 'pk', None))
        if clash.exists():
            raise ValidationError(f'Row {row}: there is already a connector {cells["designator"]}.')
        end = end or HarnessEnd(harness=item, position=item.ends.count())
        end.designator, end.used = cells['designator'][:30], _definition(cells['definition'], row)
        end.save()
    return _edit(request, item, 'The connectors', columns, records,
                 lambda e: {'designator': e.designator, 'definition': e.used_name}, apply)


@login_required
def pinout(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    end_list = list(item.ends.all())
    if not end_list:
        messages.error(request, 'Give the harness its ends first.')
        return redirect('harnesses:ends', pk)
    choices = [(e.pk, e.designator) for e in end_list]
    columns = [rows.Column('from_end', 'From', 'select', choices), rows.Column('from_pin', 'Pin', width='60px'),
               rows.Column('to_end', 'To', 'select', choices), rows.Column('to_pin', 'Pin', width='60px'),
               rows.Column('signal', 'Signal', width='120px'), rows.Column('wire_group', 'Group', width='100px'),
               rows.Column('wire_set', 'Set', width='60px'),
               rows.Column('set_type', 'Set type', 'select', [(t, t) for t in SET_TYPES]),
               rows.Column('colour', 'Colour', 'select', [(c, c) for c in COLOURS]), rows.Column('gauge', 'Gauge', width='80px'),
               rows.Column('length', 'Length (mm)', 'number', width='80px'), rows.Column('definition', 'Wire item definition or family', datalist='definitions', width='160px')]
    ends_by_id = {e.pk: e for e in end_list}
    records = item.ordered_wires()

    def apply(row, wire, cells):
        a, b = ends_by_id.get(int(cells['from_end'] or 0)), ends_by_id.get(int(cells['to_end'] or 0))
        if a is None or b is None or not cells['from_pin'] or not cells['to_pin']:
            raise ValidationError(f'Row {row}: a wire goes from a connector\'s pin to a connector\'s pin.')
        signal, wire_set = cells['signal'], cells['wire_set']
        set_type = cells['set_type'] if cells['set_type'] in SET_TYPES else 'Straight'
        wire = wire or Wire(harness=item)
        wire.from_end, wire.from_pin, wire.to_end, wire.to_pin = a, cells['from_pin'][:20], b, cells['to_pin'][:20]
        wire.signal, wire.wire_set, wire.gauge, wire.set_type = signal[:100], wire_set[:20], cells['gauge'][:20], set_type
        wire.wire_group = ' '.join(cells['wire_group'].split())[:40]
        wire.colour = cells['colour'] if cells['colour'] in COLOURS else ''
        wire.length, wire.used = _number(cells['length'], row, 'length'), _definition(cells['definition'], row)
        wire.save()
    return _edit(request, item, 'The pinout', columns, records, lambda w: {
        'from_end': w.from_end_id, 'from_pin': w.from_pin, 'to_end': w.to_end_id, 'to_pin': w.to_pin, 'signal': w.signal,
        'wire_group': w.wire_group, 'wire_set': w.wire_set, 'set_type': w.set_type, 'colour': w.colour, 'gauge': w.gauge,
        'length': f'{w.length.normalize():f}' if w.length is not None else '', 'definition': w.used_name}, apply)


@login_required
def items(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    columns = [rows.Column('definition', 'Item definition or family', datalist='definitions', width='180px'), rows.Column('quantity', 'Quantity', 'number', width='90px'),
               rows.Column('note', 'Note', width='240px')]

    def apply(row, line, cells):
        quantity = _number(cells['quantity'], row, 'quantity')
        definition = _definition(cells['definition'], row)
        if definition is None or not quantity:
            raise ValidationError(f'Row {row}: give the item definition and how many.')
        line = line or HarnessItem(harness=item)
        line.used, line.quantity, line.note = definition, quantity, cells['note'][:200]
        line.save()
    return _edit(request, item, 'The other items', columns, list(item.items.select_related('definition', 'family')),
                 lambda i: {'definition': i.used_name, 'quantity': f'{i.quantity.normalize():f}', 'note': i.note}, apply)


# -- Versions ------------------------------------------------------------------------------------------

@login_required
@require_POST
def save_version(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    try:
        version = versions.save(item, request.user, request.POST.get('note', ''))
        messages.success(request, f'{item.number} is saved as v{version.number}.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
def version(request, pk, number):
    item = get_object_or_404(Harness, pk=pk)
    saved = get_object_or_404(HarnessVersion, harness=item, number=number)
    return render(request, 'harnesses/version.html', {'harness': item, 'version': saved, 'data': saved.data, 'definitions': parts_of(saved.data)})


@login_required
@require_POST
def restore(request, pk, number):
    item = get_object_or_404(Harness, pk=pk)
    versions.restore(item, get_object_or_404(HarnessVersion, harness=item, number=number))
    messages.success(request, f'{item.number} is as it was in v{number}: save a version to keep it.')
    return redirect(item)


# -- Harnesses built: each a record with an asset tag -------------------------------------------------------------------

@transaction.atomic
def build(harness, number, version, user, take_from=None):
    """A harness built: a record of it with its asset tag (``number``), of the version it is built to (else as it is
    now), being built, with a checklist of its wires; what it is made of taken out of ``take_from`` when given."""
    from records.models import Record, RecordCheck
    from records.service import event
    number = (number or '').strip()
    if not number:
        raise ValidationError('Give it an asset tag.')
    if Record.objects.filter(tag__iexact=number).exists():
        raise ValidationError(f'There is already an asset {number}.')
    data = version.data if version else harness.snapshot()
    if not data.get('wires'):
        raise ValidationError(f'{harness.number} has no pinout yet.')
    asset = Record.objects.create(tag=number[:100], harness=harness, version=version.number if version else None,
                                  status=Record.Status.BUILDING, built_by=user, built_on=date.today())
    RecordCheck.objects.bulk_create(RecordCheck(
        record=asset, position=i, wire=f'{w["from"]}:{w["from_pin"]} → {w["to"]}:{w["to_pin"]}', between=f'{w["from"]} → {w["to"]}',
        signal=w.get('signal', ''), colour=w.get('colour', ''), wire_set=w.get('set', '')) for i, w in enumerate(data['wires']))
    if take_from is not None:
        for definition, quantity in parts_of(data):
            take = stock.use_any if isinstance(definition, DefinitionGroup) else stock.use
            take(definition, quantity, take_from, user, note=f'built into {asset.tag}')
    event(asset, 'built', user, f'{harness.number}' + (f' v{version.number}' if version else ''))
    return asset


@login_required
@require_POST
def unit_add(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    version_pk = request.POST.get('version')
    chosen = item.versions.filter(pk=version_pk).first() if version_pk else None
    where = Location.objects.filter(pk=request.POST.get('take_from') or 0).first()
    try:
        asset = build(item, request.POST.get('serial'), chosen, request.user, where)
    except ValidationError as exc:
        errors(request, exc)
        return redirect(item)
    return redirect(asset)
