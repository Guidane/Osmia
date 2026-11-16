"""Records: the assets list (the records with an asset tag: the categories of their item definitions as a tree on the left,
the assets of the one picked in the middle, by status, those due for calibration; the details of the one picked on the
right), a record's page (an asset's: checking it out and back, calibration, sending it away, moving it, a harness's
checklist, its history), a new asset made by hand, the asset fields."""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from inventory import attributes as kept
from inventory.attributes import RecordStore
from inventory.forms import AttributesForm
from inventory.models import Attribute, Category, ItemDefinition, Location
from web import excel
from web.forms import initial_for
from web.shortcuts import errors

from . import service
from .models import Record


class RecordForm(AttributesForm):
    """An asset (a record with an asset tag), and the asset fields; a record without one: its notes and price."""
    tree_fields = {'location': Location}

    class Meta:
        model = Record
        fields = ['tag', 'definition', 'asset_number', 'serial', 'device', 'harness', 'version', 'location', 'keeper',
                  'price', 'calibrated_on', 'calibration_months', 'built_on', 'notes']
        widgets = {'calibrated_on': forms.DateInput(attrs={'type': 'date'}), 'built_on': forms.DateInput(attrs={'type': 'date'}),
                   'notes': forms.Textarea(attrs={'rows': 3})}

    def common(self):
        return Attribute.asset_fields() if self.tagged else []

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        self.tagged = instance is None or bool(instance.tag)
        super().__init__(*args, **kwargs)
        if not self.tagged:   # so many of an item definition: what it cost, notes
            for name in list(self.fields):
                if name not in ('price', 'notes'):
                    del self.fields[name]
            return
        self.fields['tag'].required = True
        self.fields['definition'].queryset = ItemDefinition.objects.filter(is_asset=True)

    def clean(self):
        data = super().clean()
        if self.tagged and sum(bool(data.get(k)) for k in ('definition', 'device', 'harness')) != 1:
            raise forms.ValidationError('Say what it is: an item definition, a device or a harness.')
        return data


def _assets(request):
    """The assets (records with an asset tag) the list shows, and what it is narrowed by."""
    q = request.GET.get('q', '').strip()
    found = Record.objects.exclude(tag=None).select_related('definition__category', 'harness', 'device', 'location', 'keeper', 'holder')
    for word in q.split():
        found = found.filter(Q(tag__icontains=word) | Q(asset_number__icontains=word) | Q(serial__icontains=word)
                             | Q(definition__number__icontains=word) | Q(definition__description__icontains=word)
                             | Q(definition__manufacturer__icontains=word) | Q(definition__mpn__icontains=word)
                             | Q(harness__name__icontains=word) | Q(device__name__icontains=word))
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    built = request.GET.get('built', '')
    if category is not None:
        found = found.filter(definition__category_id__in=category.below())
    elif built == 'harness':
        found = found.exclude(harness=None)
    elif built == 'device':
        found = found.exclude(device=None)
    status = request.GET.get('status', '')
    if status in Record.Status.values:
        found = found.filter(status=status)
    elif not request.GET.get('all'):
        found = found.exclude(status=Record.Status.RETIRED)
    return q, category, built, status, found


@login_required
def asset_list(request):
    from web import browse
    q, category, built, status, found = _assets(request)
    fields = Attribute.asset_fields()
    found = kept.filtered(found, fields, request.GET, RecordStore())
    assets = list(found)
    if request.GET.get('due'):
        due = {a.pk for a in service.due()}
        assets = [a for a in assets if a.pk in due]
    if request.GET.get('export'):
        values = dict(kept.columns(assets, fields, RecordStore()))
        return excel.download('assets', [('Assets', ['Asset tag', 'Asset number', 'Item definition', 'Name', 'Category', 'Serial number',
                                                     'Location', 'Keeper', 'Status', 'Out with', 'Calibrated', 'Due'] + [f.name for f in fields],
                                          [(a.tag, a.asset_number, a.thing.number if a.thing else '', a.name,
                                            a.definition.category.path if a.definition and a.definition.category else '',
                                            a.serial, a.location.path if a.location else '', str(a.keeper or ''), a.get_status_display(),
                                            str(a.holder or ''), a.calibrated_on, a.calibration_due, *values[a]) for a in assets])])
    every = Record.objects.exclude(tag=None).exclude(status=Record.Status.RETIRED)
    counts = {}
    for c in every.exclude(definition=None).values_list('definition__category', flat=True):
        counts[c] = counts.get(c, 0) + 1
    tree = Category.ordered()
    keep = set()
    for c, _ in tree:   # the categories with assets in them, and those above them
        if counts.get(c.pk):
            keep.update(c.chain_pks())
    tree = [(c, d) for c, d in tree if c.pk in keep]
    children = {}
    for c, _ in tree:
        children.setdefault(c.parent_id, []).append(c.pk)

    def counted(pk):   # its assets and those of the categories under it
        return counts.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    keep_q = f'&q={q}' if q else ''
    nodes = [browse.node('All assets', f'?{keep_q[1:]}', every.count(), category is None and not built)]
    nodes += [{**browse.node(c.name, f'?category={c.pk}{keep_q}', counted(c.pk), category is not None and category.pk == c.pk),
               'depth': depth + 1, 'open': category is not None and c.pk in category.chain_pks()} for c, depth in tree]
    for key, label in (('harness', 'Harnesses built'), ('device', 'Devices')):
        n = every.exclude(**{key: None}).count()
        if n:
            nodes.append(browse.node(label, f'?built={key}{keep_q}', n, built == key))
    picked = Record.objects.filter(pk=request.GET.get('asset') or 0).first()
    return render(request, 'records/assets.html', {
        'rows': kept.columns(assets, fields, RecordStore()), 'attributes': fields, 'filters': kept.filters(fields, request.GET),
        'q': q, 'category': category, 'built': built, 'status': status, 'nodes': nodes,
        'statuses': Record.Status.choices, 'picked': picked, 'brief': _brief(picked) if picked else None})


