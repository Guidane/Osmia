"""Orders: reordering an item definition (onto the vendor's draft), placing, receiving into stock (partly, then all; the maker
hears), what is late, what needs ordering, and cancelling."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory import stock
from inventory.models import Movement, ItemDefinition
from inventory.tests.test_inventory import Base
from orders import service
from orders.models import Order, OrderLine
from web.models import Notification


class OrderTests(Base):
    def test_reorder_place_and_receive_in_two_parts(self):
        response = self.client.post(reverse('inventory:definition_reorder', args=[self.plug.pk]))
        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:order', args=[order.pk]))
        self.assertEqual((order.number, order.vendor, order.status), ('PO-0001', self.acme, 'draft'))
        line = order.lines.get()
        self.assertEqual((line.quantity, line.price), (10, Decimal('2.50')))     # up to the minimum, at the last price
        service.reorder(self.plug, self.ada)                                     # again: the same draft, more of it
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.lines.get().quantity, 20)

        self.client.post(reverse('orders:place', args=[order.pk]), {'expected_on': str(date.today() + timedelta(days=7))})
        order.refresh_from_db()
        self.assertEqual((order.status, order.ordered_on), ('ordered', date.today()))
        self.assertEqual(service.on_order(self.plug), 20)

        bob = self.make_user('bob')
        self.client.force_login(bob)
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '12', f'l_{line.pk}': self.shelf.pk})
        order.refresh_from_db()
        self.assertEqual(order.status, 'partly')
        self.assertEqual(self.plug.on_hand, 12)
        self.assertEqual(service.on_order(self.plug), 8)
        response = self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '9', f'l_{line.pk}': self.shelf.pk}, follow=True)
        self.assertContains(response, 'Only 8 of DSUB-9-PLUG are still to come.')
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '8', f'l_{line.pk}': self.bench.pk})
        order.refresh_from_db()
        self.assertEqual((order.status, order.received_on), ('received', date.today()))
        self.assertEqual(self.plug.on_hand, 20)
        self.assertEqual(Movement.objects.filter(kind='received', reference='PO-0001').count(), 2)
        self.assertTrue(Notification.objects.filter(user=self.ada, message__contains='it is complete').exists())   # Ada made it

    def make_user(self, name):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.create_user(name, password='pw')

    def test_what_is_late_and_what_needs_ordering(self):
        self.assertEqual([p for p, _, _ in service.needs_ordering()], [self.plug])
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        order.lines.create(definition=self.plug, quantity=10)
        self.assertEqual([p for p, _, _ in service.needs_ordering()], [self.plug])   # a draft isn't coming
        service.place(order, self.ada, date.today() - timedelta(days=1))
        self.assertEqual(service.needs_ordering(), [])                               # on its way
        self.assertTrue(Order.objects.get().overdue)
        home = self.client.get('/')
        self.assertContains(home, 'Late')
        self.assertContains(home, 'PO-0001')
        self.assertContains(self.client.get(reverse('orders:list')), 'Late')

    def test_draft_lines_and_rules(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        with self.assertRaisesMessage(ValidationError, 'has nothing on it yet'):
            service.place(order, self.ada)
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'definition': 'wire-22-red', 'quantity': '50'})
        line = order.lines.get()
        self.assertEqual((line.definition, line.quantity), (self.wire, 50))
        self.client.post(reverse('orders:line_change', args=[order.pk, line.pk]), {'quantity': '60', 'price': '0.12'})
        line.refresh_from_db()
        self.assertEqual((line.quantity, line.price), (60, Decimal('0.12')))
        service.place(order, self.ada)
        self.assertEqual(ItemDefinition.objects.get(pk=self.wire.pk).price, Decimal('0.12'))  # the last price
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'definition': 'DSUB-9-PLUG', 'quantity': '1'})
        self.assertEqual(order.lines.count(), 1)                                     # placed: lines fixed
        with self.assertRaisesMessage(ValidationError, 'Fill in what arrived.'):
            service.receive(order, [], self.ada)

    def test_cancelling(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        line = order.lines.create(definition=self.plug, quantity=10)
        service.place(order, self.ada)
        service.receive(order, [(line, 1, self.shelf)], self.ada)
        with self.assertRaisesMessage(ValidationError, 'can\'t be cancelled any more'):
            service.cancel(order, self.ada)
        other = Order.objects.create(vendor=self.acme)
        service.cancel(other, self.ada)
        self.assertEqual(Order.objects.get(pk=other.pk).status, 'cancelled')

    def test_a_definition_without_a_vendor_can_t_be_reordered(self):
        with self.assertRaisesMessage(ValidationError, 'WIRE-22-RED has no vendor'):
            service.reorder(self.wire, self.ada)
        stock.add(self.wire, 5, self.shelf, self.ada)
        self.assertNotContains(self.client.get(reverse('inventory:definition', args=[self.wire.pk])), 'Reorder</button>')


class RecordTests(Base):
    """What arrives is records: each delivery its own; each one of an item definition that is an asset its own, with
    its asset tag."""
    def test_a_delivery_is_a_record_of_its_own(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        line = order.lines.create(definition=self.plug, quantity=10, price=Decimal('2.50'))
        service.place(order, self.ada)
        stock.add(self.plug, 4, self.shelf, self.ada)
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '6', f'l_{line.pk}': self.shelf.pk})
        received = self.plug.records.get(order_line=line)
        self.assertEqual((received.quantity, received.location, received.price), (6, self.shelf, Decimal('2.50')))
        self.assertEqual(self.plug.records.count(), 2)
        stock.use(self.plug, 5, self.shelf, self.ada)                          # the oldest first: the 4 added, then 1 of the 6
        self.assertEqual([r.quantity for r in self.plug.records.all()], [5])
        self.assertContains(self.client.get(reverse('inventory:definition', args=[self.plug.pk])), order.number)

    def test_each_asset_that_arrives_gets_its_tag(self):
        meter = ItemDefinition.objects.create(number='METER-1', description='Bench meter', vendor=self.acme, is_asset=True, price=Decimal('300'))
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        line = order.lines.create(definition=meter, quantity=3, price=Decimal('300'))
        service.place(order, self.ada)
        page = self.client.get(reverse('orders:order', args=[order.pk]))
        self.assertContains(page, 'METER-1-001 METER-1-002 METER-1-003')        # the tags they would get
        response = self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '2', f'l_{line.pk}': self.bench.pk}, follow=True)
        self.assertContains(response, 'its asset tag')                          # a quantity is not enough
        self.client.post(reverse('orders:receive', args=[order.pk]), {f't_{line.pk}': 'M-1, M-2', f'l_{line.pk}': self.bench.pk})
        self.assertEqual(list(meter.records.values_list('tag', 'quantity', 'location')), [('M-1', 1, self.bench.pk), ('M-2', 1, self.bench.pk)])
        self.assertEqual((OrderLine.objects.get().received, Order.objects.get().status), (2, 'partly'))
        self.assertEqual(meter.on_hand, 2)
        response = self.client.post(reverse('orders:receive', args=[order.pk]), {f't_{line.pk}': 'M-2', f'l_{line.pk}': self.bench.pk}, follow=True)
        self.assertContains(response, 'There is already an asset M-2')
        with self.assertRaisesMessage(ValidationError, 'is an asset'):
            stock.use(meter, 1, self.bench, self.ada)
        self.assertContains(self.client.get(reverse('records:assets')), 'M-1')
