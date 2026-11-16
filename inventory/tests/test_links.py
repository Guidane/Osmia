"""Attributes that name other things: "interacts with" (pins mate with sockets, picked from the Sockets category, and
the sockets show it from their side) and links (a contact crimped with a tool: any item definition, by its number)."""
from django.urls import reverse

from inventory.models import Attribute, Category, ItemDefinition, DefinitionLink

from .test_inventory import Base


class LinkBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pins = Category.objects.create(name='Pins', parent=cls.connectors)
        cls.sockets = Category.objects.create(name='Sockets', parent=cls.connectors)
        cls.small = Category.objects.create(name='Small sockets', parent=cls.sockets)
        cls.mates = Attribute.objects.create(category=cls.pins, name='Mates with sockets', kind='interacts', target=cls.sockets,
                                             reverse_name='Mates with pins')
        cls.crimp = Attribute.objects.create(category=cls.pins, name='Crimped with', kind='link', reverse_name='Crimps')
        cls.spare = Attribute.objects.create(category=cls.pins, name='Replaced by', kind='link')
        cls.pin = ItemDefinition.objects.create(number='PIN-1', description='Pin', category=cls.pins)
        cls.socket = ItemDefinition.objects.create(number='SOCK-1', description='Socket', category=cls.sockets)
        cls.tiny = ItemDefinition.objects.create(number='SOCK-S', description='Small socket', category=cls.small)
        cls.tool = ItemDefinition.objects.create(number='CRIMP-1', description='Crimp tool', is_asset=True)

    def post(self, **attributes):
        data = {'number': 'PIN-1', 'unit': 'pcs', 'category': self.pins.pk, 'minimum': 0, 'reorder_quantity': 0, 'active': 'on',
                'attributes_of': self.pins.pk}
        for attribute, value in attributes.items():
            data[f'attr_{getattr(self, attribute).pk}'] = value
        return self.client.post(reverse('inventory:definition_edit', args=[self.pin.pk]), data)


class LinkTests(LinkBase):
    def test_interacts_with_picks_from_the_target_category_and_shows_both_ways(self):
        page = self.client.get(reverse('inventory:definition_edit', args=[self.pin.pk]))
        self.assertContains(page, 'SOCK-S Small socket')                       # from the categories under Sockets too
        self.assertNotContains(page, '>DSUB-9-PLUG')
        self.post(mates=[self.socket.pk, self.tiny.pk], crimp='crimp-1', spare='dsub-9-plug')
        self.assertEqual({l.target for l in DefinitionLink.objects.filter(attribute=self.mates)}, {self.socket, self.tiny})
        self.assertEqual(DefinitionLink.objects.get(attribute=self.crimp).target, self.tool)
        self.assertEqual(DefinitionLink.objects.get(attribute=self.spare).target, self.plug)
        page = self.client.get(reverse('inventory:definition', args=[self.socket.pk]))
        self.assertContains(page, '<dt>Mates with pins</dt>', html=False)      # the socket's side
        self.assertContains(page, 'PIN-1')
        page = self.client.get(reverse('inventory:definition', args=[self.tool.pk]))
        self.assertContains(page, 'Crimps')
        self.assertContains(page, 'PIN-1')
        page = self.client.get(reverse('inventory:definitions'), {'category': self.pins.pk})
        self.assertContains(page, 'SOCK-1, SOCK-S')

    def test_links_can_be_changed_and_wrong_numbers_are_refused(self):
        self.post(mates=[self.socket.pk])
        self.post(mates=[self.tiny.pk])
        self.assertEqual([l.target for l in DefinitionLink.objects.filter(attribute=self.mates)], [self.tiny])
        page = self.post(spare='NOPE-9')
        self.assertContains(page, 'There is no item definition NOPE-9.')
        page = self.post(mates=[self.plug.pk])                                  # not a socket
        self.assertContains(page, 'Select a valid choice')

    def test_what_a_link_attribute_needs_and_changing_its_type(self):
        url = reverse('inventory:attribute_new', args=[self.pins.pk])
        self.assertContains(self.client.post(url, {'name': 'Fits', 'kind': 'interacts'}), 'Pick the category')
        self.post(mates=[self.socket.pk])
        page = self.client.post(reverse('inventory:attribute_edit', args=[self.pins.pk, self.mates.pk]),
                                {'name': 'Mates with sockets', 'kind': 'text'})
        self.assertContains(page, 'Things link with it already')
        page = self.client.get(reverse('inventory:category', args=[self.pins.pk]))
        self.assertContains(page, 'the other side: Mates with pins')
