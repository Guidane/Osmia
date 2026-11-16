"""Records: what is really there. An order line received makes them (so does stock added by hand, or a harness or
device built): so many of an item definition, in a location, from that order. Together they are the stock. Each delivery
stays its own record; using stock takes from the oldest first, moving part of one splits it.

An item definition that is an asset (``is_asset``) is kept one by one: each piece is its own record with an asset tag,
and then also has a serial number, who looks after it, who has it out, its status, calibration and history. So is
each harness or device built (of its design, at a version; a harness with the checklist of its wires). What is bought
but is no thing (a subscription, a licence) is a record too, without a location, and never stock."""
import calendar
from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from inventory.models import Attribute, ItemDefinition, Location


class Record(models.Model):
    class Status(models.TextChoices):
        BUILDING = 'building', 'Being built'
        AVAILABLE = 'available', 'Available'
        OUT = 'out', 'Checked out'
        IN_USE = 'in_use', 'In use'
        CALIBRATION = 'calibration', 'Away for calibration'
        REPAIR = 'repair', 'In repair'
        RETIRED = 'retired', 'Retired'

    definition = models.ForeignKey(ItemDefinition, null=True, blank=True, on_delete=models.PROTECT, related_name='records',
                                   verbose_name='item definition')
    device = models.ForeignKey('devices.Device', null=True, blank=True, on_delete=models.PROTECT, related_name='records')
    harness = models.ForeignKey('harnesses.Harness', null=True, blank=True, on_delete=models.PROTECT, related_name='records')
    version = models.PositiveIntegerField(null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)   # a retired one: 0
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name='records')
    order_line = models.ForeignKey('orders.OrderLine', null=True, blank=True, on_delete=models.SET_NULL, related_name='records',
                                   editable=False)
    tag = models.CharField('asset tag', max_length=100, null=True, blank=True, unique=True)
    asset_number = models.CharField('asset number', max_length=100, blank=True)   # e.g. the company's own (finance) number
    serial = models.CharField('serial number', max_length=100, blank=True)
    keeper = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='kept_records')
    status = models.CharField(max_length=12, choices=Status, default=Status.AVAILABLE)
    holder = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='held_records',
                               editable=False)   # who has it out
    price = models.DecimalField('price each', max_digits=12, decimal_places=2, null=True, blank=True)
    calibrated_on = models.DateField(null=True, blank=True)
    calibration_months = models.PositiveIntegerField('calibration every (months)', null=True, blank=True)
    built_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                                 editable=False)
    built_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        if self.tag:
            return f'{self.tag} {self.name}'
        return f'{self.quantity.normalize():f} × {self.thing.number}' if self.thing else f'Record {self.pk}'

    def get_absolute_url(self):
        return reverse('records:record', args=[self.pk])

    @property
    def thing(self):
        """What it is one (or so many) of: an item definition, a harness or a device."""
        return self.definition or self.harness or self.device

    @property
    def name(self):
        if self.definition:
            return self.definition.description or self.definition.number
        return self.thing.name if self.thing else ''

    @property
    def number(self):   # what lists and links show of it
        return self.tag or str(self)

    @property
    def description(self):   # what lists show next to the number
        return self.name

    @property
    def is_asset(self):
        return bool(self.tag)

    @property
    def calibration_due(self):
        if not self.calibration_months:
            return None
        if self.calibrated_on is None:
            return date.today()   # never calibrated: due now
        months = self.calibrated_on.month - 1 + self.calibration_months
        year, month = self.calibrated_on.year + months // 12, months % 12 + 1
        return date(year, month, min(self.calibrated_on.day, calendar.monthrange(year, month)[1]))

    @property
    def calibration_overdue(self):
        due = self.calibration_due
        return due is not None and due <= date.today() and self.status != self.Status.RETIRED


class RecordValue(models.Model):
    """What an asset fills in for an asset field (``number`` too, for numbers: to sort and filter by)."""
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name='values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='record_values')
    value = models.CharField(max_length=200)
    number = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['record', 'attribute'], name='unique_record_value')]


class RecordCheck(models.Model):
    """A wire of a harness built: what it was when built, placed and verified."""
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name='checks')
    wire = models.CharField(max_length=100)          # "P1:3 → P2:5"
    between = models.CharField(max_length=70)        # "P1 → P2": its heading
    signal = models.CharField(max_length=100, blank=True)
    colour = models.CharField(max_length=20, blank=True)
    wire_set = models.CharField(max_length=20, blank=True)
    placed = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']


class RecordEvent(models.Model):
    """Something that happened to an asset: checked out or back, calibrated, sent away, received, built, a note."""
    class Kind(models.TextChoices):
        OUT = 'out', 'Checked out'
        BACK = 'back', 'Brought back'
        CALIBRATED = 'calibrated', 'Calibrated'
        AWAY = 'away', 'Sent away'
        RECEIVED = 'received', 'Received'
        BUILT = 'built', 'Built'
        NOTE = 'note', 'Note'

    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=12, choices=Kind)
    note = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-pk']
