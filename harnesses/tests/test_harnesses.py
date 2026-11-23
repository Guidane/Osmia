"""Harnesses: their connectors (what they plug into is the setup's to say), the pinout edited as a table,
what is wrong with it, its parts list, versions, and building one: a serial number, a checklist, item definitions out of stock."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from devices.models import Connector, Device, Pin
from devices.tests.test_devices import DeviceBase
from harnesses import views
from records.models import Record
from harnesses.models import Harness, HarnessEnd, Wire
from inventory import stock
from setups.models import Setup
from web import versions


class HarnessBase(DeviceBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.board = Device.objects.create(number='LOAD-1', name='Load board')
        cls.board_j1 = Connector.objects.create(device=cls.board, designator='J1', name='Bus in')
        for number, signal in (('1', '+24 V'), ('3', '0 V'), ('2', 'CAN H'), ('7', 'CAN L')):
            Pin.objects.create(connector=cls.board_j1, number=number, signal=signal)
        cls.setup = Setup.objects.create(name='Burn-in rack')
        cls.harness = Harness.objects.create(setup=cls.setup, name='Bus loom')
        cls.p1 = HarnessEnd.objects.create(harness=cls.harness, designator='P1', definition=cls.plug)
        cls.p2 = HarnessEnd.objects.create(harness=cls.harness, designator='P2', definition=cls.plug, position=1)

    def connect(self, a, b, signal='', **more):
        return Wire.objects.create(harness=self.harness, from_end=self.p1, from_pin=a, to_end=self.p2, to_pin=b, signal=signal, **more)


class PinoutTests(HarnessBase):
    def test_the_pinout_as_a_table_and_what_is_wrong(self):
        p1, p2 = self.p1.pk, self.p2.pk
        self.j1.pins.filter(number='6').update(wire_set='CAN', set_type='Twisted')
        response = self.client.post(reverse('harnesses:pinout', args=[self.harness.pk]), {
            'r0_seen': 1, 'r0_from_end': p1, 'r0_from_pin': '1', 'r0_to_end': p2, 'r0_to_pin': '1', 'r0_length': '450',
            'r0_definition': 'wire-22-red', 'r0_colour': 'red',
            'r1_seen': 1, 'r1_from_end': p1, 'r1_from_pin': '6', 'r1_to_end': p2, 'r1_to_pin': '7',           # crossed over
            'r2_seen': 1, 'r2_from_end': p1, 'r2_from_pin': '9', 'r2_to_end': p2, 'r2_to_pin': '3', 'r2_signal': 'GND',
            'r3_seen': 1})
        self.assertRedirects(response, reverse('harnesses:harness', args=[self.harness.pk]))
        wires = {w.from_pin: w for w in self.harness.wires.all()}
        self.assertEqual((wires['1'].signal, wires['9'].signal), ('', 'GND'))   # its own: it knows no device
        self.assertEqual((wires['1'].wire_set, wires['1'].set_type), ('', 'Straight'))
        self.assertEqual(self.harness.problems(), [])                           # the devices' pins: the setup's to check
        self.assertIn((self.wire, Decimal('0.45')), self.harness.parts_list())   # metres of wire
        self.assertIn((self.plug, Decimal(2)), self.harness.parts_list())                 # its two ends
        response = self.client.post(reverse('harnesses:pinout', args=[self.harness.pk]), {
            'r0_seen': 1, 'r0_from_end': p1, 'r0_from_pin': '2', 'r0_to_end': p2, 'r0_to_pin': '3', 'r0_definition': 'NOPE'}, follow=True)
        self.assertContains(response, 'Row 1: there is no item definition or family &quot;NOPE&quot;.')
        self.assertEqual(self.harness.wires.count(), 3)                         # nothing of it was kept

    def test_the_harness_list_as_a_tree_and_a_harness_picked(self):
        from work.models import Project as Work
        rack = Work.objects.create(code='BR', name='Rack')
        type(self.harness.setup).objects.filter(pk=self.harness.setup_id).update(in_project=rack)
        self.connect('6', '2', signal='CAN H')
        page = self.client.get(reverse('harnesses:list'), {'work': rack.pk, 'harness': self.harness.pk})
        self.assertEqual([(kind, depth, n) for kind, _, depth, n in page.context['tree']], [('work', 0, 1), ('setup', 1, 1)])
        self.assertContains(page, self.harness.number)
        self.assertContains(page, 'data-brief="%d"' % self.harness.pk)                    # its details, already open
        brief = self.client.get(reverse('harnesses:brief', args=[self.harness.pk]))
        self.assertContains(brief, 'CAN H')
        self.assertContains(self.client.get(reverse('harnesses:list'), {'q': 'nothing like it'}), 'No harnesses match')

    def test_the_pinout_drawn_in_each_connector_s_layout(self):
        from inventory.faces import start
        from inventory.models import Branch, Family
        self.connect('6', '2', wire_set='CAN', set_type='Twisted')
        page = self.client.get(reverse('harnesses:harness', args=[self.harness.pk]))
        self.assertContains(page, f'?setup={self.harness.setup_id}&amp;harness={self.harness.pk}">← Harnesses')   # back: the list
        self.assertContains(page, 'used in setup')
        for tab in ('pinout', 'bundle', 'wires', 'bom', 'versions', 'built'):   # the page as a tree, a panel each
            self.assertContains(page, f'data-panel="{tab}"')
        self.assertContains(page, 'data-notes')
        p1, p2 = page.context['drawing']['ends']
        self.assertEqual(p1['face']['shape'], 'rect')                                    # nothing known: a row of its pins
        self.assertEqual(([n for n, _ in p1['pins']], [n for n, _ in p2['pins']]), (['6'], ['2']))   # only the pins its wires use
        dsub = Family.objects.create(name='D-sub 9', face=start('staggered', 9))
        self.plug.family = dsub
        self.plug.save()
        p1, p2 = self.client.get(reverse('harnesses:harness', args=[self.harness.pk])).context['drawing']['ends']
        self.assertEqual((p1['face']['shape'], len(p1['face']['contacts'])), ('dsub', 9))   # its item definition's family
        self.plug.branch = Branch.objects.create(family=dsub, name='socket', contacts='socket')
        self.plug.save()
        p1 = self.client.get(reverse('harnesses:harness', args=[self.harness.pk])).context['drawing']['ends'][0]
        self.assertEqual(p1['face']['contacts'][0][1], dsub.face['w'] - dsub.face['contacts'][0][1])   # a socket: mirrored
        self.board_j1.definition = None
        self.board_j1.save()
        self.p2.used = None
        self.p2.save()
        self.assertEqual(self.client.get(reverse('harnesses:harness', args=[self.harness.pk])).context['drawing']['ends'][1]['face']['shape'], 'rect')
        self.assertIn({'id': Wire.objects.get().pk, 'from': self.p1.pk, 'from_pin': '6', 'to': self.p2.pk, 'to_pin': '2', 'signal': '', 'to_signal': '', 'group': '', 'set': 'CAN', 'type': 'Twisted', 'gauge': '', 'length': '',
                       'colour': ''}, page.context['drawing']['wires'])

    def test_a_shield_joined_on_one_side_or_both(self):
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        self.connect('6', '2', wire_set='CAN', set_type='Shielded twisted')
        self.connect('7', '7', wire_set='CAN', set_type='Shielded twisted')
        common = {'action': 'shield', 'set': 'CAN', 'a_end': self.p1.pk, 'b_end': self.p2.pk}
        self.client.post(url, {**common, 'a_pin': '9', 'b_pin': ''})                      # the left side only
        shield = Wire.objects.get(set_type='Shield')
        self.assertEqual((shield.wire_set, shield.from_pin, shield.to_pin), ('CAN', '9', ''))
        self.assertFalse(any('no pin  (' in text for _, text in self.harness.problems()))  # not joined there: no problem
        self.client.post(url, {**common, 'a_pin': '9', 'b_pin': '8'})                     # both sides: the same wire
        self.assertEqual(Wire.objects.get(set_type='Shield').to_pin, '8')
        self.client.post(url, {**common, 'a_pin': '', 'b_pin': ''})                       # on neither: gone
        self.assertFalse(Wire.objects.filter(set_type='Shield').exists())
        self.assertEqual(self.client.post(url, {**common, 'set': 'NONE', 'a_pin': '9'}).status_code, 400)

    def test_connectors_added_changed_and_taken_away_in_the_drawing(self):
        from inventory.faces import start
        from inventory.models import Family
        dsub = Family.objects.create(name='D-sub 9', face=start('staggered', 9))
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        drawing = self.client.post(url, {'action': 'end_add', 'side': 'right', 'used': 'D-sub 9 / socket'}).json()
        added = self.harness.ends.get(designator='P3')                                      # the next free one
        self.assertEqual((added.side, str(added.used), added.used.contacts), ('right', 'D-sub 9 / socket', 'socket'))   # made
        end = next(e for e in drawing['ends'] if e['id'] == added.pk)
        self.assertEqual((end['side'], end['used']), ('right', 'D-sub 9 / socket'))
        self.client.post(url, {'action': 'end_set', 'end': added.pk, 'used': 'D-sub 9'})
        added.refresh_from_db()
        self.assertEqual(added.used, dsub)
        self.assertEqual(self.client.post(url, {'action': 'end_set', 'end': added.pk, 'used': 'NOPE'}).status_code, 400)
        wire = self.connect('6', '2')
        self.client.post(url, {'action': 'end_delete', 'end': self.p2.pk})
        self.assertFalse(self.harness.ends.filter(pk=self.p2.pk).exists())
        self.assertFalse(Wire.objects.filter(pk=wire.pk).exists())                           # its wires with it

    def test_sets_in_groups_in_the_drawing(self):
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        tx, rx, gnd = self.connect('2', '2', wire_set='1', set_type='Twisted'), self.connect('3', '3', wire_set='1', set_type='Twisted'), self.connect('5', '5')
        versions.save(self.harness, self.ada)
        drawing = self.client.post(url, {'action': 'group', 'wire': tx.pk, 'group': ' Channel  1 '}).json()
        self.assertEqual({w.pk: w.wire_group for w in Wire.objects.all()}, {tx.pk: 'Channel 1', rx.pk: 'Channel 1', gnd.pk: ''})   # its whole set
        self.assertEqual({w['id']: w['group'] for w in drawing['wires']}[rx.pk], 'Channel 1')
        self.client.post(url, {'action': 'group', 'wire': gnd.pk, 'group': 'Channel 1'})                               # in no set: just it
        other = self.connect('6', '6')
        self.client.post(url, {'action': 'set', 'wire': other.pk, 'set': '1'})
        self.assertEqual(Wire.objects.get(pk=other.pk).wire_group, 'Channel 1')                                         # into the set: its group too
        self.assertTrue(versions.changed(self.harness))
        page = self.client.get(self.harness.get_absolute_url())
        self.assertContains(page, 'Channel 1')
        self.assertIn(['P1', '2', 'P2', '2', '', 'Channel 1'], [list(r[:6]) for r in views._sheets(self.harness)[0][2]])

    def test_a_group_s_lengths_and_where_its_bundle_ends(self):
        from harnesses.models import HarnessGroup
        self.connect('2', '2', wire_set='1', set_type='Twisted', wire_group='Channel 1')
        self.connect('3', '3', wire_set='1', set_type='Twisted', wire_group='Channel 1')
        self.connect('5', '5', wire_group='Channel 2')
        url = reverse('harnesses:groups', args=[self.harness.pk])
        self.client.post(url, {'length_0': '1200', 'bundled_0': '400', 'length_1': '1000', 'bundled_1': '500'})
        one, two = HarnessGroup.objects.get(name='Channel 1'), HarnessGroup.objects.get(name='Channel 2')
        self.assertEqual((one.length, one.bundled, one.breakout, two.breakout), (1200, 400, '1/3', '1/2'))
        self.assertEqual(HarnessGroup(length=1000, bundled=600).breakout, '2/3')
        self.assertIsNone(HarnessGroup(length=1000).breakout)
        drawing = self.client.get(self.harness.get_absolute_url()).context['drawing']
        self.assertEqual(drawing['groups']['Channel 1'], {'length': '1200', 'bundled': '400', 'breakout': '1/3'})
        response = self.client.post(url, {'length_0': '100', 'bundled_0': '400'}, follow=True)
        self.assertContains(response, 'bundled for longer than it is')
        self.assertEqual(HarnessGroup.objects.get(name='Channel 1').length, 1200)        # nothing saved
        self.client.post(url, {'length_0': '1200', 'bundled_0': '400', 'length_1': '1000', 'bundled_1': ''})   # no bundle: fine
        two.refresh_from_db()
        self.assertEqual((two.length, two.bundled, two.breakout), (1000, None, None))                       # (no line drawn)
        saved = versions.save(self.harness, self.ada)
        HarnessGroup.objects.all().delete()
        self.assertTrue(versions.changed(self.harness))
        self.harness.restore(saved.data)
        self.assertEqual(HarnessGroup.objects.get(name='Channel 2').length, 1000)

    def test_the_pinout_edited_in_its_drawing(self):
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        drawing = self.client.post(url, {'action': 'add', 'from_end': self.p1.pk, 'from_pin': '6', 'to_end': self.p2.pk, 'to_pin': '2'}).json()
        wire = Wire.objects.get()
        self.assertEqual((wire.from_pin, wire.to_pin, wire.signal), ('6', '2', ''))   # a purpose: given in the drawing
        self.assertEqual(drawing['wires'][0]['id'], wire.pk)
        self.client.post(url, {'action': 'set', 'wire': wire.pk, 'set': 'new:Shielded twisted'})
        wire.refresh_from_db()
        self.assertEqual((wire.wire_set, wire.set_type), ('1', 'Shielded twisted'))      # the next free number
        other = self.connect('7', '7')
        self.client.post(url, {'action': 'set', 'wire': other.pk, 'set': '1'})
        other.refresh_from_db()
        self.assertEqual((other.wire_set, other.set_type), ('1', 'Shielded twisted'))    # the set's type
        drain = self.connect('9', '8')
        self.client.post(url, {'action': 'set', 'wire': drain.pk, 'set': 'shield:1'})
        drain.refresh_from_db()
        self.assertEqual((drain.wire_set, drain.set_type), ('1', 'Shield'))
        self.client.post(url, {'action': 'set_type', 'wire': wire.pk, 'type': 'Twisted'})     # the set's type changed
        self.assertEqual(sorted(Wire.objects.filter(wire_set='1').values_list('set_type', flat=True)), ['Shield', 'Twisted', 'Twisted'])
        self.client.post(url, {'action': 'set_type', 'wire': other.pk, 'type': 'Shield'})     # a wire made its shield
        self.assertEqual(Wire.objects.get(pk=other.pk).set_type, 'Shield')
        loose = self.connect('3', '5')
        self.assertEqual(self.client.post(url, {'action': 'set_type', 'wire': loose.pk, 'type': 'Twisted'}).status_code, 400)
        self.client.post(url, {'action': 'colour', 'wire': drain.pk, 'colour': 'grey'})
        self.assertEqual(Wire.objects.get(pk=drain.pk).colour, 'grey')
        gauged = self.client.post(url, {'action': 'gauge', 'wire': drain.pk, 'gauge': '24'}).json()   # a bare number: AWG
        self.assertEqual(Wire.objects.get(pk=drain.pk).gauge, '24 AWG')
        self.assertIn('24 AWG', [w['gauge'] for w in gauged['wires']])
        self.client.post(url, {'action': 'signal', 'wire': drain.pk, 'signal': ' TX+ '})          # its purpose
        self.assertEqual(Wire.objects.get(pk=drain.pk).signal, 'TX+')
        made = self.client.post(url, {'action': 'add', 'from_end': self.p1.pk, 'from_pin': '4', 'to_end': self.p1.pk, 'to_pin': '5'})
        loop = Wire.objects.get(from_end=self.p1, to_end=self.p1, from_pin='4')
        self.client.post(url, {'action': 'signal', 'wire': loop.pk, 'signal': 'TX'})            # a loopback: comes back as RX
        self.assertEqual((Wire.objects.get(pk=loop.pk).signal, Wire.objects.get(pk=loop.pk).to_signal), ('TX', 'RX'))
        self.client.post(url, {'action': 'signal', 'wire': loop.pk, 'signal': 'GND', 'end': 'to'})   # its own
        self.client.post(url, {'action': 'signal', 'wire': loop.pk, 'signal': 'MOSI'})          # kept, as it was set
        self.assertEqual((Wire.objects.get(pk=loop.pk).signal, Wire.objects.get(pk=loop.pk).to_signal), ('MOSI', 'GND'))
        self.assertIn('Power', [n['name'] for n in made.json()['purposes']])
        self.client.post(url, {'action': 'gauge', 'wire': drain.pk, 'gauge': ' 0.5  mm² '})
        self.assertEqual(Wire.objects.get(pk=drain.pk).gauge, '0.5 mm²')
        self.client.post(url, {'action': 'delete', 'wire': drain.pk})
        self.assertFalse(Wire.objects.filter(pk=drain.pk).exists())
        self.assertEqual(self.client.post(url, {'action': 'add', 'from_end': self.p1.pk}).status_code, 400)
        loop = self.client.post(url, {'action': 'add', 'from_end': self.p1.pk, 'from_pin': '1', 'to_end': self.p1.pk, 'to_pin': '2'})
        self.assertEqual(loop.status_code, 200)                                                  # a loopback
        self.assertTrue(Wire.objects.filter(from_end=self.p1, to_end=self.p1, from_pin='1', to_pin='2').exists())
        self.assertEqual(self.client.post(url, {'action': 'add', 'from_end': self.p1.pk, 'from_pin': '3',
                                                'to_end': self.p1.pk, 'to_pin': '3'}).status_code, 400)   # not to itself

    def test_a_splice_but_not_the_same_wire_twice(self):
        self.connect('1', '1')
        self.connect('1', '3')                                                     # a splice: fine
        self.assertFalse([t for _, t in self.harness.problems() if 'times' in t])
        self.connect('1', '1')
        self.assertIn('P1:1 → P2:1 is there 2 times.', [t for _, t in self.harness.problems()])


class TransferTests(HarnessBase):
    def file(self, data, name='loom.json'):
        import json

        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, json.dumps(data).encode('utf-8'), content_type='application/json')

    def test_a_harness_file_made_elsewhere_taken_in(self):
        from inventory.models import Family
        Family.objects.create(name='D-sub 9')
        data = {'kind': 'osmia harness', 'name': 'From a drawing',
                'connectors': [{'designator': 'J1', 'family': 'D-sub 9 / pin', 'side': 'left'}, {'designator': 'J2', 'family': 'Nope 3'}],
                'wires': [{'from': 'J1', 'from_pin': 1, 'to': 'J2', 'to_pin': '1', 'signal': '+24 V', 'colour': 'Red', 'gauge': '22',
                           'length': '450 mm', 'group': 'Power', 'set': 'P', 'set_type': 'twisted'},
                          {'from': 'J1', 'from_pin': '2', 'to': 'J2', 'to_pin': '2', 'colour': 'gray', 'set': 'P', 'set_type': 'Twisted'},
                          {'from': 'J1', 'from_pin': '1', 'to': 'J3', 'to_pin': '1', 'colour': 'pink'}],   # a splice, to a connector not listed
                'groups': [{'name': 'Power', 'length': 450, 'bundled': 100}]}
        response = self.client.post(reverse('harnesses:import'), {'setup': self.setup.pk, 'file': self.file(data)}, follow=True)
        made = Harness.objects.get(name='From a drawing')
        self.assertEqual(made.setup, self.setup)
        self.assertEqual([(e.designator, e.used_name, e.side) for e in made.ends.all()],
                         [('J1', 'D-sub 9 / pin', 'left'), ('J2', '', ''), ('J3', '', '')])
        first = made.wires.get(from_pin='1', to_end__designator='J2')
        self.assertEqual((first.colour, first.gauge, first.length, first.wire_group, first.set_type), ('red', '22 AWG', Decimal('450'), 'Power', 'Twisted'))
        self.assertEqual(made.wires.get(from_pin='2').wire_group, 'Power')   # with its set
        self.assertEqual(made.groups.get().bundled, Decimal('100'))
        self.assertContains(response, 'Nope 3')
        self.assertContains(response, 'pink')
        # out again and back in: the same harness
        out = self.client.get(made.get_absolute_url() + '?json=1').json()
        again, _ = __import__('harnesses.transfer', fromlist=['x']).import_harness(out, self.setup)
        self.assertEqual(again.snapshot()['wires'], made.snapshot()['wires'])

    def test_a_harness_in_no_setup(self):
        response = self.client.post(reverse('harnesses:import'), {'setup': '', 'file': self.file(
            {'name': 'Loose', 'wires': [{'from': 'J1', 'from_pin': '1', 'to': 'J2', 'to_pin': '1'}]})}, follow=True)
        loose = Harness.objects.get(name='Loose')
        self.assertIsNone(loose.setup)
        self.assertContains(response, 'Loose')                                   # its page
        listed = self.client.get(reverse('harnesses:list'), {'setup': 'none'})
        self.assertEqual(list(listed.context['harnesses']), [loose])
        self.assertContains(self.client.get(reverse('harnesses:brief', args=[loose.pk])), 'Loose')
        self.assertNotIn('setup', self.client.get(loose.get_absolute_url() + '?json=1').json())
        self.client.post(reverse('harnesses:new'), {'name': 'Bare', 'status': 'draft'})
        self.assertIsNone(Harness.objects.get(name='Bare').setup)

    def test_a_file_that_can_t_be_read_makes_nothing(self):
        before = Harness.objects.count()
        for data in ({'wires': [{'from': 'J1', 'from_pin': '1', 'to': 'J2'}]},   # no contact on one end
                     {'wires': [{'from': 'J1', 'from_pin': '1', 'to': 'J2', 'to_pin': '1', 'set': 'A', 'set_type': 'Coiled'}]},
                     {'something': 'else'}):
            self.client.post(reverse('harnesses:import'), {'setup': self.setup.pk, 'file': self.file(data)})
        self.client.post(reverse('harnesses:import'), {'file': self.file({'nothing': []})})
        self.assertEqual(Harness.objects.count(), before)
        self.assertContains(self.client.get(reverse('harnesses:format')), 'from_pin')


class BundleTests(HarnessBase):
    def draw(self, **fields):
        return self.client.post(reverse('harnesses:pinout_draw', args=[self.harness.pk]), fields)

    def test_the_bundle_its_marks_and_the_wires_lengths_from_it(self):
        from harnesses.models import HarnessMark
        self.connect('1', '1')
        self.connect('2', '2', wire_set='A', set_type='Shielded twisted')
        self.connect('3', '2')                                                    # P2:2 a splice
        p1, p2 = self.p1.pk, self.p2.pk
        self.assertEqual(self.draw(action='trunk', trunk='1000').json()['bundle']['trunk'], '1000')
        self.draw(action='end_place', end=p1, along='0', reach='')
        drawn = self.draw(action='end_place', end=p2, along='1000', reach='150').json()
        self.assertEqual([(e['along'], e['reach']) for e in drawn['ends']], [('0', ''), ('1000', '150')])
        line = {'a_end': p1, 'b_end': p2}                                         # P1 to P2: 1150 mm
        self.draw(action='mark_add', kind='tie', **{'from': '250'}, **line)
        self.draw(action='mark_add', kind='sleeve', definition='WIRE-22-RED', **{'from': '100', 'to': '600'}, **line)
        self.draw(action='mark_add', kind='strip', set='A', **{'from': '1120'}, **line)
        self.draw(action='mark_add', kind='splice', text='p2:2', **{'from': '900'}, **line)
        self.assertEqual([m.kind for m in self.harness.marks.all()], ['sleeve', 'tie', 'splice', 'strip'])
        self.assertEqual(self.harness.marks.get(kind='strip').start, Decimal('30'))   # 30 mm from P2, on its branch
        self.assertContains(self.client.get(self.harness.get_absolute_url()), 'id="bundle-view"')
        self.assertIn(Decimal('0.5'), [q for d, q in self.harness.parts_list() if d == self.wire])   # the sleeve's 500 mm
        self.assertIn('3 wires', self.draw(action='lengths').json()['said'])
        self.assertEqual(set(self.harness.wires.values_list('length', flat=True)), {Decimal('1150')})
        # kept in a version, and back as it was
        versions.save(self.harness, None)
        self.harness.marks.all().delete()
        self.assertTrue(versions.changed(self.harness))
        versions.restore(self.harness, self.harness.versions.get())
        self.assertEqual(self.harness.marks.count(), 4)
        self.assertEqual(HarnessEnd.objects.get(pk=p2).reach, Decimal('150'))
        # in a harness file and back
        from harnesses.transfer import import_harness
        out = self.client.get(self.harness.get_absolute_url() + '?json=1').json()
        again, _ = import_harness(out, None)
        self.assertEqual(again.snapshot()['bundle'], self.harness.snapshot()['bundle'])

    def test_a_splice_s_wires_changed_together_from_its_own_row(self):
        one, two = self.connect('1', '1'), Wire.objects.create(harness=self.harness, from_end=self.p2, from_pin='3', to_end=self.p1, to_pin='1')
        url, ids, contact = reverse('harnesses:pinout_draw', args=[self.harness.pk]), f'{one.pk},{two.pk}', f'{self.p1.pk}:1'
        self.draw(action='gauge', wire=ids, gauge='20')
        self.draw(action='colour', wire=ids, colour='red')
        self.draw(action='signal', wire=ids, signal='+24 V', contact=contact)   # each at its end on P1:1
        one.refresh_from_db(); two.refresh_from_db()
        self.assertEqual((one.gauge, one.colour, one.signal, one.to_signal), ('20 AWG', 'red', '+24 V', ''))
        self.assertEqual((two.gauge, two.colour, two.signal, two.to_signal), ('20 AWG', 'red', '', '+24 V'))
        self.assertEqual(self.draw(action='set', wire=ids, set='new:Straight').status_code, 400)   # one wire at a time
        self.draw(action='delete', wire=ids)
        self.assertFalse(self.harness.wires.exists())
        self.assertEqual(self.client.post(url, {'action': 'gauge', 'wire': ''}).status_code, 400)

    def test_marks_put_on_a_line_in_the_bundle_mode(self):
        self.connect('1', '1')
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        line = {'a_end': self.p1.pk, 'b_end': self.p2.pk}
        refused = self.client.post(url, {'action': 'mark_add', 'kind': 'tie', 'from': '10', **line})
        self.assertIn('places along the trunk', refused.json()['error'])           # no bundle yet
        HarnessEnd.objects.filter(pk=self.p1.pk).update(along=0, reach=100)
        HarnessEnd.objects.filter(pk=self.p2.pk).update(along=1000, reach=50)     # P1 to P2: 1150 mm
        drawn = self.client.post(url, {'action': 'mark_add', 'kind': 'tie', 'from': '600', **line}).json()
        self.assertEqual([(m['on'], m['start']) for m in drawn['bundle']['marks']], [(None, '500')])   # on the trunk
        self.client.post(url, {'action': 'mark_add', 'kind': 'sleeve', 'from': '50', 'to': '1120', **line})
        self.assertEqual(sorted((m.on_id or 0, m.start, m.end) for m in self.harness.marks.filter(kind='sleeve')),
                         sorted([(self.p1.pk, Decimal('50'), Decimal('100')), (0, Decimal('0'), Decimal('1000')),
                                 (self.p2.pk, Decimal('30'), Decimal('50'))]))                     # a piece on each part
        self.assertEqual(self.client.post(url, {'action': 'mark_add', 'kind': 'tie', 'from': '1200', **line}).status_code, 400)
        tie = self.harness.marks.get(kind='tie')
        self.client.post(url, {'action': 'mark_set', 'mark': tie.pk, 'kind': 'label', 'from': '20', 'text': 'X1', **line})
        self.assertEqual(list(self.harness.marks.filter(kind='label').values_list('on', 'start', 'text')), [(self.p1.pk, Decimal('20'), 'X1')])
        self.client.post(url, {'action': 'mark_delete', 'mark': self.harness.marks.get(kind='label').pk})
        self.assertFalse(self.harness.marks.filter(kind__in=['tie', 'label']).exists())

    def test_marks_that_can_t_be(self):
        self.connect('1', '1')
        p1, p2 = self.p1.pk, self.p2.pk
        self.draw(action='trunk', trunk='500')
        self.assertEqual(self.draw(action='end_place', end=p2, along='700').status_code, 400)            # past the trunk
        self.draw(action='end_place', end=p1, along='0')
        self.draw(action='end_place', end=p2, along='500')
        self.assertIn('break', self.draw(action='trunk', trunk='400').json()['error'])                    # P2 past it
        self.assertEqual(self.draw(action='trunk', trunk='x').status_code, 400)
        line = {'a_end': p1, 'b_end': p2}
        for bad in ({'kind': 'sleeve', 'from': '100', 'to': '50'},                                          # backwards
                    {'kind': 'tie', 'from': '600'},                                                         # past the end
                    {'kind': 'strip', 'from': '20'},                                                        # not on a branch
                    {'kind': 'splice', 'from': '20', 'text': 'P9:9'}):                                      # no such splice
            self.assertEqual(self.draw(action='mark_add', **bad, **line).status_code, 400)
        self.assertFalse(self.harness.marks.exists())


class BuildTests(HarnessBase):
    def test_built_with_a_checklist_and_its_definitions_from_stock(self):
        self.connect('1', '1', length=Decimal(500), definition=self.wire)
        self.connect('2', '3')
        v1 = versions.save(self.harness, self.ada)
        stock.add(self.plug, 5, self.shelf, self.ada)
        stock.add(self.wire, 10, self.shelf, self.ada)
        response = self.client.post(reverse('harnesses:unit_add', args=[self.harness.pk]),
                                    {'serial': 'H-0001-001', 'version': v1.pk, 'take_from': self.shelf.pk})
        unit = Record.objects.exclude(harness=None).get()
        self.assertRedirects(response, unit.get_absolute_url())
        self.assertEqual((unit.tag, unit.harness, unit.version, unit.status), ('H-0001-001', self.harness, 1, 'building'))
        self.assertEqual(self.plug.on_hand, 3)                                  # two connectors went into it
        self.assertEqual(self.wire.on_hand, Decimal('9.5'))
        checks = list(unit.checks.all())
        self.assertEqual([c.wire for c in checks], ['P1:1 → P2:1', 'P1:2 → P2:3'])
        response = self.client.post(reverse('records:checklist', args=[unit.pk]), {f'verified_{checks[0].pk}': 'on'}, follow=True)
        self.assertContains(response, 'place it before verifying it')
        self.client.post(reverse('records:checklist', args=[unit.pk]), {f'placed_{c.pk}': 'on' for c in checks} | {f'verified_{c.pk}': 'on' for c in checks})
        self.assertEqual(Record.objects.exclude(harness=None).get().status, 'available')

    def test_not_without_a_pinout_or_enough_stock(self):
        with self.assertRaisesMessage(ValidationError, 'has no pinout yet'):
            views.build(self.harness, 'X-1', None, self.ada)
        self.connect('1', '1')
        with self.assertRaisesMessage(ValidationError, 'There are only 0 pcs of DSUB-9-PLUG'):
            views.build(self.harness, 'X-1', None, self.ada, take_from=self.shelf)
        self.assertFalse(Record.objects.exclude(harness=None).exists())

    def test_versions_restore_the_pinout(self):
        self.connect('1', '1', signal='+24 V')
        versions.save(self.harness, self.ada)
        self.harness.wires.all().delete()
        self.harness.ends.filter(designator='P2').update(designator='X2')
        versions.restore(self.harness, self.harness.versions.get())
        self.assertEqual([str(w) for w in self.harness.wires.all()], ['P1:1 → P2:1'])
        self.assertFalse(versions.changed(self.harness))
        page = self.client.get(reverse('harnesses:harness', args=[self.harness.pk]), {'export': 1})
        self.assertEqual(page['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
