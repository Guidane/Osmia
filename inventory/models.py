"""Item definitions and where they are: vendors, item definition categories (a tree, each with attributes its item definitions fill in, trickling
down to the categories under it), item definitions with their attribute values, families of item definitions that can take each other's
place (the same plug from other manufacturers), locations (a tree:
building → room → shelf → bin), how many of an item definition are in each location, and every movement of stock.

Stock only changes through ``inventory.stock``, which keeps a Movement for each change.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Lower
from django.urls import reverse

from web.models import Tree




class Vendor(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    account_number = models.CharField('our account number', max_length=100, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('inventory:vendor', args=[self.pk])


class Category(Tree):
    """A kind of item definition, or of asset: each has its own tree. Its attributes, and those of the categories above it, are
    what its item definitions (or assets) fill in."""
    class Kind(models.TextChoices):
        DEFINITIONS = 'definitions', 'Item definitions'
        ASSETS = 'assets', 'Assets'

    kind = models.CharField(max_length=12, choices=Kind, default=Kind.DEFINITIONS)

    class Meta(Tree.Meta):
        verbose_name_plural = 'categories'
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_category_name')]

    def get_absolute_url(self):
        return reverse('inventory:category', args=[self.pk])

    @classmethod
    def of(cls, kind):
        """The categories of item definitions (or assets), depth first, as (category, depth)."""
        return cls.ordered(cls.objects.filter(kind=kind))

    def all_attributes(self):
        """Its attributes and those it gets from above: the top category's first."""
        chain = self.chain()
        depth = {c.pk: i for i, c in enumerate(chain)}
        return sorted(Attribute.objects.filter(category__in=chain).select_related('category'),
                      key=lambda a: (depth[a.category_id], a.position, a.pk))


