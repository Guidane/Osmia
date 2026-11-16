"""Item definitions (finding them, their page with their records (the stock), history and orders), locations, vendors and
categories."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from orders import service as orders
from web import excel
from web.templatetags.osmia import qty
from web.shortcuts import edit_page, errors
from web.forms import initial_for

from . import attributes as attributes_kept
from records.models import Record

from . import stock
from .attributes import DefinitionStore
from .forms import AttributeForm, BranchForm, CategoryForm, FamilyBranchForm, FamilyForm, LocationForm, DefinitionForm, VendorForm
from .models import Attribute, Branch, Category, Family, FamilyBranch, Location, ItemDefinition, DefinitionLink, DefinitionValue, Vendor

PAGE = 200   # item definitions listed at most



def search(found, q):
    """Item definitions with every word of ``q`` in their number, description, manufacturer or numbers."""
    for word in q.split():
        found = found.filter(Q(number__icontains=word) | Q(description__icontains=word) | Q(manufacturer__icontains=word)
                             | Q(mpn__icontains=word) | Q(vendor_number__icontains=word))
    return found


@login_required
def find(request):
    """Item definitions matching ?q= (words) and ?category= (with those under it), for finding one to pick: JSON."""
    found = search(ItemDefinition.objects.filter(active=True).select_related('category').annotate(have=Sum('records__quantity')),
                   request.GET.get('q', '').strip())
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    if category is not None:
        found = found.filter(category_id__in=category.below())
    return JsonResponse({'definitions': [{'number': p.number, 'description': p.description, 'category': p.category.name if p.category else '',
                                    'have': qty(p.have or 0), 'unit': p.get_unit_display(), 'price': qty(p.price)}
                                   for p in found[:60]], 'more': found.count() > 60})


@login_required
def definitions(request):
    q = request.GET.get('q', '').strip()
    found = search(ItemDefinition.objects.select_related('category', 'vendor').annotate(have=Sum('records__quantity')), q)
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    attributes = category.all_attributes() if category else []
    if category is not None:
        found = attributes_kept.filtered(found.filter(category_id__in=category.below()), attributes, request.GET, DefinitionStore())
    if not request.GET.get('all'):
        found = found.filter(active=True)
    if request.GET.get('export'):
        return excel.download('definitions', _definition_sheets(found))
    if q and found.count() == 1:
        return redirect(found.get())
    tree = Category.ordered()
    own = dict(ItemDefinition.objects.filter(active=True).values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    children = {}
    for c, _ in tree:
        children.setdefault(c.parent_id, []).append(c.pk)

    def counted(pk):   # its item definitions and those of the categories under it
        return own.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    picked = ItemDefinition.objects.filter(pk=request.GET.get('definition') or 0).first()
    return render(request, 'inventory/definitions.html', {
        'rows': attributes_kept.columns(list(found[:PAGE]), attributes, DefinitionStore()), 'count': found.count(), 'q': q,
        'category': category, 'categories': [(c, depth, counted(c.pk)) for c, depth in tree], 'page': PAGE,
        'attributes': attributes, 'filters': attributes_kept.filters(attributes, request.GET),
        'every': ItemDefinition.objects.filter(active=True).count(), 'open': set(category.chain_pks()) if category else set(),
        'picked': picked, 'brief': _brief(picked) if picked else None})


def _brief(definition):
    """What the details beside the list show of ``definition``."""
    return {'definition': definition, 'attributes': attributes_kept.shown(definition, definition.category),
            'stock': stock.in_stock(definition), 'on_hand': definition.on_hand,
            'on_order': orders.on_order(definition)}


@login_required
def definition_brief(request, pk):
    """The details of an item definition beside the parts list (fetched when one is picked)."""
    definition = get_object_or_404(ItemDefinition.objects.select_related('category', 'vendor', 'family', 'branch'), pk=pk)
    return render(request, 'inventory/_definition_brief.html', _brief(definition))


def _definition_sheets(definitions):
    definitions = list(definitions)
    return [('Item definitions', ['Item number', 'Kind', 'Description', 'Category', 'Manufacturer', 'Manufacturer part number', 'Unit', 'Vendor',
                       "Vendor's number", 'Last price', 'Minimum', 'On hand', 'Active'],
             [(p.number, p.get_kind_display(), p.description, p.category.path if p.category else '', p.manufacturer, p.mpn, p.unit,
               p.vendor.name if p.vendor else '', p.vendor_number, p.price, p.minimum, p.have or 0, 'yes' if p.active else 'no') for p in definitions]),
            ('Records', ['Item number', 'Asset tag', 'Location', 'Quantity', 'Order', 'Since'],
             [(r.definition.number, r.tag or '', r.location.path if r.location else '', r.quantity,
               r.order_line.order.number if r.order_line else '', r.created_at.date())
              for r in Record.objects.filter(definition__in=definitions, quantity__gt=0).select_related('definition', 'location', 'order_line__order')
              .select_related('definition', 'location')]),
            ('Attributes', ['Item number', 'Category', 'Attribute', 'Value', 'Unit'],
             [(v.definition.number, v.definition.category.path if v.definition.category else '', v.attribute.name,
               v.number if v.number is not None else v.value, v.attribute.unit)
              for v in DefinitionValue.objects.filter(definition__in=definitions).select_related('definition__category', 'attribute')]
             + [(link.definition.number, link.definition.category.path if link.definition.category else '', link.attribute.name, link.target.number, '')
                for link in DefinitionLink.objects.filter(definition__in=definitions).select_related('definition__category', 'attribute', 'target')])]


@login_required
def definition_form(request, pk=None):
    definition = get_object_or_404(ItemDefinition, pk=pk) if pk else None
    form = DefinitionForm(request.POST or None, instance=definition, initial=initial_for(definition, category=request.GET.get('category')))
    if request.method == 'POST' and not request.POST.get('refresh') and form.is_valid():   # refresh: its category changed
        definition = form.save()
        messages.success(request, f'{definition} is saved.')
        return redirect(definition)
    numbers = ItemDefinition.objects.filter(active=True).values_list('number', 'description')[:5000] \
        if any(a.kind == Attribute.Kind.LINK for a in form.attributes) else []
    return render(request, 'inventory/attributes_form.html', {'form': form, 'title': f'Change {definition}' if definition else 'New item definition',
                                                              'back': definition.get_absolute_url() if definition else None, 'definition_numbers': numbers})


@login_required
def definition(request, pk):
    definition = get_object_or_404(ItemDefinition.objects.select_related('category', 'vendor', 'family', 'branch'), pk=pk)
    return render(request, 'inventory/definition.html', {
        'attributes': attributes_kept.shown(definition, definition.category), 'linked_here': attributes_kept.linked_here(definition),
        'definition': definition, 'records': definition.records.filter(quantity__gt=0).select_related('location', 'order_line__order', 'holder'),
        'on_hand': definition.on_hand, 'on_order': orders.on_order(definition),
        'lines': definition.order_lines.select_related('order__vendor').order_by('-order__pk')[:20],
        'movements': definition.movements.select_related('source', 'target', 'user')[:50],
        'locations': Location.ordered()})


@login_required
@require_POST
def definition_stock(request, pk):
    """Add, move, use or count stock of an item definition, from its page."""
    definition = get_object_or_404(ItemDefinition, pk=pk)
    post = request.POST
    where = Location.objects.filter(pk=post.get('location') or 0).first()
    to = Location.objects.filter(pk=post.get('to') or 0).first()
    action, note = post.get('action'), post.get('note', '')
    try:
        if where is None or (action == 'move' and to is None):
            raise ValidationError('Pick the location.')
        if action == 'add':
            stock.add(definition, post.get('quantity'), where, request.user, note)
        elif action == 'move':
            stock.move(definition, post.get('quantity'), where, to, request.user, note)
        elif action == 'use':
            stock.use(definition, post.get('quantity'), where, request.user, note)
        elif action == 'count':
            stock.count(definition, where, post.get('quantity'), request.user, note)
        else:
            raise ValidationError('What should happen to the stock?')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(definition)


@login_required
@require_POST
def definition_reorder(request, pk):
    definition = get_object_or_404(ItemDefinition, pk=pk)
    try:
        line = orders.reorder(definition, request.user)
    except ValidationError as exc:
        errors(request, exc)
        return redirect(definition)
    messages.success(request, f'{line.quantity.normalize():f} × {definition} is on {line.order} ({line.order.vendor}).')
    return redirect(line.order)


@login_required
def locations(request):
    """The locations: their tree on the left (each with its picture), the locations inside the one picked in the
    middle, and on the right the one picked: its picture, notes, files and documentation. (What is kept where is the
    item definitions' and the assets' to say, not the locations'.)"""
    from web import briefs, browse
    place = Location.objects.filter(pk=request.GET.get('location') or 0).first()
    tree = Location.ordered()
    inside = {}
    for node, _ in tree:
        inside[node.parent_id] = inside.get(node.parent_id, 0) + 1
    nodes = [browse.node('All locations', '?', len(tree), place is None)] + browse.nodes(
        tree, {}, place, lambda l: f'?location={l.pk}', label=lambda l: l.name, thumbs=True)
    for n, (node, _) in zip(nodes[1:], tree):
        n['count'] = inside.get(node.pk) or None
    shown = [(l, d) for l, d in tree if place is None or (l.pk in set(place.below()) and l.pk != place.pk)]
    base = min((d for _, d in shown), default=0)
    return render(request, 'inventory/locations.html', {
        'nodes': nodes, 'place': place, 'locations': [(l, d - base, inside.get(l.pk, 0)) for l, d in shown],
        'brief': briefs.of('location', place) if place else None})


@login_required
def location(request, pk):
    """A location's page: where it is, the locations inside it, its picture, notes, files and documentation."""
    from web import briefs
    place = get_object_or_404(Location, pk=pk)
    return render(request, 'inventory/location.html', {'location': place, 'children': place.children.all(),
                                                       'brief': briefs.of('location', place)})


@login_required
def location_form(request, pk=None):
    place = get_object_or_404(Location, pk=pk) if pk else None
    return edit_page(request, LocationForm(request.POST or None, instance=place, initial=initial_for(place, parent=request.GET.get('parent'))),
                     'location')


@login_required
def vendors(request):
    """The vendors: those dealt with and those no longer on the left, the vendors in the middle, the details of the
    one picked on the right."""
    from web import briefs, browse
    shown = request.GET.get('show', '')
    q = request.GET.get('q', '').strip()
    found = Vendor.objects.all()
    if shown in ('active', 'inactive'):
        found = found.filter(active=shown == 'active')
    if q:
        found = found.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q))
    kept = browse.keep(request, 'q')
    nodes = [browse.node('All vendors', f'?{kept[1:]}', Vendor.objects.count(), not shown),
             browse.node('Active', f'?show=active{kept}', Vendor.objects.filter(active=True).count(), shown == 'active'),
             browse.node('Inactive', f'?show=inactive{kept}', Vendor.objects.filter(active=False).count(), shown == 'inactive')]
    picked = Vendor.objects.filter(pk=request.GET.get('vendor') or 0).first()
    return render(request, 'inventory/vendors.html', {'vendors': found, 'nodes': nodes, 'q': q, 'shown': shown, 'picked': picked,
                                                      'brief': briefs.of('vendor', picked) if picked else None})


