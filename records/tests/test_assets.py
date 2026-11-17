"""Assets (records with an asset tag): checked out and back, calibration (due after its interval, overdue on Home), sent
away, in use and retired (then no longer stock), moved; the list with its tree of categories, filters and the details of
the one picked; a new one made by hand; labels; the asset fields every asset fills in."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory.models import Attribute, Category, ItemDefinition
from inventory.tests.test_inventory import Base
from records import service
from records.models import Record, RecordValue


class AssetTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tools = Category.objects.create(name='Crimp tools')
        cls.crimper = ItemDefinition.objects.create(number='TE-91601', description='D-sub crimp tool', category=cls.tools, manufacturer='TE',
                                                    is_asset=True)
        cls.tool = Record.objects.create(tag='T-001', definition=cls.crimper, location=cls.shelf, keeper=cls.ada)

    def test_out_and_back_in_use(self):
        self.client.post(reverse('records:act', args=[self.tool.pk]), {'action': 'out', 'to': self.ada.pk, 'note': 'harness H-0001'})
        tool = Record.objects.get(tag='T-001')
        self.assertEqual((tool.status, tool.holder), ('out', self.ada))
        with self.assertRaisesMessage(ValidationError, 'bring it back first'):
            service.send_away(tool, self.ada, Record.Status.REPAIR)
        self.client.post(reverse('records:act', args=[self.tool.pk]), {'action': 'back'})
        tool.refresh_from_db()
        self.assertEqual((tool.status, tool.holder), ('available', None))
        self.assertContains(self.client.get(tool.get_absolute_url()), 'to Ada: harness H-0001')
        service.send_away(tool, self.ada, Record.Status.IN_USE, 'in the burn-in rack')
        self.assertEqual(Record.objects.get(tag='T-001').status, 'in_use')

    def test_calibration_due_and_done(self):
        Record.objects.filter(pk=self.tool.pk).update(calibrated_on=date(2024, 3, 31), calibration_months=11)
        self.assertEqual(Record.objects.get(tag='T-001').calibration_due, date(2025, 2, 28))   # the end of a shorter month
        self.assertContains(self.client.get('/'), 'T-001')                                   # overdue: on Home
        service.send_away(self.tool, self.ada, Record.Status.CALIBRATION)
        self.client.post(reverse('records:act', args=[self.tool.pk]), {'action': 'calibrated', 'on': str(date.today())})
        tool = Record.objects.get(tag='T-001')
        self.assertEqual((tool.calibrated_on, tool.status), (date.today(), 'available'))
        self.assertGreater(tool.calibration_due, date.today() + timedelta(days=300))

    def test_moved_and_retired(self):
        self.assertEqual(self.crimper.on_hand, 1)
        self.client.post(reverse('records:act', args=[self.tool.pk]), {'action': 'move', 'location': self.bench.pk})
        self.assertEqual(Record.objects.get(tag='T-001').location, self.bench)
        service.send_away(self.tool, self.ada, Record.Status.RETIRED)
        self.assertEqual(self.crimper.on_hand, 0)                                    # retired: no longer there
        self.assertNotContains(self.client.get(reverse('records:assets')), 'T-001')
        self.assertContains(self.client.get(reverse('records:assets'), {'status': 'retired'}), 'T-001')

    def test_the_list_finds_and_shows(self):
        Record.objects.filter(pk=self.tool.pk).update(asset_number='FIN-2026-0042')
        self.assertContains(self.client.get(reverse('records:assets'), {'q': 'crimp'}), 'T-001')      # its item definition's words
        self.assertContains(self.client.get(reverse('records:assets'), {'q': 'fin-2026'}), 'T-001')   # its asset number
        self.assertNotContains(self.client.get(reverse('records:assets'), {'q': 'meter'}), 'T-001')
        page = self.client.get(reverse('records:assets'), {'category': self.tools.pk})
        self.assertContains(page, 'T-001')
        self.assertContains(page, 'Crimp tools')                                     # the tree of the categories with assets
        picked = self.client.get(reverse('records:assets'), {'asset': self.tool.pk})   # its details beside the list
        self.assertEqual(picked.context['brief']['record'], self.tool)
        self.assertContains(self.client.get(reverse('records:brief', args=[self.tool.pk])), 'D-sub crimp tool')
        back = self.client.post(reverse('web:notes', args=['record', self.tool.pk]), {'notes': ' Keep it oiled. ', 'next': '/assets/'})
        self.assertEqual(back.status_code, 302)
        self.assertEqual(Record.objects.get(tag='T-001').notes, 'Keep it oiled.')
        self.assertRedirects(self.client.get(f'/assets/{self.tool.pk}/'), self.tool.get_absolute_url(), fetch_redirect_response=False)

    def test_a_new_one_by_hand(self):
        page = self.client.get(reverse('records:new'), {'definition': self.crimper.pk})
        self.assertContains(page, 'TE-91601-001')                                    # the next free tag
        response = self.client.post(reverse('records:new'), {'tag': 'T-002', 'definition': self.crimper.pk, 'location': self.bench.pk})
        made = Record.objects.get(tag='T-002')
        self.assertRedirects(response, made.get_absolute_url())
        self.assertEqual(self.crimper.on_hand, 2)
        response = self.client.post(reverse('records:new'), {'tag': 'T-003', 'definition': self.plug.pk})
        self.assertEqual(response.status_code, 200)                                 # not an item definition that is an asset
        response = self.client.post(reverse('records:new'), {'tag': 'T-002', 'definition': self.crimper.pk})
        self.assertContains(response, 'already exists')

    def test_labels(self):
        Record.objects.filter(pk=self.tool.pk).update(serial='SN-55')
        page = self.client.get(reverse('web:labels', args=['asset']), {'ids': self.tool.pk, 'size': '64x38', 'show_number': '1',
                                                                         'show_serial': '1', 'show_category': '1'})
        self.assertContains(page, 'T-001')
        self.assertContains(page, 'S/N SN-55')
        self.assertContains(page, 'Crimp tools')


class LabelTests(Base):
    def test_labels_of_several_on_a_sheet_and_a_saved_layout(self):
        tie = ItemDefinition.objects.create(number='TIE-100', description='Cable tie 100 mm')
        url = reverse('web:labels', args=['definition'])
        page = self.client.get(url, {'ids': f'{self.plug.pk},{tie.pk}'})
        self.assertContains(page, 'DSUB-9-PLUG')
        self.assertContains(page, 'Cable tie 100 mm')
        self.assertEqual(page.content.decode().count('class="sticker"'), 2)
        self.assertEqual(page.content.decode().count('class="sheet"'), 1)
        page = self.client.get(url, {'ids': tie.pk, 'size': '38x21', 'show_number': '1', 'copies': '70'})
        self.assertNotContains(page, 'Cable tie 100 mm')                      # its description not shown
        self.assertEqual(page.content.decode().count('class="sheet"'), 2)     # 70 labels: two sheets of 65
        self.assertEqual(page.content.decode().count('class="sticker"'), 70)
        self.client.get(url, {'ids': tie.pk, 'size': '99x38', 'show_number': '1', 'save': '1'})
        page = self.client.get(url, {'ids': tie.pk})
        self.assertContains(page, '<option value="99x38" selected>', html=False)


class AssetFieldTests(Base):
    """Asset fields: what every asset fills in, whatever it is (a company's own: an inventory ID, a cost centre)."""
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.crimper = ItemDefinition.objects.create(number='TE-91601', description='D-sub crimp tool', is_asset=True)
        cls.supply = ItemDefinition.objects.create(number='PSU-B', description='Bench supply', is_asset=True)
        cls.tool = Record.objects.create(tag='T-001', definition=cls.crimper)
        stock_of = Record.objects.create(definition=cls.crimper.__class__.objects.create(number='NUT-M3'), quantity=100)
        cls.untagged = stock_of

    def test_asset_fields_every_asset_fills_in(self):
        url = reverse('records:fields')
        self.client.post(url, {'name': 'Inventory ID', 'kind': 'auto', 'prefix': 'INV-', 'digits': '4'})
        ident = Attribute.objects.get(name='Inventory ID')
        self.assertIsNone(ident.category)                                                   # no category: every asset
        self.assertEqual(value_of(self.tool, ident), 'INV-0001')                            # the ones there already: numbered
        self.assertIsNone(value_of(self.untagged, ident))                                   # stock is no asset
        self.client.post(url, {'name': 'Cost centre', 'kind': 'choice', 'choices': 'Lab\nProduction'})
        self.client.post(url, {'name': 'Bought for', 'kind': 'decimal', 'unit': '€'})
        self.assertContains(self.client.post(url, {'name': 'cost centre', 'kind': 'text'}), 'There is already an asset field')
        response = self.client.post(reverse('records:new'), {'tag': 'PSU-02', 'definition': self.supply.pk,
                                                             f'attr_{Attribute.objects.get(name="Cost centre").pk}': 'Lab',
                                                             f'attr_{Attribute.objects.get(name="Bought for").pk}': '129,50',
                                                             'attributes_of': ''})
        psu = Record.objects.get(tag='PSU-02')
        self.assertRedirects(response, psu.get_absolute_url())
        self.assertEqual((value_of(psu, ident), value_of(psu, Attribute.objects.get(name='Cost centre'))), ('INV-0002', 'Lab'))
        self.assertContains(self.client.get(psu.get_absolute_url()), '129.5')
        listed = self.client.get(reverse('records:assets'), {f'a{Attribute.objects.get(name="Cost centre").pk}': 'Lab'})
        self.assertEqual([a.tag for a, _ in listed.context['rows']], ['PSU-02'])           # filtered by it
        self.client.post(reverse('records:field_move', args=[Attribute.objects.get(name='Bought for').pk]), {'to': 'up'})
        self.assertEqual([a.name for a in Attribute.asset_fields()], ['Inventory ID', 'Bought for', 'Cost centre'])
        self.client.post(reverse('records:field_delete', args=[ident.pk]))
        self.assertFalse(Attribute.objects.filter(name='Inventory ID').exists())


def value_of(record, attribute):
    found = RecordValue.objects.filter(record=record, attribute=attribute).first()
    return found.value if found else None


class StockPageTests(Base):
    """The stock: every item definition with something in a location, how many in all and where."""
    def test_all_that_is_in_stock(self):
        from inventory import stock
        stock.add(self.plug, 6, self.shelf, self.ada)
        stock.add(self.plug, 4, self.bench, self.ada)
        stock.add(self.wire, 20, self.bench, self.ada)
        stock.use(self.wire, 20, self.bench, self.ada)                       # used up: not in stock
        page = self.client.get(reverse('records:stock'))
        self.assertEqual([(r['definition'], r['quantity']) for r in page.context['rows']], [(self.plug, 10)])
        self.assertNotContains(page, 'WIRE-22-RED')
        self.assertContains(page, 'Bench')
        page = self.client.get(reverse('records:stock'), {'location': self.store.pk})   # the store and what is inside it
        self.assertEqual([r['quantity'] for r in page.context['rows']], [6])
        self.assertEqual(self.client.get(reverse('records:stock'), {'q': 'nothing like it'}).context['rows'], [])
        self.assertEqual(self.client.get(reverse('records:stock'), {'category': self.dsub.pk}).context['rows'][0]['definition'], self.plug)
        picked = self.client.get(reverse('records:stock'), {'definition': self.plug.pk})
        self.assertContains(picked, f'data-brief="{self.plug.pk}"')
        response = self.client.get(reverse('records:stock'), {'export': 1})
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
