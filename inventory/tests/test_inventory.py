"""Item definitions and stock: adding, moving, using and counting stock keeps a movement each and never goes below zero; finding
item definitions; an item definition's page; locations and categories as trees."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from inventory import stock
from inventory.models import Category, Location, Movement, ItemDefinition, Vendor
from records.models import Record


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw', first_name='Ada')
        cls.store = Location.objects.create(name='Store')
        cls.shelf = Location.objects.create(name='Shelf 1', parent=cls.store)
        cls.bench = Location.objects.create(name='Bench')
        cls.acme = Vendor.objects.create(name='Acme')
        cls.connectors = Category.objects.create(name='Connectors')
        cls.dsub = Category.objects.create(name='D-sub', parent=cls.connectors)
        cls.plug = ItemDefinition.objects.create(number='DSUB-9-PLUG', description='D-sub 9 plug', category=cls.dsub, vendor=cls.acme,
                                       price=Decimal('2.50'), minimum=10)
        cls.wire = ItemDefinition.objects.create(number='WIRE-22-RED', description='Wire 22 AWG red', unit='m')

    def setUp(self):
        self.client.force_login(self.ada)


class StockTests(Base):
    def test_add_move_use_count(self):
        stock.add(self.plug, '25', self.shelf, self.ada, 'found in a box')
        stock.move(self.plug, 5, self.shelf, self.bench, self.ada)
        stock.use(self.plug, '2,5', self.bench, self.ada)                      # a comma works too
        self.assertEqual(self.plug.on_hand, Decimal('22.5'))
        stock.count(self.plug, self.shelf, 18, self.ada)
        self.assertEqual(sum(r.quantity for r in Record.objects.filter(definition=self.plug, location=self.shelf)), 18)
        self.assertEqual(Record.objects.filter(definition=self.plug).count(), 2)   # the delivery split by the move: each its own
        self.assertEqual([(m.kind, m.quantity) for m in Movement.objects.order_by('pk')],
                         [('added', 25), ('moved', 5), ('used', Decimal('2.5')), ('counted', -2)])

    def test_never_below_zero_and_only_real_quantities(self):
        stock.add(self.plug, 3, self.shelf, self.ada)
        with self.assertRaisesMessage(ValidationError, 'There are only 3 pcs of DSUB-9-PLUG in Store / Shelf 1.'):
            stock.use(self.plug, 4, self.shelf, self.ada)
        for bad in ('0', '-1', 'lots', 'NaN'):
            with self.assertRaises(ValidationError):
                stock.add(self.plug, bad, self.shelf, self.ada)
        with self.assertRaises(ValidationError):
            stock.move(self.plug, 1, self.shelf, self.shelf, self.ada)
        self.assertEqual(self.plug.on_hand, 3)

    def test_from_the_definition_s_page(self):
        url = reverse('inventory:definition_stock', args=[self.plug.pk])
        self.client.post(url, {'action': 'add', 'quantity': '12', 'location': self.shelf.pk})
        self.client.post(url, {'action': 'move', 'quantity': '2', 'location': self.shelf.pk, 'to': self.bench.pk})
        response = self.client.post(url, {'action': 'use', 'quantity': '99', 'location': self.bench.pk}, follow=True)
        self.assertContains(response, 'There are only 2 pcs')
        page = self.client.get(reverse('inventory:definition', args=[self.plug.pk]))
        self.assertContains(page, 'Store / Shelf 1')
        self.assertContains(page, '<b>12</b>', html=False)                       # on hand, written plainly (not 1.2E+1)
        self.assertContains(page, 'Moved <b>2</b>')


class FindingTests(Base):
    def test_the_category_tree_the_list_and_the_definition_picked(self):
        stock.add(self.plug, 3, self.shelf, self.ada)
        page = self.client.get(reverse('inventory:definitions'), {'category': self.dsub.pk, 'definition': self.plug.pk})
        tree = page.context['categories']
        self.assertEqual([(c.name, depth, n) for c, depth, n in tree], [('Connectors', 0, 1), ('D-sub', 1, 1)])   # counted below
        self.assertEqual(page.context['open'], {self.connectors.pk, self.dsub.pk})
        self.assertContains(page, 'data-brief="%d"' % self.plug.pk)                       # its details, already open
        brief = self.client.get(reverse('inventory:definition_brief', args=[self.plug.pk]))
        self.assertContains(brief, 'Shelf 1')
        self.assertContains(brief, 'D-sub 9 plug')

    def test_search_category_and_one_match_goes_straight_to_it(self):
        page = self.client.get(reverse('inventory:definitions'), {'q': 'plug'})
        self.assertRedirects(page, reverse('inventory:definition', args=[self.plug.pk]))
        page = self.client.get(reverse('inventory:definitions'), {'category': self.connectors.pk})   # the categories under it too
        self.assertContains(page, 'DSUB-9-PLUG')
        self.assertNotContains(page, 'WIRE-22-RED')
        ItemDefinition.objects.filter(pk=self.wire.pk).update(active=False)
        self.assertNotContains(self.client.get(reverse('inventory:definitions')), 'WIRE-22-RED')
        self.assertContains(self.client.get(reverse('inventory:definitions'), {'all': 1}), 'WIRE-22-RED')

    def test_making_and_changing_a_definition(self):
        response = self.client.post(reverse('inventory:definition_new'), {
            'number': 'TIE-100', 'description': 'Cable tie', 'unit': 'pcs', 'category': self.connectors.pk,
            'minimum': '0', 'reorder_quantity': '0', 'active': 'on'})
        tie = ItemDefinition.objects.get(number='TIE-100')
        self.assertRedirects(response, reverse('inventory:definition', args=[tie.pk]))
        page = self.client.post(reverse('inventory:definition_new'), {'number': 'tie-100', 'unit': 'pcs', 'minimum': 0, 'reorder_quantity': 0})
        self.assertEqual(ItemDefinition.objects.filter(number__iexact='tie-100').count(), 1)
        self.assertEqual(page.status_code, 200)


class TreeTests(Base):
    def test_locations_show_locations_not_what_is_kept_there(self):
        stock.add(self.plug, 4, self.shelf, self.ada)
        page = self.client.get(reverse('inventory:location', args=[self.store.pk]))
        self.assertContains(page, 'Shelf 1')                                    # inside it
        self.assertNotContains(page, 'DSUB-9-PLUG')                             # what is kept there: the item definition's to say
        listed = self.client.get(reverse('inventory:locations'), {'location': self.store.pk})
        self.assertEqual([l.name for l, _, _ in listed.context['locations']], ['Shelf 1'])
        self.assertNotContains(listed, 'DSUB-9-PLUG')
        self.assertContains(listed, 'data-notes')                               # its notes, changed in place
        self.client.post(reverse('web:notes', args=['location', self.store.pk]), {'notes': 'Key at reception.'})
        self.store.refresh_from_db()
        self.assertEqual(self.store.notes, 'Key at reception.')

    def test_nothing_inside_itself(self):
        page = self.client.post(reverse('inventory:location_edit', args=[self.store.pk]), {'name': 'Store', 'parent': self.shelf.pk})
        self.assertContains(page, 'inside itself')
        page = self.client.post(reverse('inventory:categories') + f'?edit={self.connectors.pk}', {'name': 'Connectors', 'parent': self.dsub.pk})
        self.assertContains(page, 'part of itself')


class LinkTests(Base):
    def test_a_record_shown_is_a_link_to_it(self):
        from web.templatetags.osmia import link
        self.assertEqual(str(link(self.shelf)), f'<a href="{self.shelf.get_absolute_url()}">{self.shelf}</a>')
        self.assertEqual(link(None), '')
        self.assertEqual(str(link(self.ada)), str(self.ada))                     # a person: just the name
        stock.add(self.plug, 4, self.shelf, self.ada)
        page = self.client.get(self.plug.get_absolute_url())
        self.assertContains(page, f'<a href="{self.shelf.get_absolute_url()}">')    # its location, a link


class StandardCategoryTests(Base):
    def test_standard_categories_added_once_with_their_attributes(self):
        from inventory.models import Attribute, Category
        connectors = self.connectors                                                   # there already, with D-sub
        Attribute.objects.create(category=self.dsub, name='Mounting', kind='text')    # its own already
        self.client.post(reverse('inventory:categories_standard'))
        resistors = Category.objects.get(name='Resistors', parent__name='Electronic components')
        self.assertEqual([a.name for a in resistors.all_attributes()][:2], ['Package', 'Mounting'])   # from above
        self.assertTrue(Category.objects.filter(name='Nuts', parent__name='Fasteners').exists())
        self.assertEqual(Category.objects.filter(name__iexact='connectors', parent=None).count(), 1)   # the one there, used
        self.assertEqual(Category.objects.filter(name='D-sub').count(), 1)
        self.assertFalse(connectors.attributes.filter(name='Mounting').exists())       # D-sub has one: not twice
        threads = Attribute.objects.get(category__name='Fasteners', name='Thread')
        self.assertIn('M3', threads.choice_list())
        before = (Category.objects.count(), Attribute.objects.count())
        response = self.client.post(reverse('inventory:categories_standard'), follow=True)   # again: nothing new
        self.assertEqual((Category.objects.count(), Attribute.objects.count()), before)
        self.assertContains(response, 'The standard categories are all there.')