@login_required
def vendor(request, pk):
    item = get_object_or_404(Vendor, pk=pk)
    return render(request, 'inventory/vendor.html', {'vendor': item, 'definitions': item.definitions.filter(active=True),
                                                     'orders': item.orders.all()[:30]})


@login_required
def vendor_form(request, pk=None):
    item = get_object_or_404(Vendor, pk=pk) if pk else None
    return edit_page(request, VendorForm(request.POST or None, instance=item), 'vendor')


@login_required
def families(request):
    """The connector families, like the item definitions: their branches as a tree on the left (D-sub, Circular / M12, …), the
    families of the one picked in the middle, the details of the family picked on the right. A family or a branch is
    made or changed on a form of its own (?new=family, ?new=branch, ?edit=<family>, ?branch=<branch>)."""
    from .faces import natural
    item = Family.objects.filter(pk=request.GET.get('edit') or 0).first()
    branch = FamilyBranch.objects.filter(pk=request.GET.get('branch') or 0).first()
    making = request.POST.get('form') or ('family' if item or request.GET.get('new') == 'family' else
                                          'branch' if branch or request.GET.get('new') == 'branch' else '')
    group = FamilyBranch.objects.filter(pk=request.GET.get('group') or 0).first()
    if making:
        start = {'group': group.pk} if group and not item else {}
        under = {'parent': group.pk} if group and not branch else {}
        form = FamilyForm(request.POST if making == 'family' and request.method == 'POST' else None, instance=item, prefix='family', initial=start)
        branch_form = FamilyBranchForm(request.POST if making == 'branch' and request.method == 'POST' else None, instance=branch,
                                       prefix='branch', initial=under)
        sent = branch_form if making == 'branch' else form
        if sent.is_bound and sent.is_valid():
            saved = sent.save()
            messages.success(request, f'{saved} is saved.')
            where = saved.group_id if making == 'family' else saved.pk
            return redirect(reverse('inventory:families') + (f'?group={where}' if where else '')
                            + (f'{"&" if where else "?"}family={saved.pk}' if making == 'family' else ''))
        title = (f'Change {item.name}' if item else 'New connector family') if making == 'family' else \
                (f'Change {branch.name}' if branch else 'New branch')
        return render(request, 'inventory/family_form.html', {'form': sent, 'kind': making, 'title': title,
                                                              'back': reverse('inventory:families') + (f'?group={group.pk}' if group else '')})
    q = request.GET.get('q', '').strip()
    every = sorted(Family.objects.annotate(n=Count('definitions')).select_related('group').prefetch_related('branches'), key=lambda f: natural(f.name))
    found = [f for f in every if (not q or q.lower() in f.name.lower()) and (group is None or f.group_id in group.below())]
    tree = FamilyBranch.ordered()
    own, children = {}, {}
    for f in every:
        own[f.group_id] = own.get(f.group_id, 0) + 1
    for b, _ in tree:
        children.setdefault(b.parent_id, []).append(b.pk)

    def counted(pk):   # its families and those of the branches under it
        return own.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    keep = f'&q={q}' if q else ''
    open_ = set(group.chain_pks()) if group else set()
    nodes = [{'label': 'All families', 'url': f'?{keep[1:]}', 'count': len(every), 'on': group is None}] + [
        {'label': b.name, 'url': f'?group={b.pk}{keep}', 'depth': depth, 'count': counted(b.pk), 'on': group == b, 'open': b.pk in open_}
        for b, depth in tree]
    picked = Family.objects.filter(pk=request.GET.get('family') or 0).first()
    return render(request, 'inventory/families.html', {'families': found, 'nodes': nodes, 'group': group, 'q': q, 'picked': picked,
                                                       'brief': _family_brief(picked) if picked else None})


