"""Item definitions and budgets from Excel: what ⬇ Excel makes, edited and sent back (changed, made); a column left
out left as it is; categories and vendors made; a sheet with a wrong row refused whole."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from budgets.models import Budget
from inventory.models import Category, ItemDefinition, Vendor

from .test_inventory import Base


def book(title, rows):
    """An .xlsx file of one sheet ``title``: ``rows``, the first its headers."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    out = BytesIO()
    wb.save(out)
    return SimpleUploadedFile('sheet.xlsx', out.getvalue())


def as_sent(content):
    """A downloaded .xlsx, as a file to send back."""
    return SimpleUploadedFile('export.xlsx', content)


def edited(content, title, change):
    """A downloaded .xlsx with ``change(rows)`` made to its sheet ``title`` (rows: lists, the first the headers)."""
    wb = load_workbook(BytesIO(content))
    sheet = wb[title]
    rows = [list(r) for r in sheet.values]
    change(rows)
    sheet.delete_rows(1, sheet.max_row)
    for row in rows:
        sheet.append(row)
    out = BytesIO()
    wb.save(out)
    return as_sent(out.getvalue())


class DefinitionImportTests(Base):
    def send(self, sent):
        return self.client.post(reverse('inventory:definitions_import'), {'file': sent}, follow=True)

    def test_exported_edited_and_imported_back(self):
        content = self.client.get(reverse('inventory:definitions'), {'export': 1}).content
        before = {d.number: (d.description, d.category_id, d.vendor_id, d.price, d.minimum, d.unit) for d in ItemDefinition.objects.all()}
        page = self.send(as_sent(content))                                      # as it is: nothing changes
        self.assertContains(page, '0 item definitions made, 2 changed')
        self.assertEqual(before, {d.number: (d.description, d.category_id, d.vendor_id, d.price, d.minimum, d.unit) for d in ItemDefinition.objects.all()})

        def change(rows):
            head = rows[0]
            plug = next(r for r in rows if r[0] == 'DSUB-9-PLUG')
            plug[head.index('Description')] = 'D-sub 9 plug, gold'
            plug[head.index('Last price')] = 3.1
            rows.append(['NUT-M3', 'Physical', 'Nut M3', 'Hardware / Nuts', '', '', 'pieces', 'Bolt & Co', '', '0,05', 100, 999, 'yes', 500, 'no', '', 'A box of 1000'])
        page = self.send(edited(content, 'Item definitions', change))
        self.assertContains(page, '1 item definitions made, 2 changed')
        self.assertContains(page, 'Category Hardware / Nuts was made.')
        self.plug.refresh_from_db()
        self.assertEqual((self.plug.description, self.plug.price, self.plug.category, self.plug.vendor), ('D-sub 9 plug, gold', Decimal('3.1'), self.dsub, self.acme))
        nut = ItemDefinition.objects.get(number='NUT-M3')
        self.assertEqual((nut.category.path, nut.vendor.name, nut.price, nut.minimum, nut.reorder_quantity, nut.unit, nut.notes),
                         ('Hardware / Nuts', 'Bolt & Co', Decimal('0.05'), 100, 500, 'pcs', 'A box of 1000'))

    def test_only_the_columns_in_the_sheet(self):
        self.send(book('Item definitions', [['item number ', 'Description'], ['dsub-9-plug', 'Plug']]))   # (its number in any case)
        self.plug.refresh_from_db()
        self.assertEqual((self.plug.description, self.plug.vendor, self.plug.price, self.plug.category), ('Plug', self.acme, Decimal('2.50'), self.dsub))
        self.assertEqual(ItemDefinition.objects.count(), 2)

    def test_a_wrong_row_and_nothing_is_imported(self):
        page = self.send(book('Item definitions', [['Item number', 'Unit', 'Last price', 'Category'],
                                                   ['NEW-1', 'pcs', 1, 'New / Kind'], ['NEW-2', 'barrels', 1, ''],
                                                   ['NEW-3', 'pcs', 'cheap', ''], ['', 'pcs', 1, ''], ['NEW-1', 'pcs', 1, '']]))
        for said in ('Nothing was imported.', 'Row 3: &quot;barrels&quot; is not a unit', 'Row 4: the last price &quot;cheap&quot; is not a number.',
                     'Row 5: it has no item number.', 'Row 6: item number NEW-1 is in row 2 already.'):
            self.assertContains(page, said)
        self.assertFalse(ItemDefinition.objects.filter(number__startswith='NEW').exists())
        self.assertFalse(Category.objects.filter(name='New').exists())
        self.assertContains(self.send(book('Sheet', [['Number', 'Name']])), 'There are no item definitions')
        self.assertContains(self.send(book('Sheet', [['Number', 'Name'], ['X', 'Y']])), 'has no &quot;Item number&quot; column')
        self.assertContains(self.send(SimpleUploadedFile('notes.xlsx', b'not a workbook')), 'is not an Excel file')
        self.assertEqual(Vendor.objects.count(), 1)


class BudgetImportTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year = Budget.objects.create(number='FY26', name='2026', amount=1000, owner=cls.ada)
        cls.test = Budget.objects.create(number='FY26-TE', name='Test equipment', parent=cls.year, amount=100, owner=cls.ada)

    def send(self, sent):
        return self.client.post(reverse('budgets:import'), {'file': sent}, follow=True)

    def test_exported_edited_and_imported_back(self):
        content = self.client.get(reverse('budgets:list'), {'export': 1}).content
        page = self.send(as_sent(content))
        self.assertContains(page, '0 budgets made, 2 changed')
        self.assertEqual(Budget.objects.get(pk=self.test.pk).parent, self.year)

        def change(rows):
            head = rows[0]
            te = next(r for r in rows if r[0] == 'FY26-TE')
            te[head.index('Amount')] = 250
            te[head.index('Ends')] = '2026-12-31'
            row = [''] * len(head)
            for k, v in (('Number', 'FY26-TR'), ('Name', 'Travel'), ('Part of', 'FY26 2026'), ('Owner', 'ada'), ('Amount', '80,5'), ('Active', 'no')):
                row[head.index(k)] = v
            rows.append(row)
        page = self.send(edited(content, 'Budgets', change))
        self.assertContains(page, '1 budgets made, 2 changed')
        self.assertEqual((Budget.objects.get(pk=self.test.pk).amount, Budget.objects.get(pk=self.test.pk).ends_on), (250, date(2026, 12, 31)))
        travel = Budget.objects.get(number='FY26-TR')
        self.assertEqual((travel.parent, travel.owner, travel.amount, travel.active), (self.year, self.ada, Decimal('80.5'), False))

    def test_a_budget_part_of_one_further_down_the_sheet(self):
        self.send(book('Budgets', [['Number', 'Name', 'Part of', 'Amount'], ['FY27-A', 'Lab', 'FY27 2027', 10], ['FY27', '2027', '', 100]]))
        self.assertEqual(Budget.objects.get(number='FY27-A').parent, Budget.objects.get(number='FY27'))

    def test_a_wrong_row_and_nothing_is_imported(self):
        page = self.send(book('Budgets', [['Number', 'Name', 'Part of', 'Owner', 'Amount'],
                                          ['N1', 'New', '', 'nobody', 1], ['N2', '', '', '', 1], ['N3', 'Other', '', '', 'lots']]))
        for said in ('Nothing was imported.', 'Row 2: there is no user &quot;nobody&quot;.', 'Row 3: it has no name.',
                     'Row 4: the amount &quot;lots&quot; is not a number.'):
            self.assertContains(page, said)
        self.assertEqual(Budget.objects.count(), 2)
        page = self.send(book('Budgets', [['Number', 'Name', 'Part of'], ['FY26', '2026', 'FY26-TE']]))   # inside itself
        self.assertContains(page, 'can&#x27;t be part of itself')
        self.assertIsNone(Budget.objects.get(pk=self.year.pk).parent)
