"""Devices: connectors made with their pins, pins edited as a table, versions saved and restored (what harnesses
plug into keeps its connector), a unit (an asset) made with it, deleting one, Excel."""
from django.core.exceptions import ValidationError
from django.urls import reverse

from devices.models import Connector, Device, Pin
from inventory.tests.test_inventory import Base
from web import versions


class DeviceBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.controller = Device.objects.create(number='CTRL-1', name='Controller')
        cls.j1 = Connector.objects.create(device=cls.controller, designator='J1', name='Bus', definition=cls.plug)
        for number, signal in (('1', '+24 V'), ('2', '0 V'), ('6', 'CAN H'), ('7', 'CAN L')):
            Pin.objects.create(connector=cls.j1, number=number, signal=signal)


class DeviceTests(DeviceBase):
    def test_a_connector_with_its_pins_and_editing_them(self):
        self.client.post(reverse('devices:connector_new', args=[self.controller.pk]), {'designator': 'J2', 'name': 'Power', 'pins': '3'})
        j2 = Connector.objects.get(designator='J2')
        self.assertEqual([p.number for p in j2.ordered_pins()], ['1', '2', '3'])
        page = self.client.post(reverse('devices:connector_new', args=[self.controller.pk]), {'designator': 'j2'})
        self.assertContains(page, 'already has a j2')
        pins = {p.number: p for p in j2.pins.all()}
        self.client.post(reverse('devices:pins', args=[self.controller.pk, j2.pk]), {
            f'number_{pins["1"].pk}': '1', f'signal_{pins["1"].pk}': '+24 V',
            f'set_{pins["1"].pk}': 'PWR', f'set_type_{pins["1"].pk}': 'Twisted',
            f'number_{pins["2"].pk}': '2', f'signal_{pins["2"].pk}': '0 V', f'set_{pins["2"].pk}': 'PWR', f'set_type_{pins["2"].pk}': 'Twisted',
            f'gone_{pins["3"].pk}': 'on',
            'new': '2', 'number_new0': '10', 'signal_new0': 'PE', 'set_type_new0': 'nonsense', 'number_new1': ''})
        self.assertEqual([(p.number, p.signal, p.wire_set, p.set_type) for p in j2.ordered_pins()],
                         [('1', '+24 V', 'PWR', 'Twisted'), ('2', '0 V', 'PWR', 'Twisted'), ('10', 'PE', '', 'Straight')])
        url = reverse('devices:device', args=[self.controller.pk])
        page = self.client.get(url)                                       # the device: its connectors in the middle
        self.assertContains(page, f'?connector={self.j1.pk}')
        self.assertNotContains(page, 'CAN H')
        self.assertContains(self.client.get(f'{url}?connector={self.j1.pk}'), 'CAN H')    # a connector: its pins
        brief = self.client.get(reverse('devices:connector_brief', args=[self.controller.pk, self.j1.pk]))
        self.assertContains(brief, 'data-face')
        self.assertContains(self.client.get(f'{url}?c={self.j1.pk}'), 'data-connector-brief')

    def test_a_set_has_one_type(self):
        pins = {p.number: p for p in self.j1.pins.all()}
        self.j1.pins.filter(number__in=['6', '7']).update(wire_set='CAN', set_type='Twisted')
        post = {f'number_{p.pk}': p.number for p in pins.values()}
        post.update({f'set_{pins["6"].pk}': 'CAN', f'set_type_{pins["6"].pk}': 'Twisted',
                     f'set_{pins["7"].pk}': 'CAN', f'set_type_{pins["7"].pk}': 'Shielded twisted',      # changed on one
                     f'set_{pins["1"].pk}': 'CAN', f'set_type_{pins["1"].pk}': 'Straight',              # put into it
                     'new': '1', 'number_new0': '8', 'set_new0': '+'})
        self.client.post(reverse('devices:pins', args=[self.controller.pk, self.j1.pk]), post)
        self.assertEqual({p.number: (p.wire_set, p.set_type) for p in self.j1.pins.all()},
                         {'1': ('CAN', 'Shielded twisted'), '2': ('', 'Straight'), '6': ('CAN', 'Shielded twisted'),
                          '7': ('CAN', 'Shielded twisted'), '8': ('', 'Straight')})

    def test_a_set_is_in_one_group(self):
        pins = {p.number: p for p in self.j1.pins.all()}
        self.j1.pins.filter(number__in=['6', '7']).update(wire_set='1', set_type='Twisted', wire_group='Channel 1')
        post = {f'number_{p.pk}': p.number for p in pins.values()}
        post.update({f'set_{pins["6"].pk}': '1', f'set_type_{pins["6"].pk}': 'Twisted', f'group_{pins["6"].pk}': 'Channel 1',
                     f'set_{pins["7"].pk}': '1', f'set_type_{pins["7"].pk}': 'Twisted', f'group_{pins["7"].pk}': 'Channel 2',   # changed on one
                     f'group_{pins["1"].pk}': 'Channel 2'})                                                                  # in no set: its own
        self.client.post(reverse('devices:pins', args=[self.controller.pk, self.j1.pk]), post)
        self.assertEqual({p.number: p.wire_group for p in self.j1.pins.all()}, {'1': 'Channel 2', '2': '', '6': 'Channel 2', '7': 'Channel 2'})
        self.assertContains(self.client.get(reverse('devices:pins', args=[self.controller.pk, self.j1.pk])), '<option value="Channel 2">', html=False)
        versions.save(self.controller, self.ada)
        self.assertFalse(versions.changed(self.controller))
        self.j1.pins.filter(number='1').update(wire_group='')
        self.assertTrue(versions.changed(self.controller))

    def test_a_connector_s_family_picked_in_a_popup(self):
        from inventory.faces import start
        from inventory.models import Branch, Family
        dsub = Family.objects.create(name='D-sub 9', face=start('staggered', 9))
        Branch.objects.create(family=dsub, name='socket', contacts='socket')
        url = reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk])
        form = self.client.get(url)
        self.assertContains(form, 'family-finder')
        self.assertContains(form, '"D-sub 9 / socket"')                                     # its genders, to pick
        self.client.post(url, {'designator': 'J1', 'name': 'Bus', 'used': 'D-sub 9 / socket'})
        self.j1.refresh_from_db()
        self.assertEqual(str(self.j1.used), 'D-sub 9 / socket')
        self.assertContains(form, '"D-sub 9 / pin"')                                       # a side it has none of yet
        self.client.post(reverse('devices:connector_new', args=[self.controller.pk]), {'designator': 'J5', 'used': 'D-sub 9 / pin'})
        made = self.controller.connectors.get(designator='J5').used
        self.assertEqual((str(made), made.contacts), ('D-sub 9 / pin', 'pin'))              # made when picked

    def test_connectors_copied_from_another_device(self):
        other = Device.objects.create(number='CTRL-2', name='Other controller')
        Connector.objects.create(device=other, designator='J1', name='Mine')
        self.j1.pins.filter(number='6').update(wire_set='CAN', set_type='Twisted')
        page = self.client.get(reverse('devices:connectors_copy', args=[other.pk]))
        self.assertContains(page, 'CTRL-1')
        self.assertContains(page, '4 pins')
        self.client.post(reverse('devices:connectors_copy', args=[other.pk]), {'connector': [self.j1.pk]})
        copied = other.connectors.get(designator='J2')                          # J1 was taken
        self.assertEqual((copied.name, copied.definition), ('Bus', self.plug))
        self.assertEqual(sorted((p.number, p.signal, p.wire_set) for p in copied.pins.all()),
                         [('1', '+24 V', ''), ('2', '0 V', ''), ('6', 'CAN H', 'CAN'), ('7', 'CAN L', '')])
        self.assertEqual(self.j1.pins.count(), 4)                                 # the original stays

    def test_versions_saved_and_restored(self):
        v1 = versions.save(self.controller, self.ada, 'first')
        self.assertEqual((v1.number, self.controller.version), (1, 1))
        with self.assertRaisesMessage(ValidationError, 'Nothing changed since v1.'):
            versions.save(self.controller, self.ada)
        Pin.objects.filter(connector=self.j1, number='6').update(signal='CAN HIGH')
        Pin.objects.filter(connector=self.j1, number='7').delete()
        Connector.objects.create(device=self.controller, designator='J9')
        self.assertTrue(versions.changed(self.controller))
        self.client.post(reverse('devices:restore', args=[self.controller.pk, 1]))
        self.assertFalse(versions.changed(self.controller))
        self.assertEqual(Connector.objects.get(pk=self.j1.pk).pins.get(number='6').signal, 'CAN H')   # the same connector
        self.assertFalse(Connector.objects.filter(designator='J9').exists())
        page = self.client.get(reverse('devices:version', args=[self.controller.pk, 1]))
        self.assertContains(page, 'CAN L')

    def test_a_version_keeps_the_device_itself_too(self):
        from devices.models import DeviceVersion
        Device.objects.filter(pk=self.controller.pk).update(manufacturer='Acme', colour='#ff0000', origin='external')
        self.controller.refresh_from_db()
        versions.save(self.controller, self.ada)
        Device.objects.filter(pk=self.controller.pk).update(name='Rack controller', colour='#00ff00', origin='in_house')
        self.controller.refresh_from_db()
        self.assertTrue(versions.changed(self.controller))
        self.assertContains(self.client.get(reverse('devices:version', args=[self.controller.pk, 1])), 'Acme')
        self.client.post(reverse('devices:restore', args=[self.controller.pk, 1]))
        self.controller.refresh_from_db()
        self.assertEqual((self.controller.name, self.controller.colour, self.controller.origin), ('Controller', '#ff0000', 'external'))
        old = DeviceVersion.objects.get(device=self.controller, number=1)       # one saved before colour and origin were kept
        old.data = {k: v for k, v in old.data.items() if k not in ('colour', 'origin')}
        old.save()
        self.assertFalse(versions.changed(self.controller))

    def test_a_unit_made_with_the_device_and_deleting_it_from_the_list(self):
        from records.models import Record
        versions.save(self.controller, self.ada)
        page = self.client.get(reverse('devices:device', args=[self.controller.pk]))
        self.assertNotContains(page, reverse('records:new'))                        # no "Add one" any more
        base = {'number': 'CTRL-1', 'name': 'Controller', 'origin': 'in_house', 'colour': '#3b7dd8'}
        self.client.post(reverse('devices:edit', args=[self.controller.pk]), dict(base, make_asset='on'))
        unit = Record.objects.get(tag='CTRL-1-001')
        self.assertEqual((unit.device, unit.version, unit.definition), (self.controller, 1, None))
        self.assertContains(self.client.get(reverse('devices:device', args=[self.controller.pk]) + '?show=assets'), 'CTRL-1-001')
        self.client.post(reverse('devices:edit', args=[self.controller.pk]), dict(base, make_asset='on'))
        self.client.post(reverse('devices:edit', args=[self.controller.pk]), base)                  # not ticked: none
        self.assertEqual(list(self.controller.records.values_list('tag', flat=True)), ['CTRL-1-001', 'CTRL-1-002'])
        self.client.post(reverse('devices:new'), {'number': 'NEW-1', 'name': 'New one', 'origin': 'external', 'colour': '#000000',
                                                  'make_asset': 'on'})
        self.assertEqual(Record.objects.get(tag='NEW-1-001').device.number, 'NEW-1')
        self.assertContains(self.client.get(reverse('devices:list')), reverse('devices:delete', args=[self.controller.pk]))
        self.client.post(reverse('devices:delete', args=[self.controller.pk]))
        self.assertTrue(Device.objects.filter(pk=self.controller.pk).exists())      # not while there are records of it
        Record.objects.filter(device=self.controller).delete()
        self.client.post(reverse('devices:delete', args=[self.controller.pk]))
        self.assertFalse(Device.objects.filter(pk=self.controller.pk).exists())
        self.assertFalse(Connector.objects.filter(pk=self.j1.pk).exists())

    def test_a_device_in_a_setup_is_not_deleted(self):
        from setups.models import Placement, Setup
        setup = Setup.objects.create(code='WD-1', name='Rack')
        Placement.objects.create(setup=setup, key='d1', kind='device', device=self.controller)
        self.client.post(reverse('devices:delete', args=[self.controller.pk]))
        self.assertTrue(Device.objects.filter(pk=self.controller.pk).exists())

    def test_excel(self):
        from io import BytesIO

        from openpyxl import load_workbook
        response = self.client.get(reverse('devices:list'), {'export': 1})
        book = load_workbook(BytesIO(response.content))
        rows = list(book['Pins'].values)
        self.assertEqual(rows[0][:5], ('Device', 'Connector', 'Connector name', 'Connector item definition', 'Pin'))
        self.assertIn(('CTRL-1', 'J1', 'Bus', 'DSUB-9-PLUG', '6', 'CAN H', None, None, None, None), rows)


