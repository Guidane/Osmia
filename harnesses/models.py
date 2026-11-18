"""Harnesses: each belongs to a setup. Its ends (each a connector, plugged into a device's connector), its pinout
(wires from an end's pin to another end's pin), extra items (contacts, ties, sleeving), saved as versions. Each one
built is an asset (``assets``) with a checklist of its wires, placed and verified."""
from collections import OrderedDict
from decimal import Decimal

from django.db import models, transaction
from django.urls import reverse

from devices.models import SET_TYPES as PIN_SET_TYPES, Connector, pin_order
from inventory.models import ItemDefinition, DefinitionOrFamily, definition_or_family
from web.models import Version

SET_TYPES = PIN_SET_TYPES + ['Shield']   # a shield's drain wire too
COLOURS = ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white', 'green/yellow']


class Harness(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        RELEASED = 'released', 'Released'
        OBSOLETE = 'obsolete', 'Obsolete'

    setup = models.ForeignKey('setups.Setup', on_delete=models.PROTECT, related_name='harnesses', verbose_name='setup')
    number = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        verbose_name_plural = 'harnesses'

    def __str__(self):
        return f'{self.number} {self.name}'

    def get_absolute_url(self):
        return reverse('harnesses:harness', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.number:
            with transaction.atomic():
                last = Harness.objects.select_for_update().order_by('-pk').values_list('pk', flat=True).first() or 0
                self.number = f'H-{last + 1:04d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def ordered_wires(self):
        return sorted(self.wires.select_related('from_end', 'to_end', 'definition', 'family'),
                      key=lambda w: (w.from_end.designator, w.to_end.designator, pin_order(w.from_pin)))

    def parts_list(self):
        """What it is made of now: [(item definition, quantity)]."""
        return parts_of(self.snapshot())

    def problems(self):
        """What is wrong with its pinout: [(wire or end or None, message)]. (What it plugs into, and whether the
        devices' pins fit, is its setup's to say: ``setups.contents.problems``.)"""
        found, joined = [], {}
        for wire in self.ordered_wires():   # a pin with several wires is a splice; the same two pins joined twice isn't
            pair = frozenset(((wire.from_end_id, wire.from_pin.lower()), (wire.to_end_id, wire.to_pin.lower())))
            joined.setdefault(pair, []).append(wire)
        for wires in joined.values():
            if len(wires) > 1:
                found.append((wires[1], f'{wires[0]} is there {len(wires)} times.'))
        return found

    def snapshot(self):
        return {'name': self.name, 'description': self.description, 'notes': self.notes,
                'ends': [{'designator': e.designator, 'definition': e.used_name} for e in self.ends.select_related('definition', 'family')],
                'wires': [{'from': w.from_end.designator, 'from_pin': w.from_pin, 'to': w.to_end.designator, 'to_pin': w.to_pin,
                           'signal': w.signal, 'to_signal': w.to_signal, 'set': w.wire_set, 'set_type': w.set_type, 'colour': w.colour, 'gauge': w.gauge,
                           'length': str(w.length) if w.length is not None else None, 'definition': w.used_name,
                           **({'group': w.wire_group} if w.wire_group else {})}   # (only when there is one: older versions have none)
                          for w in self.ordered_wires()],
                'items': [{'definition': i.used_name, 'quantity': str(i.quantity), 'note': i.note}
                          for i in self.items.select_related('definition', 'family')],
                **({'groups': [{'name': g.name, 'length': str(g.length) if g.length is not None else None,
                                'bundled': str(g.bundled) if g.bundled is not None else None} for g in self.groups.all()]}
                   if self.groups.exists() else {})}   # (only when there are: older versions have none)

    def restore(self, data):
        self.name, self.description, self.notes = data.get('name', ''), data.get('description', ''), data.get('notes', '')
        self.save()
        self.wires.all().delete()
        self.items.all().delete()
        wanted = {e['designator']: e for e in data.get('ends', [])}
        self.ends.exclude(designator__in=wanted).delete()
        ends = {}
        for position, (designator, e) in enumerate(wanted.items()):
            ends[designator], _ = HarnessEnd.objects.update_or_create(harness=self, designator=designator, defaults={'position': position})
            ends[designator].used = definition_or_family(e.get('definition'))
            ends[designator].save()
        for w in data.get('wires', []):
            wire = Wire(harness=self, from_end=ends[w['from']], from_pin=w['from_pin'], to_end=ends[w['to']], to_pin=w['to_pin'],
                        signal=w.get('signal', ''), to_signal=w.get('to_signal', ''), wire_set=w.get('set', ''), set_type=w.get('set_type', 'Straight'),
                        wire_group=w.get('group', ''), colour=w.get('colour', ''), gauge=w.get('gauge', ''), length=Decimal(w['length']) if w.get('length') else None)
            wire.used = definition_or_family(w.get('definition'))
            wire.save()
        self.groups.all().delete()
        for g in data.get('groups', []):
            HarnessGroup.objects.create(harness=self, name=g['name'], length=Decimal(g['length']) if g.get('length') else None,
                                        bundled=Decimal(g['bundled']) if g.get('bundled') else None)
        for i in data.get('items', []):
            found = definition_or_family(i['definition'])
            if found:
                line = HarnessItem(harness=self, quantity=Decimal(i['quantity']), note=i.get('note', ''))
                line.used = found
                line.save()


def parts_of(data):
    """What a harness as in ``data`` (a snapshot) is made of: [(item definition or family, quantity)], its ends' connectors, its
    wire (in metres when the wire's item definition is counted in metres) and its other items."""
    wanted = [(e['definition'], Decimal(1), None) for e in data.get('ends', []) if e.get('definition')]
    wanted += [(w['definition'], None, Decimal(w['length'] or 0)) for w in data.get('wires', []) if w.get('definition')]
    wanted += [(i['definition'], Decimal(i['quantity']), None) for i in data.get('items', [])]
    definitions = {n.lower(): definition_or_family(n) for n in {n for n, _, _ in wanted}}
    need = OrderedDict()
    for number, quantity, length in wanted:
        definition = definitions.get(number.lower())
        if definition is None:
            continue
        if quantity is None:   # a wire
            quantity = length / 1000 if definition.unit == ItemDefinition.Unit.M else Decimal(1)
        need[definition] = need.get(definition, Decimal(0)) + quantity
    return list(need.items())


class HarnessEnd(DefinitionOrFamily):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='ends')
    designator = models.CharField(max_length=30)
    definition = models.ForeignKey(ItemDefinition, null=True, blank=True, on_delete=models.SET_NULL, related_name='harness_ends')
    position = models.PositiveIntegerField(default=0)
    side = models.CharField(max_length=5, blank=True, choices=[('left', 'Left'), ('right', 'Right')])   # in the drawing: where it was added

    class Meta:
        ordering = ['position', 'designator']
        constraints = [models.UniqueConstraint(fields=['harness', 'designator'], name='unique_end_designator')]

    def __str__(self):
        return self.designator


class Wire(DefinitionOrFamily):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='wires')
    from_end = models.ForeignKey(HarnessEnd, on_delete=models.CASCADE, related_name='wires_from')
    from_pin = models.CharField(max_length=20)
    to_end = models.ForeignKey(HarnessEnd, on_delete=models.CASCADE, related_name='wires_to')
    to_pin = models.CharField(max_length=20)
    signal = models.CharField(max_length=100, blank=True)
    to_signal = models.CharField('signal at its other end', max_length=100, blank=True)   # a loopback's (TX: RX)
    wire_group = models.CharField('group', max_length=40, blank=True)   # a name tag over sets: "Channel 1"
    wire_set = models.CharField('set', max_length=20, blank=True)
    set_type = models.CharField(max_length=20, default='Straight', choices=[(t, t) for t in SET_TYPES])
    colour = models.CharField(max_length=20, blank=True, choices=[(c, c) for c in COLOURS])
    gauge = models.CharField(max_length=20, blank=True)
    length = models.DecimalField('length (mm)', max_digits=9, decimal_places=1, null=True, blank=True)
    definition = models.ForeignKey(ItemDefinition, null=True, blank=True, on_delete=models.SET_NULL, related_name='harness_wires')

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.from_end.designator}:{self.from_pin} → {self.to_end.designator}:{self.to_pin}'