def _family_brief(family):
    """What the details beside the list of connector families show of ``family``."""
    face = family.face if (family.face or {}).get('contacts') else None
    return {'family': family, 'face': {'face': face, 'pins': [[c[0], ''] for c in face['contacts']]} if face else None,
            'branches': family.branches.annotate(n=Count('definitions')),
            'definitions': family.definitions.select_related('branch').annotate(have=Sum('records__quantity'))[:30]}


@login_required
def family_brief(request, pk):
    """The details of a connector family beside their list (fetched when one is picked)."""
    return render(request, 'inventory/_family_brief.html', _family_brief(get_object_or_404(Family.objects.select_related('group'), pk=pk)))


@login_required
@require_POST
def standard_categories(request):
    """The categories of single items a lab keeps (electronic components, connectors, fasteners, wire, …), those not
    there yet, with their attributes: ``inventory.category_presets``."""
    from .category_presets import standard_categories as make
    categories, attributes = make()
    messages.success(request, f'{categories} standard categor{"y" if categories == 1 else "ies"} and {attributes} attribute{"" if attributes == 1 else "s"} added.'
                     if categories or attributes else 'The standard categories are all there.')
    return redirect('inventory:categories')


@login_required
@require_POST
def standard_families(request):
    """The connectors made often (D-sub, D-sub HD, Gecko) as families, those not there yet."""
    from .faces import standard_families as make
    made = make()
    messages.success(request, f'{made} standard connector famil{"y" if made == 1 else "ies"} added.' if made else
                     'The standard connector families are all there.')
    return redirect('inventory:families')


