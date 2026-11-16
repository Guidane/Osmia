"""What is bought but is not a thing (a service, a subscription, a licence, a statement of work): ordered and received like
anything else, but never kept in stock, never short of stock, and never what a harness or device is made of."""
from decimal import Decimal

from django.urls import reverse

from inventory.models import ItemDefinition, Movement, definition_or_family, choices_of_definitions
from inventory.tests.test_inventory import Base
from orders import service
from orders.models import Order


class KindTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.calibration = ItemDefinition.objects.create(number='CAL-DMM', description='Calibration of a multimeter', vendor=cls.acme,
                                                        kind=ItemDefinition.Kind.SERVICE, price=Decimal('85'))

    def test_received_without_a_location_or_stock(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        line = order.lines.create(definition=self.calibration, quantity=1, price=Decimal('85'))
        service.place(order, self.ada)
        page = self.client.get(order.get_absolute_url())
        self.assertNotContains(page, f'name="l_{line.pk}"')                      # no location to pick
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '1'})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.RECEIVED)
        self.assertFalse(Movement.objects.filter(definition=self.calibration).exists())
        made = self.calibration.records.get()                                 # a record of it: no location, no stock
        self.assertEqual((made.order_line, made.location, made.quantity), (line, None, 1))

    def test_its_page_and_form(self):
        page = self.client.get(self.calibration.get_absolute_url())
        self.assertContains(page, 'Service')
        self.assertNotContains(page, 'stock-form')
        self.assertNotContains(page, 'on hand')
        self.client.post(reverse('inventory:definition_edit', args=[self.calibration.pk]),
                         {'kind': 'subscription', 'number': 'CAL-DMM', 'unit': 'year', 'minimum': '5', 'reorder_quantity': '2'})
        self.calibration.refresh_from_db()
        self.assertEqual((self.calibration.kind, self.calibration.minimum, self.calibration.reorder_quantity), ('subscription', 0, 0))

    def test_never_short_and_never_part_of_a_harness(self):
        ItemDefinition.objects.filter(pk=self.calibration.pk).update(minimum=3)
        self.assertNotIn(self.calibration, [d for d, *_ in service.needs_ordering()])
        self.assertIsNone(definition_or_family('CAL-DMM'))
        self.assertEqual(definition_or_family('DSUB-9-PLUG'), self.plug)
        self.assertNotIn('CAL-DMM', [number for number, _ in choices_of_definitions()])