class DeviceTransferTests(DeviceBase):
    def file(self, data):
        import json

        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('device.json', json.dumps(data).encode('utf-8'), content_type='application/json')

    def test_a_device_file_made_elsewhere_taken_in_and_out_again(self):
        from inventory.models import Family
        Family.objects.create(name='D-sub 9')
        data = {'kind': 'osmia device', 'number': 'LOAD-2', 'name': 'Load board', 'origin': 'bought', 'manufacturer': 'Acme',
                'connectors': [{'designator': 'J1', 'name': 'Bus in', 'family': 'D-sub 9 / socket', 'side': 'Left',
                                'pins': [{'number': 1, 'signal': '+24 V'}, {'number': '2', 'signal': 'CAN H', 'set': 'CAN', 'set_type': 'twisted', 'group': 'Bus'},
                                         {'number': '7', 'signal': 'CAN L', 'set': 'CAN', 'set_type': 'Twisted', 'group': 'Bus'}]},
                               {'designator': 'X2', 'family': 'Nope 4', 'pins': ['1', '2']}]}
        response = self.client.post(reverse('devices:import'), {'file': self.file(data)}, follow=True)
        made = Device.objects.get(number='LOAD-2')
        self.assertEqual((made.origin, made.manufacturer), ('external', 'Acme'))
        j1, x2 = made.connectors.all()
        self.assertEqual((j1.used_name, j1.side, x2.used_name), ('D-sub 9 / socket', 'left', ''))
        self.assertEqual([(p.number, p.signal, p.wire_set, p.set_type, p.wire_group) for p in j1.ordered_pins()],
                         [('1', '+24 V', '', 'Straight', ''), ('2', 'CAN H', 'CAN', 'Twisted', 'Bus'), ('7', 'CAN L', 'CAN', 'Twisted', 'Bus')])
        self.assertEqual([p.number for p in x2.ordered_pins()], ['1', '2'])
        self.assertContains(response, 'Nope 4')
        out = self.client.get(made.get_absolute_url() + '?json=1').json()
        made.delete()
        from devices.transfer import export_device, import_device
        again, _ = import_device(out)
        self.assertEqual(export_device(again), out)   # the same device again

    def test_a_file_that_can_t_be_read_makes_nothing(self):
        before = Device.objects.count()
        for data in ({'number': 'CTRL-1', 'name': 'Taken'},
                     {'number': 'N-1', 'name': 'x', 'connectors': [{'designator': 'J1', 'pins': [{'number': '1'}, {'number': '1'}]}]},
                     {'number': 'N-2', 'name': 'x', 'connectors': [{'designator': 'J1', 'pins': [
                         {'number': '1', 'set': 'A', 'set_type': 'Twisted'}, {'number': '2', 'set': 'A', 'set_type': 'Shielded'}]}]},
                     {'name': 'no number'}, ['not', 'a', 'device']):
            self.client.post(reverse('devices:import'), {'file': self.file(data)})
        self.assertEqual(Device.objects.count(), before)
        self.assertContains(self.client.get(reverse('devices:format')), 'set_type')