@login_required
def family(request, pk):
    """A family: its branches (added, or renamed: ?branch=<pk>), its item definitions, their stock together, the one it is
    ordered as."""
    item = get_object_or_404(Family, pk=pk)
    branch = item.branches.filter(pk=request.GET.get('branch') or 0).first()
    form = BranchForm(request.POST or None, instance=branch, family=item)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved} is saved.')
        return redirect(item)
    from .faces import mirrored
    face = item.face if (item.face or {}).get('contacts') else None
    return render(request, 'inventory/family.html', {
        'faces': {side: {'face': f, 'pins': [[c[0], ''] for c in f['contacts']]} for side, f in (('pin', face), ('socket', mirrored(face)))}
                 if face else None,
        'family': item, 'form': form, 'branch': branch, 'branches': item.branches.annotate(n=Count('definitions')),
        'definitions': item.definitions.select_related('vendor', 'branch').annotate(have=Sum('records__quantity'))})


def _with_branches(family):
    """A connector family has a pin branch and a socket branch (made when missing; a branch named so is marked so)."""
    for contacts, name in (('pin', 'pin'), ('socket', 'socket')):
        if family.branches.filter(contacts=contacts).exists():
            continue
        named = family.branches.filter(name__iexact=name).first()
        if named:
            named.contacts = contacts
            named.save(update_fields=['contacts'])
        else:
            Branch.objects.create(family=family, name=name, contacts=contacts)


