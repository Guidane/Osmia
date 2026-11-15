"""Where what item definitions and assets fill in for their attributes is kept: values (DefinitionValue, AssetValue) and links to item definitions or
assets (DefinitionLink and DefinitionAsset for item definitions, AssetLink for assets). ``store_for`` gives the one for an item definition or an asset;
forms, pages and lists use it the same way for both."""
from .models import Attribute, ItemDefinition, DefinitionLink, DefinitionValue


class Store:
    value_model = None        # (subject, attribute, value, number)
    subject = ''              # the field naming the item definition or asset on the value and link models

    def values(self, obj):
        """{attribute id: value} of what ``obj`` filled in (not links)."""
        return {v.attribute_id: v.value for v in self.value_model.objects.filter(**{self.subject: obj})}

    def save(self, obj, attributes, values, links):
        """Keep ``values`` ({attribute id: (text, number)}) and ``links`` ({attribute id: [item definition or asset]}) for ``obj``;
        drop what it had for attributes it no longer has; give it the next auto number of those it has none of yet."""
        kept = [a.pk for a in attributes]
        self.value_model.objects.filter(**{self.subject: obj}).exclude(attribute__in=kept).delete()
        self.drop_links(obj, kept)
        for a in attributes:
            if a.is_link:
                self.set_links(obj, a, links.get(a.pk, []))
                continue
            if a.kind == Attribute.Kind.AUTO:
                number_up(a, [obj])
                continue
            text, number = values.get(a.pk, ('', None))
            if text:
                self.value_model.objects.update_or_create(**{self.subject: obj}, attribute=a, defaults={'value': text, 'number': number})
            else:
                self.value_model.objects.filter(**{self.subject: obj}, attribute=a).delete()

    def matching(self, attribute, **lookup):
        """The pks of the item definitions or assets whose value for ``attribute`` matches ``lookup`` (e.g. value__iexact=...)."""
        return self.value_model.objects.filter(attribute=attribute, **lookup).values(self.subject)


class DefinitionStore(Store):
    value_model, subject = DefinitionValue, 'definition'

    def linked(self, attribute, definition):
        if attribute.to_assets:
            from assets.models import Asset
            return list(Asset.objects.filter(definition_links__definition=definition, definition_links__attribute=attribute))
        return list(ItemDefinition.objects.filter(linked_from__definition=definition, linked_from__attribute=attribute))

    def set_links(self, definition, attribute, wanted):
        from assets.models import DefinitionAsset
        model, field = (DefinitionAsset, 'asset') if attribute.to_assets else (DefinitionLink, 'target')
        model.objects.filter(definition=definition, attribute=attribute).exclude(**{f'{field}__in': wanted}).delete()
        for x in wanted:
            model.objects.get_or_create(definition=definition, attribute=attribute, **{field: x})

    def drop_links(self, definition, kept):
        from assets.models import DefinitionAsset
        DefinitionLink.objects.filter(definition=definition).exclude(attribute__in=kept).delete()
        DefinitionAsset.objects.filter(definition=definition).exclude(attribute__in=kept).delete()

    def link_texts(self, definitions):
        """{item definition id: {attribute id: "A-1, B-2"}} of what the item definitions link to, for lists."""
        from assets.models import DefinitionAsset
        out = {}
        for link in DefinitionLink.objects.filter(definition__in=definitions).select_related('target'):
            out.setdefault(link.definition_id, {}).setdefault(link.attribute_id, []).append(link.target.number)
        for link in DefinitionAsset.objects.filter(definition__in=definitions).select_related('asset'):
            out.setdefault(link.definition_id, {}).setdefault(link.attribute_id, []).append(link.asset.number)
        return {p: {a: ', '.join(n) for a, n in d.items()} for p, d in out.items()}


class AssetStore(Store):
    subject = 'asset'

    @property
    def value_model(self):
        from assets.models import AssetValue
        return AssetValue

    def linked(self, attribute, asset):
        from assets.models import Asset
        if attribute.to_assets:
            return list(Asset.objects.filter(linked_from__asset=asset, linked_from__attribute=attribute))
        return list(ItemDefinition.objects.filter(linked_from_assets__asset=asset, linked_from_assets__attribute=attribute))

    def set_links(self, asset, attribute, wanted):
        from assets.models import AssetLink
        field = 'target' if attribute.to_assets else 'definition'
        AssetLink.objects.filter(asset=asset, attribute=attribute).exclude(**{f'{field}__in': wanted}).delete()
        for x in wanted:
            AssetLink.objects.get_or_create(asset=asset, attribute=attribute, **{field: x})

    def drop_links(self, asset, kept):
        from assets.models import AssetLink
        AssetLink.objects.filter(asset=asset).exclude(attribute__in=kept).delete()

    def link_texts(self, assets):
        from assets.models import AssetLink
        out = {}
        for link in AssetLink.objects.filter(asset__in=assets).select_related('definition', 'target'):
            out.setdefault(link.asset_id, {}).setdefault(link.attribute_id, []).append((link.definition or link.target).number)
        return {t: {a: ', '.join(n) for a, n in d.items()} for t, d in out.items()}


