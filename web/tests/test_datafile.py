"""The Import page: an Osmia data file with every section (as an AI makes one from screenshots), taken in whole or not
at all; again, changing what is there and keeping devices, harnesses and orders; other files it recognises (CSV of
item definitions, a harness file); the AI instructions with this Osmia's names."""
import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from inventory.tests.test_inventory import Base

DATA = {
    'kind': 'osmia data', 'version': 1,
    'vendors': [{'name': 'Bolt & Co', 'website': 'https://bolt.example'}],
    'locations': [{'path': 'Lab / Cabinet 2', 'description': 'by the window'}],
    'departments': [{'path': 'Engineering / Test', 'manager': 'ada'}],
    'item_definitions': [
        {'number': 'NUT-M3', 'description': 'Nut M3', 'category': 'Hardware / Nuts', 'vendor': 'Bolt & Co', 'price': '0,05', 'unit': 'pieces'},
        {'number': 'SCOPE-1', 'description': 'Oscilloscope', 'category': 'Lab equipment', 'is_asset': True, 'price': 1200},
        {'number': 'DSUB-9-PLUG', 'minimum': 40}],
    'projects': [{'code': 'BR', 'name': 'Burn-in', 'status': 'active'}, {'code': 'BR-4', 'name': 'Rack 4', 'part_of': 'BR', 'owner': 'ada'}],
    'setups': [{'code': 'R4', 'name': 'Rack 4 bench', 'project': 'BR-4',
                'devices': [{'key': 'D1', 'device': 'CTRL-1'}, {'key': 'D2', 'device': 'LOAD-1', 'label': 'Load'}]}],
    'budgets': [{'number': 'FY27', 'name': '2027', 'amount': 5000, 'owner': 'ada'},
                {'number': 'FY27-BR', 'name': 'Burn-in', 'part_of': 'FY27', 'amount': 800, 'setup': 'R4', 'starts_on': '2027-01-01'}],
    'devices': [
        {'number': 'CTRL-1', 'name': 'Controller', 'connectors': [{'designator': 'J1', 'family': 'D-sub 9 / pin', 'pins': [{'number': '1', 'signal': '+24 V'}]}]},
        {'number': 'LOAD-1', 'name': 'Load board', 'connectors': [{'designator': 'J2', 'pins': [{'number': '1'}]}]}],
    'harnesses': [{'name': 'Controller to load', 'setup': 'R4', 'plugs': {'P1': 'D1:J1', 'P2': 'D2'},
                   'connectors': [{'designator': 'P1'}, {'designator': 'P2'}],
                   'wires': [{'from': 'P1', 'from_pin': '1', 'to': 'P2', 'to_pin': '1', 'colour': 'red', 'signal': '+24 V'}]}],
    'stock': [{'item': 'NUT-M3', 'location': 'Lab / Cabinet 2', 'quantity': 500}],
    'assets': [{'tag': 'SCOPE-001', 'item': 'SCOPE-1', 'location': 'Lab/Cabinet 2', 'serial': 'X123', 'status': 'available',
                'calibrated_on': '2026-02-01', 'calibration_months': 12}],
    'orders': [{'number': 'OLD-17', 'vendor': 'Bolt & Co', 'budget': 'FY27-BR', 'status': 'received', 'ordered_on': '2026-01-05',
                'lines': [{'item': 'NUT-M3', 'quantity': 500, 'price': 0.05}]}],
}


def sent(data, name='osmia-data.json'):
    return SimpleUploadedFile(name, json.dumps(data).encode('utf-8'))