class Attribute(models.Model):
    """Something the item definitions and assets of a category, and those of every category under it, fill in, e.g. Resistance in Ω.
    One of no category is an asset field: every asset fills it in (what a company keeps of its assets: a cost centre,
    an inventory number, a purchase date)."""
    class Kind(models.TextChoices):
        TEXT = 'text', 'Text'
        INTEGER = 'integer', 'Whole number'
        DECIMAL = 'decimal', 'Number (with decimals)'
        CHOICE = 'choice', 'Choice from a list'
        YESNO = 'yesno', 'Yes / no'
        AUTO = 'auto', 'Auto number (an ID)'
        INTERACTS = 'interacts', 'Interacts with item definitions of a category'
        LINK = 'link', 'Link to an item definition or an asset'

    class LinksTo(models.TextChoices):
        DEFINITION = 'definition', 'An item definition (of any category)'
        ASSET = 'asset', 'An asset (a tool, lab equipment…)'

    NUMERIC = (Kind.INTEGER, Kind.DECIMAL)
    LINKS = (Kind.INTERACTS, Kind.LINK)   # what item definitions fill in are other item definitions (or assets), not a value

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)
    kind = models.CharField('type', max_length=10, choices=Kind, default=Kind.TEXT)
    unit = models.CharField(max_length=20, blank=True)
    choices = models.TextField(blank=True)
    prefix = models.CharField(max_length=20, blank=True)
    digits = models.PositiveSmallIntegerField(default=5)
    required = models.BooleanField(default=False)
    help = models.CharField(max_length=200, blank=True)
    target = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE, related_name='interactions',
                               verbose_name='interacts with')
    links_to = models.CharField(max_length=10, choices=LinksTo, blank=True)
    reverse_name = models.CharField('name on the other side', max_length=100, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']

    def __str__(self):
        return self.name

    @property
    def is_link(self):
        return self.kind in self.LINKS

    @property
    def to_assets(self):
        return self.kind == self.Kind.LINK and self.links_to == self.LinksTo.ASSET

    def other_side(self):
        """What the item definitions or assets linked to call this attribute."""
        return self.reverse_name or f'{self.name} (of {self.category.name if self.category else "assets"})'

    @classmethod
    def asset_fields(cls):
        """The asset fields: what every asset fills in, whatever its category."""
        return list(cls.objects.filter(category=None))

    def candidates(self):
        """What may be linked to with this attribute: the target category's item definitions (and below), every item definition, or assets."""
        if self.kind == self.Kind.INTERACTS:
            return ItemDefinition.objects.filter(category_id__in=self.target.below(), active=True) if self.target else ItemDefinition.objects.none()
        if self.to_assets:
            from assets.models import Asset
            return Asset.objects.exclude(status='retired')
        return ItemDefinition.objects.filter(active=True)

    def choice_list(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]

    def clean_value(self, raw):
        """(text, number) to keep for ``raw``, ('', None) when empty; refused when it doesn't fit."""
        from decimal import Decimal, InvalidOperation

        from django.core.exceptions import ValidationError
        text = str(raw if raw is not None else '').strip()
        if not text:
            return '', None
        if self.kind in self.NUMERIC:
            try:
                number = Decimal(text.replace(',', '.'))
            except InvalidOperation:
                raise ValidationError(f'{self.name}: "{text}" is not a number.')
            if not number.is_finite():
                raise ValidationError(f'{self.name}: "{text}" is not a number.')
            if self.kind == self.Kind.INTEGER and number != number.to_integral_value():
                raise ValidationError(f'{self.name}: "{text}" is not a whole number.')
            number = number.to_integral_value() if self.kind == self.Kind.INTEGER else number.normalize()
            return f'{number:f}', number
        if self.kind == self.Kind.CHOICE:
            match = next((c for c in self.choice_list() if c.lower() == text.lower()), None)
            if match is None:
                raise ValidationError(f'{self.name}: "{text}" is not one of its choices.')
            return match, None
        if self.kind == self.Kind.YESNO:
            if text.lower() not in ('yes', 'no'):
                raise ValidationError(f'{self.name}: yes or no.')
            return text.capitalize(), None
        return text[:200], None

    def auto_value(self, number):
        """An auto number as shown and kept: ID-00042."""
        return f'{self.prefix}{number:0{self.digits}d}'

    def next_number(self):
        """The next auto number of this attribute: one more than the highest given to an item definition or an asset."""
        from django.db.models import Max
        from assets.models import AssetValue
        highest = max(self.values.aggregate(n=Max('number'))['n'] or 0, AssetValue.objects.filter(attribute=self).aggregate(n=Max('number'))['n'] or 0)
        return int(highest) + 1

    def show(self, value):
        """A value as shown: with its unit."""
        return f'{value} {self.unit}' if value and self.unit and self.kind in self.NUMERIC else value


class Location(Tree):
    description = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta(Tree.Meta):
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_location_name')]

    def get_absolute_url(self):
        return reverse('inventory:location', args=[self.pk])


class ItemDefinition(models.Model):
    """What something bought from another company is: a physical thing (a connector, a nut, a crimp tool) or not one (a
    service, a subscription, a licence, a statement of work). Only physical ones are kept in stock."""
    class Kind(models.TextChoices):
        PHYSICAL = 'physical', 'Physical'
        SERVICE = 'service', 'Service'
        SUBSCRIPTION = 'subscription', 'Subscription'
        LICENCE = 'licence', 'Licence'
        WORK = 'work', 'Statement of work'

    class Unit(models.TextChoices):
        PCS = 'pcs', 'pieces'
        M = 'm', 'metres'
        KG = 'kg', 'kilograms'
        L = 'l', 'litres'
        SET = 'set', 'sets'
        ROLL = 'roll', 'rolls'
        HOUR = 'h', 'hours'
        MONTH = 'month', 'months'
        YEAR = 'year', 'years'

    kind = models.CharField(max_length=12, choices=Kind, default=Kind.PHYSICAL)
    number = models.CharField('item number', max_length=100)
    description = models.CharField(max_length=300, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='definitions')
    manufacturer = models.CharField(max_length=200, blank=True)
    mpn = models.CharField('manufacturer part number', max_length=200, blank=True)
    unit = models.CharField(max_length=10, choices=Unit, default=Unit.PCS)
    datasheet = models.URLField(blank=True)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name='definitions')
    vendor_number = models.CharField("vendor's part number", max_length=200, blank=True)
    family = models.ForeignKey('Family', null=True, blank=True, on_delete=models.SET_NULL, related_name='definitions')
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='definitions')
    price = models.DecimalField('last price', max_digits=12, decimal_places=4, null=True, blank=True)
    minimum = models.DecimalField('minimum stock', max_digits=12, decimal_places=3, default=0)
    reorder_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        verbose_name = 'item definition'
        constraints = [models.UniqueConstraint(Lower('number'), name='unique_definition_number',
                                               violation_error_message='There is already an item definition with this number.')]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('inventory:definition', args=[self.pk])

    @property
    def physical(self):
        return self.kind == self.Kind.PHYSICAL

    @property
    def on_hand(self):
        return self.stock.aggregate(n=Sum('quantity'))['n'] or Decimal(0)


class DefinitionGroup:
    """Item definitions that can take each other's place (a family, or a branch of one). Where a harness or device names the
    group, any of them will do: their stock counts together, the most stocked is used first, and the one last ordered
    is ordered again. It shows where an item definition would, so it answers to what an item definition does (number, unit, vendor)."""
    def members(self):
        raise NotImplementedError

    @property
    def chosen(self):
        """The item definition ordered for it: the one last ordered, else the first with a vendor, else the first."""
        return self.members().order_by(models.F('order_lines__pk').desc(nulls_last=True), models.F('vendor').asc(nulls_last=True),
                                       'number').first()

    @property
    def unit(self):
        return self.chosen.unit if self.chosen else ItemDefinition.Unit.PCS

    @property
    def vendor_id(self):
        return self.chosen.vendor_id if self.chosen else None

    @property
    def on_hand(self):
        return Stock.objects.filter(definition__in=self.members()).aggregate(n=Sum('quantity'))['n'] or Decimal(0)


PartGroup = DefinitionGroup   # what the migrations made before item definitions call it