def number_up(attribute, objs):
    """Give each of ``objs`` (item definitions or assets) without one the next auto number of ``attribute``, in turn."""
    from django.db import transaction
    with transaction.atomic():
        Attribute.objects.select_for_update().filter(pk=attribute.pk).first()   # one numbering at a time
        number = attribute.next_number()
        for obj in objs:
            store = store_for(obj)
            if not store.value_model.objects.filter(**{store.subject: obj}, attribute=attribute).exists():
                store.value_model.objects.create(**{store.subject: obj}, attribute=attribute, value=attribute.auto_value(number), number=number)
                number += 1


def store_for(obj):
    return DefinitionStore() if isinstance(obj, ItemDefinition) else AssetStore()


def linked_here(obj):
    """What other item definitions and assets say of ``obj`` (an item definition or an asset): {"Mates with pins": [item definitions and assets]}."""
    from assets.models import AssetLink, DefinitionAsset
    found = {}
    if isinstance(obj, ItemDefinition):
        links = list(DefinitionLink.objects.filter(target=obj).select_related('definition', 'attribute__category'))
        links += list(AssetLink.objects.filter(definition=obj).select_related('asset', 'attribute__category'))
    else:
        links = list(DefinitionAsset.objects.filter(asset=obj).select_related('definition', 'attribute__category'))
        links += list(AssetLink.objects.filter(target=obj).select_related('asset', 'attribute__category'))
    for link in links:
        source = link.definition if isinstance(link, (DefinitionLink, DefinitionAsset)) else link.asset
        found.setdefault(link.attribute.other_side(), []).append(source)
    return sorted(found.items())


def filtered(found, attributes, query, store):
    """``found`` (item definitions or assets) narrowed to those whose attributes match what a list is filtered by: a<id> (text:
    contains; a choice or yes/no: is), a<id>_min and a<id>_max (numbers)."""
    from decimal import Decimal, InvalidOperation
    for a in (a for a in attributes if not a.is_link):
        wanted = query.get(f'a{a.pk}', '').strip()
        if wanted and a.kind not in Attribute.NUMERIC:
            exact = a.kind in (Attribute.Kind.CHOICE, Attribute.Kind.YESNO)
            found = found.filter(pk__in=store.matching(a, **({'value__iexact': wanted} if exact else {'value__icontains': wanted})))
        for end, lookup in (('min', 'number__gte'), ('max', 'number__lte')):
            text = query.get(f'a{a.pk}_{end}', '').strip().replace(',', '.')
            if text and a.kind in Attribute.NUMERIC:
                try:
                    found = found.filter(pk__in=store.matching(a, **{lookup: Decimal(text)}))
                except InvalidOperation:
                    pass
    return found


def columns(objs, attributes, store):
    """[(obj, [shown value of each attribute])] for a list."""
    links = store.link_texts(objs)
    rows = []
    values = {}
    for v in store.value_model.objects.filter(**{f'{store.subject}__in': objs}):
        values.setdefault(getattr(v, f'{store.subject}_id'), {})[v.attribute_id] = v.value
    for obj in objs:
        mine = {**values.get(obj.pk, {}), **links.get(obj.pk, {})}
        rows.append((obj, [a.show(mine.get(a.pk, '')) for a in attributes]))
    return rows


def filters(attributes, query):
    return [(a, query.get(f'a{a.pk}', ''), query.get(f'a{a.pk}_min', ''), query.get(f'a{a.pk}_max', ''))
            for a in attributes if not a.is_link]



def of(obj, node):
    """The attributes ``obj`` (an item definition or an asset) fills in: an asset's fields first, then its category's (``node``)."""
    return ([] if isinstance(obj, ItemDefinition) else Attribute.asset_fields()) + (node.all_attributes() if node else [])


def shown(obj, node):
    """[(attribute, value)] of an item definition or asset for its page: a link attribute's value is what it links to."""
    store = store_for(obj)
    values = store.values(obj)
    return [(a, store.linked(a, obj) if a.is_link else a.show(values.get(a.pk, ''))) for a in of(obj, node)]