class HarnessItem(DefinitionOrFamily):
    """Something else it is made of: contacts, ties, sleeving, labels."""
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='items')
    definition = models.ForeignKey(ItemDefinition, null=True, blank=True, on_delete=models.PROTECT, related_name='harness_items')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['pk']


class HarnessGroup(models.Model):
    """A group of a harness (the name tag over sets its wires carry: "Channel 1"): how long it is in all, and how much of
    that, from its left-hand connector, it runs bundled together with the other sets."""
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=40)
    length = models.DecimalField('total length (mm)', max_digits=9, decimal_places=1, null=True, blank=True)
    bundled = models.DecimalField('bundled together (mm)', max_digits=9, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['harness', 'name'], name='unique_harness_group')]

    def __str__(self):
        return f'{self.harness.number} {self.name}'

    @property
    def breakout(self):
        """Where, along the wires, the bundle ends, as drawn: 1/3 when bundled for less than half the total length, 1/2 at
        half, 2/3 past half; None without both lengths."""
        if not self.length or self.bundled is None:
            return None
        half = self.length / 2
        return '1/3' if self.bundled < half else '2/3' if self.bundled > half else '1/2'


class HarnessVersion(Version):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='versions')

    class Meta(Version.Meta):
        constraints = [models.UniqueConstraint(fields=['harness', 'number'], name='unique_harness_version')]
