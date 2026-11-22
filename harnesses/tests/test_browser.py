"""The pinout drawing in a real browser: viewing, a contact clicked lights the wires on it and every contact they
join (a splice's branches too); clicked again, nothing is lit."""
from django.core.management import call_command

from harnesses.models import Harness
from web.tests.browser import BrowserTestCase, expect


class PinoutDrawingTests(BrowserTestCase):
    def test_a_contact_clicked_lights_its_wires_and_their_contacts(self):
        call_command('demo', stdout=open('nul', 'w'))
        loom = Harness.objects.get(name='Rack loom')
        hub = loom.ends.get(designator='P1')
        spliced = loom.wires.filter(from_end=hub, from_pin='1').count() + loom.wires.filter(to_end=hub, to_pin='1').count()
        page = self.go(loom.get_absolute_url())
        # a splice: its contact once, a diamond by it and one where each of its other wires starts
        expect(page.locator('#pinout-drawing g.pd-splice[data-splice="S1"]')).to_have_count(spliced)
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
