"""Changing something shows what it is: a page that can start something new with a value from the address (?parent=,
?setup=, ...) doesn't put that value over what an existing record has."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, User
from budgets.models import Budget
from harnesses.models import Harness
from inventory.models import Category, Location, ItemDefinition
from setups.models import Setup
from assets.models import Asset


class EditFormTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_superuser('ada', 'ada@example.com', 'pw')
        self.bob = User.objects.create_user('bob', first_name='Bob')
        self.client.force_login(self.ada)

    def selected(self, url, value):
        self.assertContains(self.client.get(url), f'<option value="{value}" selected>', html=False)

    def test_each_edit_page_shows_the_record_s_own_values(self):
        store = Location.objects.create(name='Store')
        shelf = Location.objects.create(name='Shelf', parent=store)
        self.selected(reverse('inventory:location_edit', args=[shelf.pk]), store.pk)
        wire = Category.objects.create(name='Wire')
        definition = ItemDefinition.objects.create(number='W-1', category=wire)
        self.selected(reverse('inventory:definition_edit', args=[definition.pk]), wire.pk)
        engineering = Department.objects.create(name='Engineering')
        test = Department.objects.create(name='Test', parent=engineering)
        self.selected(reverse('accounts:department_edit', args=[test.pk]), engineering.pk)
        self.bob.department = test
        self.bob.save()
        self.selected(reverse('accounts:user_edit', args=[self.bob.pk]), test.pk)
        setup = Setup.objects.create(name='Rack', owner=self.bob)
        self.selected(reverse('setups:edit', args=[setup.pk]), self.bob.pk)       # not who is changing it
        year = Budget.objects.create(name='2026', amount=1)
        budget = Budget.objects.create(name='Rack', parent=year, setup=setup, owner=self.bob, amount=1)
        self.selected(reverse('budgets:edit', args=[budget.pk]), self.bob.pk)
        self.selected(reverse('budgets:edit', args=[budget.pk]), year.pk)
        harness = Harness.objects.create(setup=setup, name='Loom')
        self.selected(reverse('harnesses:edit', args=[harness.pk]), setup.pk)
        tools = Category.objects.create(name='Tools', kind='assets')
        tool = Asset.objects.create(number='T-1', name='Crimper', category=tools, location=shelf)
        self.selected(reverse('assets:edit', args=[tool.pk]), tools.pk)
        self.selected(reverse('assets:edit', args=[tool.pk]), shelf.pk)

    def test_something_new_starts_from_the_address(self):
        store = Location.objects.create(name='Store')
        self.selected(reverse('inventory:location_new') + f'?parent={store.pk}', store.pk)