class FamilyBranch(Tree):
    """Where families sit, as a tree: "D-sub" holds D-sub 9 and D-sub 25, "Circular / M12" the M12 ones."""
    class Meta(Tree.Meta):
        verbose_name_plural = 'family branches'
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_family_branch_name')]


class Family(DefinitionGroup, models.Model):
    """Item definitions that can take each other's place, by a name (D-sub 9), maybe split into branches (pin, socket, …). A
    connector family has its face (``inventory.faces``): its outline and where its contacts sit, as seen from the pin
    side."""
    name = models.CharField(max_length=100)
    group = models.ForeignKey(FamilyBranch, null=True, blank=True, on_delete=models.SET_NULL, related_name='families',
                              verbose_name='branch')
    face = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'families'
        constraints = [models.UniqueConstraint(Lower('name'), name='unique_family_name',
                                               violation_error_message='There is already a family with this name.')]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('inventory:family', args=[self.pk])

    @property
    def number(self):
        return self.name

    def members(self):
        return ItemDefinition.objects.filter(family=self)


class Branch(DefinitionGroup, models.Model):
    """A part of a family (its male ones, its female ones): "D-sub 9 / female"."""
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100)
    contacts = models.CharField(max_length=6, blank=True, choices=[('pin', 'Pins'), ('socket', 'Sockets')])   # sockets: the face mirrored

    class Meta:
        ordering = ['family__name', 'name']
        verbose_name_plural = 'branches'
        constraints = [models.UniqueConstraint('family', Lower('name'), name='unique_branch_name',
                                               violation_error_message='The family has a branch of this name already.')]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return self.family.get_absolute_url()

    @property
    def number(self):
        return f'{self.family.name} / {self.name}'

    def members(self):
        return ItemDefinition.objects.filter(branch=self)


class DefinitionOrFamily(models.Model):
    """What names an item definition (a harness end, a wire, a device connector): one item definition, or any of a family, or of a branch."""
    family = models.ForeignKey(Family, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        abstract = True

    @property
    def used(self):
        return self.definition or self.branch or self.family

    @used.setter
    def used(self, found):
        self.definition, self.branch, self.family = (found if isinstance(found, ItemDefinition) else None, found if isinstance(found, Branch) else None,
                                               found if isinstance(found, Family) else None)

    @property
    def used_name(self):
        return self.used.number if self.used else ''


def definition_or_family(text):
    """The physical item definition numbered ``text``, else the branch ("family / branch") or the family named so; None
    when none (what a harness or device is made of is never a service, licence, …)."""
    text = (text or '').strip()
    if not text:
        return None
    family, _, branch = text.rpartition('/')
    return (ItemDefinition.objects.filter(number__iexact=text, kind=ItemDefinition.Kind.PHYSICAL).first()
            or (Branch.objects.filter(family__name__iexact=family.strip(), name__iexact=branch.strip()).first() if family.strip() else None)
            or Family.objects.filter(name__iexact=text).first())


def choices_of_definitions():
    """For a list to type from: (item number, family or branch name, what it is)."""
    def what(n):
        return f'{n} item definition{"s" if n != 1 else ""}'
    return ([(f.name, f'family: {what(f.n)}') for f in Family.objects.annotate(n=models.Count('definitions'))]
            + [(b.number, f'branch: {what(b.n)}') for b in Branch.objects.select_related('family').annotate(n=models.Count('definitions'))]
            + list(ItemDefinition.objects.filter(active=True, kind=ItemDefinition.Kind.PHYSICAL).values_list('number', 'description')[:5000]))


class DefinitionValue(models.Model):
    """What an item definition fills in for an attribute of its category (``number`` too, for numbers: to sort and filter by)."""
    definition = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name='values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=200)
    number = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['definition', 'attribute'], name='unique_definition_value')]

    def __str__(self):
        return f'{self.attribute}: {self.value}'


class DefinitionLink(models.Model):
    """An item definition naming another item definition with an "interacts with" attribute or a link (a pin that mates with a socket)."""
    definition = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name='links')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='links')
    target = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name='linked_from')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['definition', 'attribute', 'target'], name='unique_definition_link')]

    def __str__(self):
        return f'{self.definition} {self.attribute} {self.target}'


class Stock(models.Model):
    """How many of an item definition are in a location now."""
    definition = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name='stock')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='stock')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        ordering = ['definition__number', 'location__name']
        constraints = [models.UniqueConstraint(fields=['definition', 'location'], name='unique_stock')]

    def __str__(self):
        return f'{self.definition} × {self.quantity} in {self.location}'


class Movement(models.Model):
    """One change of stock: into a location, out of one, or from one to another."""
    class Kind(models.TextChoices):
        RECEIVED = 'received', 'Received'
        ADDED = 'added', 'Added'
        MOVED = 'moved', 'Moved'
        USED = 'used', 'Used'
        COUNTED = 'counted', 'Counted'

    definition = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name='movements')
    kind = models.CharField(max_length=10, choices=Kind)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)   # signed for a count: the difference it made
    source = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    target = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    note = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=100, blank=True)   # e.g. the order it was received for
    url = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-pk']

    def __str__(self):
        return f'{self.get_kind_display()} {self.quantity} {self.definition}'