def _brief(record):
    """What the details beside a list show of ``record``."""
    return {'record': record, 'attributes': kept.shown(record, None) if record.tag else [],
            'events': record.events.select_related('user')[:8]}


@login_required
def record_brief(request, pk):
    """The details of a record beside a list (fetched when one is picked)."""
    item = get_object_or_404(Record.objects.select_related('definition', 'location', 'keeper', 'holder', 'device', 'harness'), pk=pk)
    return render(request, 'records/_brief.html', _brief(item))


@login_required
def record_form(request, pk=None):
    """A record changed, or a new asset made by hand (``?definition=``, or a device's or harness's: ``?device=``)."""
    item = get_object_or_404(Record, pk=pk) if pk else None
    initial = initial_for(item, **{k: request.GET.get(k) for k in ('definition', 'device', 'harness', 'tag', 'version')})
    if item is None and not initial.get('tag'):
        prefix = next((x.number for x in (ItemDefinition.objects.filter(pk=request.GET.get('definition') or 0).first(),)
                       if x is not None), 'A')
        initial['tag'] = service.next_tag(prefix)
    form = RecordForm(request.POST or None, instance=item, initial=initial)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    return render(request, 'inventory/attributes_form.html', {'form': form, 'title': f'Change {item}' if item else 'New asset',
                                                              'back': item.get_absolute_url() if item else None})


@login_required
def record(request, pk):
    item = get_object_or_404(Record.objects.select_related('definition__category', 'location', 'keeper', 'holder', 'device', 'harness',
                                                           'order_line__order__vendor'), pk=pk)
    checks = list(item.checks.all())
    return render(request, 'records/record.html', {
        'record': item, 'events': item.events.select_related('user')[:100],
        'attributes': kept.shown(item, None) if item.tag else [],
        'checks': checks, 'placed': sum(c.placed for c in checks), 'verified': sum(c.verified for c in checks),
        'people': get_user_model().objects.filter(is_active=True), 'today': date.today(), 'locations': Location.ordered()})


@login_required
@require_POST
def act(request, pk):
    """Check it out or back, record a calibration, send it away, move it."""
    item = get_object_or_404(Record, pk=pk)
    post, action, note = request.POST, request.POST.get('action'), request.POST.get('note', '')
    try:
        if not item.tag:
            raise ValidationError('Only an asset is checked out, calibrated or sent away.')
        if action == 'out':
            to = get_user_model().objects.filter(pk=post.get('to') or 0, is_active=True).first()
            service.check_out(item, request.user, to, note)
        elif action == 'back':
            service.bring_back(item, request.user, note)
        elif action == 'calibrated':
            on = post.get('on')
            service.calibrated(item, request.user, date.fromisoformat(on) if on else None, note)
        elif action == 'move':
            service.move(item, Location.objects.filter(pk=post.get('location') or 0).first(), request.user, note)
        elif action in service.AWAY:
            service.send_away(item, request.user, action, note)
        else:
            raise ValidationError('What happened to it?')
    except ValueError:
        messages.error(request, 'That is not a date.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
@require_POST
def checklist(request, pk):
    """A harness built: its wires ticked as placed, then verified; when every one is, it is available."""
    item = get_object_or_404(Record, pk=pk)
    checks = list(item.checks.all())
    try:
        with transaction.atomic():
            for check in checks:
                check.placed = f'placed_{check.pk}' in request.POST
                check.verified = f'verified_{check.pk}' in request.POST
                if check.verified and not check.placed:
                    raise ValidationError(f'{check.wire}: place it before verifying it.')
                check.save(update_fields=['placed', 'verified'])
            if checks and all(c.verified for c in checks) and item.status == Record.Status.BUILDING:
                item.status = Record.Status.AVAILABLE
                item.save(update_fields=['status'])
                service.event(item, 'built', request.user, 'every wire verified')
                messages.success(request, f'{item.tag}: every wire is verified.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


# -- the asset fields: what every asset fills in, whatever it is ---------------------------------------------------

@login_required
def fields(request, pk=None):
    """The asset fields (a list, each changed, moved or taken away) and a new one added."""
    from inventory.forms import AttributeForm
    current = get_object_or_404(Attribute, pk=pk, category=None) if pk else None
    form = AttributeForm(request.POST or None, instance=current, category=None)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved.name} is saved.')
        return redirect('records:fields')
    if current is not None:
        return render(request, 'web/form.html', {'form': form, 'title': f'Asset field {current.name}', 'back': reverse('records:fields')})
    return render(request, 'records/fields.html', {'fields': Attribute.asset_fields(), 'form': form})


@login_required
@require_POST
def field_delete(request, pk):
    found = get_object_or_404(Attribute, pk=pk, category=None)
    found.delete()
    messages.success(request, f'{found.name} is taken away, with what was filled in for it.')
    return redirect('records:fields')


@login_required
@require_POST
def field_move(request, pk):
    order = Attribute.asset_fields()
    found = get_object_or_404(Attribute, pk=pk, category=None)
    i = order.index(found)
    j = i - 1 if request.POST.get('to') == 'up' else i + 1
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
        for position, a in enumerate(order):
            Attribute.objects.filter(pk=a.pk).update(position=position)
    return redirect('records:fields')
