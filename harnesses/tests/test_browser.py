"""The pinout drawing in a real browser: viewing, a contact clicked lights the wires on it and every contact they
join (a splice's branches too); clicked again, nothing is lit."""
import os
import re

from django.core.management import call_command

from harnesses.models import Harness, HarnessEnd, HarnessSplice, Wire
from web.tests.browser import BrowserTestCase, expect


class PinoutDrawingTests(BrowserTestCase):
    def test_a_contact_clicked_lights_its_wires_and_their_contacts(self):
        call_command('demo', stdout=open('nul', 'w'))
        loom = Harness.objects.get(name='Rack loom')
        hub = loom.ends.get(designator='P1')
        spliced = loom.wires.filter(from_end=hub, from_pin='1').count() + loom.wires.filter(to_end=hub, to_pin='1').count()
        page = self.go(loom.get_absolute_url())
        # a splice: a row of its own (its contact, its symbol), and its symbol where each of its wires starts
        expect(page.locator('#pinout-drawing g.pd-splice[data-splice="S1"]')).to_have_count(spliced + 1)
        contact = page.locator('#pinout-drawing g.pd-contact', has_text='1').first
        contact.click()
        expect(page.locator('#pinout-drawing.picking')).to_have_count(1)
        self.assertGreaterEqual(page.locator('#pinout-drawing g.pd-wire.lit').count(), spliced)   # (a splice's branch: a piece of its own)
        self.assertGreater(page.locator('#pinout-drawing g.pd-contact.lit').count(), spliced)   # its own and those it joins
        contact.click()
        expect(page.locator('#pinout-drawing g.pd-wire.lit')).to_have_count(0)

    def test_a_group_s_name_tag_clicked_lights_all_of_it(self):
        call_command('demo', stdout=open('nul', 'w'))
        harness = Harness.objects.get(name='Controller to load board')
        harness.wires.filter(wire_set='CAN').update(wire_group='Channel 2')
        page = self.go(harness.get_absolute_url())
        page.locator('#pinout-drawing g.pd-group-tag', has_text='Channel 2').click()
        expect(page.locator('#set-chips button[data-set]')).to_have_count(0)            # no set chips above the drawing
        expect(page.locator('#pinout-drawing g.pd-group-tag.lit')).to_contain_text('Channel 2')
        lit = page.locator('#pinout-drawing g.pd-wire.lit').count()   # (a shield is drawn in pieces)
        self.assertGreaterEqual(lit, harness.wires.filter(wire_group='Channel 2').count())
        self.assertLess(lit, page.locator('#pinout-drawing g.pd-wire').count())                  # not the other wires

    def test_editing_keeps_the_rows_where_they_are_sets_apart_a_splice_s_stretch_twisted(self):
        call_command('demo', stdout=open('nul', 'w'))
        loom = Harness.objects.get(name='Rack loom')
        hub = loom.ends.get(designator='P1')
        HarnessSplice.objects.create(harness=loom, end=hub, pin='1', wire_set='S1', set_type='Twisted')
        HarnessSplice.objects.create(harness=loom, end=hub, pin='14', wire_set='S1', set_type='Twisted')
        page = self.go(loom.get_absolute_url())
        if os.environ.get('PINOUT_SHOT'):
            page.screenshot(path=os.environ['PINOUT_SHOT'].replace('.png', '-view.png'), full_page=True)
        page.locator('#set-chips button[data-mode="edit"]').click()
        sets = page.locator('#pinout-drawing select[data-wire]')
        expect(sets.first).to_be_visible()

        def rows():   # each wire's set picker, top to bottom
            return page.evaluate("""() => [...document.querySelectorAll('#pinout-drawing select[data-wire]')]
                .map(s => [s.dataset.wire, s.closest('foreignObject').getAttribute('y') * 1]).sort((a, b) => a[1] - b[1])""")
        before = rows()
        names = page.locator('#pinout-drawing select[data-wire]').first.locator('option').all_inner_texts()[1:-1]
        self.assertEqual(names, sorted(names, key=lambda n: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', n)]))
        self.assertFalse([n for n in names if n.startswith('Set ')])          # just its name: 1, 2, … 9, 10, 11
        gaps = sorted({round(b[1] - a[1]) for a, b in zip(before, before[1:])})
        self.assertGreater(gaps[-1], gaps[0], 'room between one set and the next')
        # the first wire put in the last set (its order would put it there): it stays where it is
        first, last = before[0][0], before[-1][0]
        last_set = page.locator(f'#pinout-drawing select[data-wire="{last}"]').input_value()
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator(f'#pinout-drawing select[data-wire="{first}"]').select_option(last_set)
        expect(page.locator(f'#pinout-drawing select[data-wire="{first}"]')).to_have_value(last_set)
        self.assertEqual([r[0] for r in rows()], [r[0] for r in before])
        # the splices' own stretches, twisted: their lines bend (a straight one is a single H)
        bent = page.evaluate("""() => [...document.querySelectorAll('#pinout-drawing g.pd-wire:not(.pd-wire-over)[data-wire^="splice-"] path.pd-wire-core')]
            .map(p => p.getAttribute('d').includes('Q'))""")
        self.assertEqual(bent, [True, True])
        # each crossing: the wire going up drawn over the other (each of the two over at every other crossing)
        over = page.evaluate("""() => [...document.querySelectorAll('#pinout-drawing g.pd-wire-over[data-wire^="splice-"]')]
            .map(g => document.querySelectorAll(g.getAttribute('clip-path').slice(4, -1) + ' rect').length)""")
        self.assertEqual(len(over), 2)
        self.assertLessEqual(abs(over[0] - over[1]), 1)
        if os.environ.get('PINOUT_SHOT'):   # (to look at it)
            page.screenshot(path=os.environ['PINOUT_SHOT'], full_page=True)

    def test_a_twisted_wire_whose_set_is_elsewhere_twists_with_its_twins_drawn_faint(self):
        call_command('demo', stdout=open('nul', 'w'))
        loom = Harness.objects.get(name='Rack loom')
        loom.wires.filter(from_end__designator='P1', from_pin='4').update(wire_set='PWR5', set_type='Twisted')   # (P2 to P7)
        page = self.go(loom.get_absolute_url())
        for mode in ('view', 'edit'):
            if mode == 'edit':
                page.locator('#set-chips button[data-mode="edit"]').click()
            expect(page.locator('#pinout-drawing g.pd-twin-tag')).to_have_count(1)
            expect(page.locator('#pinout-drawing g.pd-twin-tag')).to_contain_text('twisted with P2:4, P2:17')
            self.assertEqual(page.locator('#pinout-drawing g.pd-wire-twin:not(.pd-wire-over)').count(), 2)
            if os.environ.get('PINOUT_SHOT'):
                page.screenshot(path=os.environ['PINOUT_SHOT'].replace('.png', f'-twin-{mode}.png'), full_page=True)

    def test_a_single_contact_connector_is_drawn_once_with_how_many_and_its_contacts_picked_from_a_popup(self):
        from inventory.faces import preset
        from inventory.models import Family
        call_command('demo', stdout=open('nul', 'w'))
        loom = Harness.objects.get(name='Rack loom')
        bullet = Family.objects.create(name='Bullet terminal trial', face=preset('bullet'))
        p4 = loom.ends.get(designator='P4')
        p8 = HarnessEnd(harness=loom, designator='P8', position=99)
        p8.used = bullet
        p8.save()
        Wire.objects.create(harness=loom, from_end=p8, from_pin='1', to_end=p4, to_pin='3')
        Wire.objects.create(harness=loom, from_end=p8, from_pin='2', to_end=p4, to_pin='4')
        self.assertIn((bullet, 2), loom.parts_list())                           # two terminals in the parts list
        page = self.go(loom.get_absolute_url())
        many = page.locator(f'#pinout-drawing g.pd-many[data-end="{p8.pk}"]')
        expect(many).to_contain_text('x2')
        expect(page.locator('#pinout-drawing text.pd-title', has_text='P8 · Bullet terminal trial x2')).to_have_count(1)   # its name too
        many.click()                                                            # viewing: its contacts, one lights its wire
        expect(page.locator('.pd-contacts .pd-contact-pick')).to_have_count(2)
        page.locator('.pd-contacts .pd-contact-pick[data-pin="2"]').click()
        expect(page.locator('.pd-contacts')).to_have_count(0)
        self.assertGreaterEqual(page.locator('#pinout-drawing g.pd-wire.lit').count(), 1)
        page.locator('#set-chips button[data-mode="edit"]').click()             # editing: a new contact, joined to P4:8
        page.locator(f'#pinout-drawing g.pd-many[data-end="{p8.pk}"]').click()
        expect(page.locator('.pd-contacts .pd-contact-pick')).to_have_count(3)
        page.locator('.pd-contacts .pd-contact-pick.new').click()               # in the list at once, picked; ＋ for another
        expect(page.locator('.pd-contacts .pd-contact-pick')).to_have_count(4)
        expect(page.locator('.pd-contacts .pd-contact-pick.chosen')).to_have_attribute('data-pin', '3')
        expect(page.locator('.pd-contacts .pd-contact-pick.new')).to_have_attribute('data-pin', '4')
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator(f'#pinout-drawing g.pd-pin[data-end="{p4.pk}"][data-pin="8"]').click()
        expect(page.locator(f'#pinout-drawing g.pd-many[data-end="{p8.pk}"]')).to_contain_text('x3')
        self.assertTrue(loom.wires.filter(from_end=p8, from_pin='3', to_end=p4, to_pin='8').exists())
        if os.environ.get('PINOUT_SHOT'):
            page.locator(f'#pinout-drawing g.pd-many[data-end="{p8.pk}"]').click()
            page.screenshot(path=os.environ['PINOUT_SHOT'].replace('.png', '-many.png'), full_page=True)
