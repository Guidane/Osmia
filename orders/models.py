"""Orders to vendors, charged to a budget: item definitions and assets ordered, when they are expected, and what has arrived.
Receiving books the item definitions into stock and makes the assets available (``orders.service``). An order can start as a
request: someone describes what they need and asks someone else to order it, who adds the lines and places it."""
from datetime import date

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse

from inventory.models import ItemDefinition, Vendor


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ORDERED = 'ordered', 'Ordered'
        PARTLY = 'partly', 'Partly received'
        RECEIVED = 'received', 'Received'
        CANCELLED = 'cancelled', 'Cancelled'

    class Kind(models.TextChoices):
        ORDER = 'order', 'Order'
        REQUEST = 'request', 'Request to order'

    OPEN = (Status.ORDERED, Status.PARTLY)   # waiting for something to arrive

    number = models.CharField(max_length=20, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind, default=Kind.ORDER)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.PROTECT, related_name='orders')
    request = models.TextField('what is needed', blank=True)
    ask = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='order_requests',
                            verbose_name='who should order it')
    budget = models.ForeignKey('budgets.Budget', null=True, blank=True, on_delete=models.PROTECT, related_name='orders')
    in_project = models.ForeignKey('work.Project', null=True, blank=True, on_delete=models.SET_NULL, related_name='orders',
                                   verbose_name='project')
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    vendor_reference = models.CharField("vendor's order number", max_length=100, blank=True)
    ordered_on = models.DateField(null=True, blank=True)
    expected_on = models.DateField('expected', null=True, blank=True)
    received_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pk']

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('orders:order', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.number:
            with transaction.atomic():
                last = Order.objects.select_for_update().order_by('-pk').values_list('pk', flat=True).first() or 0
                self.number = f'PO-{last + 1:04d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @property
    def overdue(self):
        return self.status in self.OPEN and self.expected_on is not None and self.expected_on < date.today()

    @property
    def total(self):
        return sum((line.price or 0) * line.quantity for line in self.lines.all())


class OrderLine(models.Model):
    """An item definition (so many) or an asset (one) on an order."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    definition = models.ForeignKey(ItemDefinition, null=True, blank=True, on_delete=models.PROTECT, related_name='order_lines')
    asset = models.ForeignKey('assets.Asset', null=True, blank=True, on_delete=models.PROTECT, related_name='order_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    price = models.DecimalField('price each', max_digits=12, decimal_places=4, null=True, blank=True)
    received = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.order}: {self.item} × {self.quantity}'

    @property
    def item(self):
        """The item definition or asset ordered."""
        return self.definition or self.asset

    @property
    def stocked(self):
        """Whether what arrives of it goes somewhere: an asset, or a physical item definition (not a service, ...)."""
        return bool(self.asset_id) or bool(self.definition and self.definition.physical)

    @property
    def text(self):
        """What it is, in words: an item definition's description, an asset's name."""
        return self.definition.description if self.definition else self.asset.name

    @property
    def vendor_number(self):
        return self.item.vendor_number

    @property
    def outstanding(self):
        return max(self.quantity - self.received, 0)