class DataFileTests(Base):
    def send(self, file):
        return self.client.post(reverse('web:import'), {'file': file}, follow=True)

    def test_every_section_and_again(self):
        from budgets.models import Budget
        from inventory.models import ItemDefinition, Location
        from orders.models import Order
        from records.models import Record
        from setups.models import Placement, Setup
        from work.models import Project
        page = self.send(sent(DATA))
        self.assertContains(page, 'item definitions 2 made, 1 changed')
        self.assertContains(page, 'Category Hardware / Nuts was made.')
        nut = ItemDefinition.objects.get(number='NUT-M3')
        self.assertEqual((nut.vendor.name, nut.price, nut.unit, nut.on_hand), ('Bolt & Co', Decimal('0.05'), 'pcs', 500))
        self.assertEqual(ItemDefinition.objects.get(number='DSUB-9-PLUG').minimum, 40)
        self.assertEqual(Project.objects.get(code='BR-4').parent.code, 'BR')
        self.assertEqual(Budget.objects.get(number='FY27-BR').parent.number, 'FY27')
        setup = Setup.objects.get(code='R4')
        self.assertEqual(setup.in_project.code, 'BR-4')
        devices = {p.key: p for p in Placement.objects.filter(setup=setup, kind='device')}
        self.assertEqual((devices['D1'].device.number, devices['D2'].label), ('CTRL-1', 'Load'))
        harness = Placement.objects.get(setup=setup, kind='harness')
        plugs = {e.designator: harness.ends[str(e.pk)] for e in harness.harness.ends.all()}
        self.assertEqual(plugs['P2'], 'D2')
        self.assertEqual(plugs['P1'][0], 'D1')
        scope = Record.objects.get(tag='SCOPE-001')
        self.assertEqual((scope.location, scope.serial, scope.calibration_months), (Location.objects.get(name='Cabinet 2'), 'X123', 12))
        order = Order.objects.get(number='OLD-17')
        self.assertEqual((order.status, order.lines.get().received, order.budget.number), ('received', 500, 'FY27-BR'))
        self.assertEqual(Record.objects.filter(definition=nut).count(), 1)   # (an order brings no stock of its own)

        again = dict(DATA, stock=[{'item': 'NUT-M3', 'location': 'Lab / Cabinet 2', 'quantity': 420}],
                     item_definitions=[{'number': 'nut-m3', 'description': 'Hex nut M3'}])
        page = self.send(sent(again))
        self.assertContains(page, 'Device CTRL-1 is there already: kept as it is.')
        self.assertContains(page, 'Order OLD-17 is there already')
        self.assertContains(page, 'Harness Controller to load in R4 Rack 4 bench is there already')
        nut.refresh_from_db()
        self.assertEqual((nut.description, nut.vendor.name, nut.on_hand), ('Hex nut M3', 'Bolt & Co', 420))
        self.assertEqual(Setup.objects.count(), 1)
        self.assertEqual(Placement.objects.filter(setup=setup).count(), 3)

    def test_anything_wrong_and_nothing_is_imported(self):
        from inventory.models import ItemDefinition, Vendor
        wrong = dict(DATA, budgets=[{'number': 'FY27', 'name': '2027', 'owner': 'nobody'}],
                     stock=[{'item': 'NO-SUCH', 'location': 'Lab / Cabinet 2', 'quantity': 1}],
                     orders=[{'vendor': 'Bolt & Co', 'lines': []}])
        page = self.send(sent(wrong))
        for said in ('Nothing was imported.', 'budgets 1: there is no user &quot;nobody&quot;.',
                     'stock 1: there is no item definition &quot;NO-SUCH&quot;.', 'orders 1: give its &quot;lines&quot;'):
            self.assertContains(page, said)
        self.assertFalse(ItemDefinition.objects.filter(number='NUT-M3').exists())
        self.assertFalse(Vendor.objects.filter(name='Bolt & Co').exists())
        self.assertContains(self.send(sent({'kind': 'osmia data'})), 'is not an Osmia data file')
        self.assertContains(self.send(SimpleUploadedFile('x.json', b'{nope')), 'is not a file Osmia takes in')

    def test_other_files_it_knows(self):
        from harnesses.models import Harness
        from inventory.models import ItemDefinition
        csv = SimpleUploadedFile('parts.csv', 'Item number;Description;Last price\nCAP-100N;Capacitor 100 nF;0,02\n'.encode('utf-8'))
        page = self.send(csv)
        self.assertContains(page, '1 item definitions made, 0 changed')
        self.assertEqual(ItemDefinition.objects.get(number='CAP-100N').price, Decimal('0.02'))
        harness = {'kind': 'osmia harness', 'name': 'Patch', 'wires': [{'from': 'P1', 'from_pin': '1', 'to': 'P2', 'to_pin': '1'}]}
        self.send(sent(harness, 'patch.json'))
        self.assertTrue(Harness.objects.filter(name='Patch').exists())

    def test_the_ai_instructions(self):
        page = self.client.get(reverse('web:import'))
        self.assertContains(page, reverse('web:ai_instructions'))
        text = self.client.get(reverse('web:ai_instructions')).content.decode('utf-8')
        for said in ('# Osmia: instructions for an AI', '### item_definitions', '## Osmia harness file', '`Shielded twisted`',
                     '## What this Osmia has', 'DSUB-9-PLUG: D-sub 9 plug', 'Connectors / D-sub'):
            self.assertIn(said, text)
        from web import ai
        self.assertNotIn('What this Osmia has', ai.describe(names=False))
