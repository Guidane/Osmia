"""Setups: each one its own devices and the harnesses between them (no tree: projects group them), a copy being a
setup of its own, what is wrong (a harness not plugged in, not into a connector of the device, two in one connector, a
pin the device connector hasn't, a signal not the pin's) and what building it needs. Which device connector a
harness's connector plugs into is the setup's."""
from decimal import Decimal

from django.urls import reverse

from devices.models import Connector, Device
from harnesses.models import HarnessEnd, HarnessItem, Wire
from harnesses.tests.test_harnesses import HarnessBase
from inventory import stock
from orders.models import Order
from setups import contents
from setups.models import Setup


class SetupBase(HarnessBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ctrl = contents.place(cls.setup, kind='device', device_id=cls.controller.pk, label='Controller')
        cls.load = contents.place(cls.setup, kind='device', device_id=cls.board.pk, label='Load board 1', x=300)
        cls.loom = contents.place(cls.setup, kind='harness', harness_id=cls.harness.pk,
                                  ends={str(cls.p1.pk): [cls.ctrl, cls.j1.pk], str(cls.p2.pk): [cls.load, cls.board_j1.pk]})

    def labels(self, setup):
        return sorted(r['label'] for r in contents.rows(setup).values() if r['kind'] == 'device')


class ContentTests(SetupBase):
    def test_a_harness_plugs_itself_in_where_one_connector_of_its_family_is_free(self):
        from harnesses.models import Harness
        from inventory.models import Family
        dsub = Family.objects.create(name='D-sub 9')
        Connector.objects.filter(pk=self.board_j1.pk).update(family=dsub)
        spare = Harness.objects.create(setup=self.setup, name='Spare')
        end = HarnessEnd.objects.create(harness=spare, designator='P1', family=dsub)
        self.assertEqual(contents.plug(self.setup, spare), {})                   # its one fitting connector is taken
        contents.place(self.setup, self.loom, ends={str(self.p1.pk): [self.ctrl, self.j1.pk]})
        self.assertEqual(contents.plug(self.setup, spare), {str(end.pk): [self.load, self.board_j1.pk]})
        wanted = contents.plug(self.setup, spare, {str(end.pk): f'{self.ctrl}:{self.j1.pk}'})   # picked in the list
        self.assertEqual(wanted, {str(end.pk): [self.ctrl, self.j1.pk]})

    def test_the_device_pins_a_harness_meets(self):
        self.assertEqual(contents.problems(self.setup), [])
        self.connect('6', '7', signal='CAN H')                                   # crossed over
        self.connect('9', '3')
        texts = [t for _, t in contents.problems(self.setup)]
        self.assertIn(f'{self.harness.number} P1:6 → P2:7: the wire carries "CAN H", LOAD-1 J1:7 is "CAN L".', texts)
        self.assertIn(f'CTRL-1 J1 has no pin 9 ({self.harness.number} P1:9 → P2:3).', texts)

    def test_a_copy_is_a_setup_of_its_own_in_the_same_project(self):
        from work.models import Project
        rack = Project.objects.create(name='Rack')
        Setup.objects.filter(pk=self.setup.pk).update(in_project=rack)
        self.setup.refresh_from_db()
        copy = contents.copy(self.setup, 'Field test', self.ada)
        self.assertEqual((copy.name, copy.in_project, self.labels(copy)), ('Field test', rack, ['Controller', 'Load board 1']))
        contents.place(copy, kind='device', device_id=self.board.pk, label='Load board 2')
        contents.place(self.setup, self.load, label='Renamed')                  # nothing flows between them
        self.assertEqual(self.labels(copy), ['Controller', 'Load board 1', 'Load board 2'])
        self.assertEqual(self.labels(self.setup), ['Controller', 'Renamed'])
        self.assertEqual(contents.rows(copy)[self.loom]['harness_id'], self.harness.pk)   # the same harness, in both

    def test_taking_a_device_away_unplugs_its_harness(self):
        contents.take_away(self.setup, self.load)
        self.assertEqual(self.labels(self.setup), ['Controller'])
        self.assertIn(f'{self.harness.number} P2 is not plugged in.', [t for _, t in contents.problems(self.setup)])

    def test_swapping_a_device_and_plugging_wrongly(self):
        other = Device.objects.create(number='LOAD-2', name='Bigger load board')
        Connector.objects.create(device=other, designator='J1')
        contents.place(self.setup, self.load, device_id=other.pk)
        self.assertIn(f'{self.harness.number} P2 is plugged into Load board 1, but not into one of its connectors.',
                      [t for _, t in contents.problems(self.setup)])
        contents.place(self.setup, self.loom, ends={str(self.p1.pk): [self.ctrl, self.j1.pk], str(self.p2.pk): [self.ctrl, self.board_j1.pk]})
        self.assertTrue(any('P2 is plugged into Controller, but not' in t for _, t in contents.problems(self.setup)))


class PageTests(SetupBase):
    def test_setups_live_at_setups(self):
        self.assertEqual(self.setup.get_absolute_url(), f'/setups/{self.setup.pk}/')

    def test_the_setup_page_and_its_changes(self):
        url = reverse('setups:change', args=[self.setup.pk])
        self.client.post(url, {'action': 'add_device', 'device': self.board.pk})
        self.assertIn('LOAD-1 2', self.labels(self.setup))                      # a name of its own
        response = self.client.post(url, {'action': 'move', 'key': self.ctrl, 'x': '120', 'y': '40'})
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(contents.rows(self.setup)[self.ctrl]['x'], 120)
        page = self.client.get(self.setup.get_absolute_url())
        self.assertContains(page, 'diagram-data')
        self.assertNotContains(page, 'onfiguration')
        response = self.client.post(reverse('setups:copy', args=[self.setup.pk]), {'name': 'Rev C'}, follow=True)
        copy = Setup.objects.get(name='Rev C')
        self.assertRedirects(response, copy.get_absolute_url())
        self.assertEqual(self.labels(copy), self.labels(self.setup))

    def test_the_list_has_each_setup_with_what_is_in_it(self):
        contents.copy(self.setup, 'Field test')
        page = self.client.get(reverse('setups:list'))
        self.assertEqual([(s.name, s.n_devices, s.n_harnesses) for s in page.context['setups']],
                         [(self.setup.name, 2, 1), ('Field test', 2, 1)])

    def test_what_it_needs_and_ordering_what_is_missing(self):
        Wire.objects.create(harness=self.harness, from_end=self.p1, from_pin='1', to_end=self.p2, to_pin='1', length=Decimal(400), definition=self.wire)
        HarnessItem.objects.create(harness=self.harness, definition=self.plug, quantity=1)
        stock.add(self.plug, 1, self.shelf, self.ada)
        devices, harnesses, definitions = contents.needs(self.setup)
        self.assertEqual([(d.number, n) for d, n in devices], [('CTRL-1', 1), ('LOAD-1', 1)])
        needed = {p.number: (q, have) for p, q, have, _ in definitions}
        self.assertEqual(needed['DSUB-9-PLUG'], (3, 1))                         # two ends and one extra
        self.assertEqual(needed['WIRE-22-RED'][0], Decimal('0.4'))
        self.client.post(reverse('setups:needs', args=[self.setup.pk]) + '?count=2')
        line = Order.objects.get().lines.get()
        self.assertEqual((line.definition, line.quantity), (self.plug, 5))           # 6 needed, 1 on hand
        response = self.client.get(reverse('setups:needs', args=[self.setup.pk]), {'export': 1})
        self.assertEqual(response.status_code, 200)

    def test_two_harnesses_in_one_connector(self):
        from harnesses.models import Harness
        other = Harness.objects.create(setup=self.setup, name='Spare loom')
        end = HarnessEnd.objects.create(harness=other, designator='P1')
        contents.place(self.setup, kind='harness', harness_id=other.pk, ends={str(end.pk): [self.ctrl, self.j1.pk]})
        self.assertTrue(any('both plug into Controller J1' in t for _, t in contents.problems(self.setup)))

    def test_a_harness_of_another_setup_of_the_project_can_be_placed(self):
        from harnesses.models import Harness
        from work.models import Project
        rack = Project.objects.create(name='Rack')
        other = Setup.objects.create(name='Bench', in_project=rack)
        Setup.objects.filter(pk=self.setup.pk).update(in_project=rack)
        stranger = Harness.objects.create(setup=Setup.objects.create(name='Elsewhere'), name='Not ours')
        change = reverse('setups:change', args=[other.pk])
        self.client.post(change, {'action': 'add_harness', 'harness': self.harness.pk})
        self.client.post(change, {'action': 'add_harness', 'harness': stranger.pk})
        self.assertEqual([r['harness_id'] for r in contents.rows(other).values()], [self.harness.pk])


class ConnectTests(SetupBase):
    def test_a_harness_made_between_two_connectors(self):
        self.j1.pins.filter(number__in=['6', '7']).update(wire_set='CAN', set_type='Twisted')
        response = self.client.post(reverse('setups:change', args=[self.setup.pk]), {
            'action': 'connect', 'name': 'Controller J1 to board J1',
            'a': self.ctrl, 'a_connector': self.j1.pk, 'b': self.load, 'b_connector': self.board_j1.pk,
            'wire': ['["1", "1"]', '["2", "3"]', '["6", "2"]']}, follow=True)
        harness = self.setup.harnesses.get(name='Controller J1 to board J1')
        self.assertContains(response, f'{harness} is made, with 3 wires.')
        p1, p2 = harness.ends.all()
        self.assertEqual((p1.designator, p2.designator), ('P1', 'P2'))
        self.assertEqual(sorted((w.from_pin, w.to_pin, w.signal, w.wire_set, w.set_type) for w in harness.wires.all()),
                         [('1', '1', '+24 V', '', 'Straight'), ('2', '3', '0 V', '', 'Straight'), ('6', '2', 'CAN H', 'CAN', 'Twisted')])
        row = next(r for r in contents.rows(self.setup).values() if r['harness_id'] == harness.pk)
        self.assertEqual(row['ends'], {str(p1.pk): [self.ctrl, self.j1.pk], str(p2.pk): [self.load, self.board_j1.pk]})   # placed, plugged in

    def test_what_can_t_be_connected(self):
        def connect(**post):
            return self.client.post(reverse('setups:change', args=[self.setup.pk]), {
                'action': 'connect', 'name': 'x', 'a': self.ctrl, 'a_connector': self.j1.pk, **post}, follow=True)
        self.assertContains(connect(b=self.ctrl, b_connector=self.j1.pk), 'Pick two different connectors.')
        self.assertContains(connect(b=self.ctrl, b_connector=self.board_j1.pk), 'That connector is not in this setup.')
        self.assertContains(connect(b=self.load, b_connector=self.board_j1.pk, wire='["99", "1"]'), 'There is no pin 99 on that connector.')
        self.assertFalse(self.setup.harnesses.filter(name='x').exists())


class HarnessRequestTests(SetupBase):
    def ask(self, **post):
        return self.client.post(reverse('setups:change', args=[self.setup.pk]), {
            'action': 'request_harness', 'a': self.ctrl, 'b': self.load, **post}, follow=True)

    def test_asked_made_between_the_two_and_who_asked_hears(self):
        from django.contrib.auth import get_user_model
        from setups.models import HarnessRequest
        from web.models import Notification
        sam = get_user_model().objects.create_user('sam', password='pw')
        bob = get_user_model().objects.create_user('bob', password='pw')
        self.client.force_login(sam)
        self.assertContains(self.ask(request=''), 'Say what is needed.')
        self.assertContains(self.ask(request='Sensor cable, 2 m', b='nope'), 'Pick two devices of this setup.')
        page = self.ask(request='Sensor cable, 2 m', ask=bob.pk)
        self.assertContains(page, 'Controller ⇄ Load board 1')
        wanted = HarnessRequest.objects.get()
        self.assertTrue(Notification.objects.filter(user=bob, message__contains='harness between Controller and Load board 1').exists())
        self.assertIn({'id': wanted.pk, 'a': self.ctrl, 'b': self.load, 'text': 'Sensor cable, 2 m'},
                      page.context['diagram']['requests'])
        self.client.force_login(self.ada)
        self.assertContains(self.client.get('/'), '1</b> harness asked for', html=False)
        self.client.post(reverse('setups:change', args=[self.setup.pk]), {    # drawn between the two: made
            'action': 'connect', 'name': 'Sensor cable', 'a': self.load, 'a_connector': self.board_j1.pk,
            'b': self.ctrl, 'b_connector': self.j1.pk})
        wanted.refresh_from_db()
        self.assertEqual((wanted.status, wanted.harness.name), ('done', 'Sensor cable'))
        self.assertTrue(Notification.objects.filter(user=sam, message__contains='is made').exists())
        self.assertNotContains(self.client.get('/'), 'harness asked for')

    def test_done_or_cancelled_by_hand(self):
        from setups.models import HarnessRequest
        self.ask(request='A loom')
        self.ask(request='Another loom')
        first, second = HarnessRequest.objects.order_by('pk')
        change = reverse('setups:change', args=[self.setup.pk])
        self.client.post(change, {'action': 'request_done', 'request_id': first.pk, 'harness': self.harness.pk})
        self.client.post(change, {'action': 'request_cancel', 'request_id': second.pk})
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.status, first.harness, second.status), ('done', self.harness, 'cancelled'))
        response = self.client.post(change, {'action': 'request_cancel', 'request_id': first.pk}, follow=True)
        self.assertContains(response, 'That request is closed already.')