def _face_sent(text):
    """The face sent by the connector editor, checked and fitted; ValidationError when it isn't right."""
    from .faces import SHAPES, fitted
    try:
        data = json.loads(text or '')
        shape = data['shape'] if data['shape'] in dict(SHAPES) else 'rect'
        contacts = [[str(n).strip(), float(x), float(y)] for n, x, y in data['contacts']]
        outline = [[float(x), float(y)] for x, y in data.get('outline') or []] if shape == 'custom' else None
    except (ValueError, TypeError, KeyError):
        raise ValidationError('The connector could not be read.')
    if shape == 'custom' and len(outline) < 3:
        raise ValidationError('An outline of its own needs at least 3 corners.')
    numbers = [c[0] for c in contacts]
    if '' in numbers:
        raise ValidationError('Every contact needs a number.')
    twice = sorted({n for n in numbers if numbers.count(n) > 1})
    if twice:
        raise ValidationError(f'Contact {", ".join(twice)} is there twice.')
    return fitted(shape, contacts, outline)


@login_required
def connector(request, pk):
    """The connector editor of a family: its outline and its contacts (where each sits, its number), as seen from the
    pin side; made from a ready-made one, or changed by hand. Its pin and socket branches are made with it."""
    from .faces import SHAPES, STARTS, preset, preset_choices, start
    item = get_object_or_404(Family, pk=pk)
    if request.method == 'POST':
        try:
            if request.POST.get('action') == 'start':
                face = preset(request.POST.get('kind')) or start(request.POST.get('kind'), min(int(request.POST.get('positions') or 1), 200),
                                                                 int(request.POST.get('columns') or 0) or None)
            else:
                face = _face_sent(request.POST.get('face'))
        except ValueError:
            messages.error(request, 'Positions and columns are numbers.')
            return redirect('inventory:connector', pk=item.pk)
        except ValidationError as exc:
            errors(request, exc)
            return redirect('inventory:connector', pk=item.pk)
        if request.POST.get('action') != 'start' and (item.face or {}).get('genders') is False:
            face['genders'] = False   # a ring terminal changed by hand: still without sides
        with transaction.atomic():
            item.face = face
            item.save(update_fields=['face'])
            if face.get('genders', True):
                _with_branches(item)
        messages.success(request, f'The {item} connector is saved.')
        return redirect('inventory:connector' if request.POST.get('action') == 'start' else 'inventory:family', pk=item.pk)
    return render(request, 'inventory/connector.html', {'family': item, 'face': item.face or {'shape': 'rect', 'contacts': []},
                                                        'shapes': SHAPES, 'starts': STARTS, 'presets': preset_choices()})


@login_required
def categories(request):
    """The categories of item definitions: their tree on the left (?category= the one picked), the categories in it in
    the middle, the details of the one picked on the right; a form to add one (or change one: ?edit=<pk>)."""
    from web import briefs, browse
    item = Category.objects.filter(pk=request.GET.get('edit') or 0).first()
    form = CategoryForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved} is saved.')
        return redirect(f"{reverse('inventory:categories')}?category={saved.pk}")
    counts = dict(ItemDefinition.objects.filter(active=True).values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    own = dict(Attribute.objects.values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    tree = Category.ordered()
    picked = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    shown = [(c, d) for c, d in tree if picked is None or c.pk in set(picked.below())]
    nodes = [browse.node('All categories', '?', None, picked is None)]
    nodes += browse.nodes(tree, counts, picked, lambda c: f'?category={c.pk}', label=lambda c: c.name, depth=1)
    top = picked.chain()[-1].pk if picked else None
    base = min((d for c, d in shown), default=0)
    return render(request, 'inventory/categories.html', {
        'categories': [(c, depth - base, counts.get(c.pk, 0), own.get(c.pk, 0)) for c, depth in shown], 'form': form, 'item': item,
        'nodes': nodes, 'picked': picked, 'top': top, 'brief': briefs.of('category', picked) if picked else None})


def _category_page(request, item, form):
    """A category's page: the attributes its item definitions fill in (those it gets from above, and its own), the
    categories under it, how many item definitions are in it, and a form to add an attribute."""
    every = item.all_attributes()
    below = item.below()
    return render(request, 'inventory/category.html', {
        'category': item, 'inherited': [a for a in every if a.category_id != item.pk], 'own': [a for a in every if a.category_id == item.pk],
        'form': form, 'children': item.children.all(), 'definitions': ItemDefinition.objects.filter(category_id__in=below, active=True).count()})


@login_required
def category(request, pk):
    item = get_object_or_404(Category, pk=pk)
    return _category_page(request, item, AttributeForm(category=item))


@login_required
def attribute_form(request, pk, attribute=None):
    item = get_object_or_404(Category, pk=pk)
    current = get_object_or_404(Attribute, pk=attribute, category=item) if attribute else None
    form = AttributeForm(request.POST or None, instance=current, category=item)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved.name} is saved.')
        return redirect(f'{item.get_absolute_url()}#attributes')
    if current is None:   # adding happens on the category's page
        return _category_page(request, item, form)
    return render(request, 'web/form.html', {'form': form, 'title': f'{current.name} of {item.name}', 'back': item.get_absolute_url()})


@login_required
@require_POST
def attribute_delete(request, pk, attribute):
    item = get_object_or_404(Category, pk=pk)
    found = get_object_or_404(Attribute, pk=attribute, category=item)
    found.delete()
    messages.success(request, f'{found.name} is taken away, with what was filled in for it.')
    return redirect(f'{item.get_absolute_url()}#attributes')


@login_required
@require_POST
def attribute_move(request, pk, attribute):
    """Move an attribute up or down among its category's."""
    item = get_object_or_404(Category, pk=pk)
    order = list(item.attributes.all())
    found = get_object_or_404(Attribute, pk=attribute, category=item)
    i = order.index(found)
    j = i - 1 if request.POST.get('to') == 'up' else i + 1
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
        for position, a in enumerate(order):
            Attribute.objects.filter(pk=a.pk).update(position=position)
    return redirect(f'{item.get_absolute_url()}#attributes')
