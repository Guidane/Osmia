"""Standard categories of parts: single small items a lab keeps (electronic components, connectors and their contacts,
fasteners, wire, mechanical bits, consumables), not assemblies such as power supplies. Each with the attributes its
parts fill in; a category's attributes are those of the categories above it too, so the shared ones sit high up.
``standard_categories()`` adds the ones not there yet (by name, under the same parent) and the attributes they lack
(by name); nothing there is changed or taken away."""

# an attribute: (name, type, unit) for a number, (name, 'choice', [choices]), (name, 'text'), (name, 'yesno')
AWG = ['30 AWG', '28 AWG', '26 AWG', '24 AWG', '22 AWG', '20 AWG', '18 AWG', '16 AWG', '14 AWG', '12 AWG', '10 AWG', '8 AWG']
MM2 = ['0.14 mm²', '0.25 mm²', '0.34 mm²', '0.5 mm²', '0.75 mm²', '1 mm²', '1.5 mm²', '2.5 mm²', '4 mm²', '6 mm²', '10 mm²', '16 mm²']
THREADS = ['M1.6', 'M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M16', '#2-56', '#4-40', '#6-32', '#8-32', '#10-32',
           '1/4"-20', '1/4" BSP']
COLOURS = ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white', 'green/yellow', 'clear']
PACKAGES = ['THT', '0201', '0402', '0603', '0805', '1206', '1210', '2512', 'SOD-123', 'SOD-323', 'SMA', 'SMB', 'SMC', 'SOT-23',
            'SOT-223', 'SOIC', 'TSSOP', 'QFN', 'QFP', 'BGA', 'DIP', 'TO-92', 'TO-220', 'TO-247', 'DPAK', 'D2PAK']

TREE = [
    ('Electronic components', [('Package', 'choice', PACKAGES), ('Mounting', 'choice', ['SMD', 'Through-hole', 'Chassis'])], [
        ('Resistors', [('Resistance', 'decimal', 'Ω'), ('Tolerance', 'choice', ['0.1 %', '0.5 %', '1 %', '2 %', '5 %', '10 %']),
                       ('Power', 'decimal', 'W')], [
            ('Fixed resistors', [], []),
            ('Potentiometers and trimmers', [('Turns', 'integer', ''), ('Taper', 'choice', ['Linear', 'Logarithmic'])], []),
            ('Resistor arrays', [('Elements', 'integer', '')], []),
            ('Thermistors', [('Type', 'choice', ['NTC', 'PTC']), ('B value', 'integer', 'K')], []),
        ]),
        ('Capacitors', [('Capacitance', 'decimal', 'µF'), ('Voltage', 'decimal', 'V'), ('Tolerance', 'choice', ['1 %', '5 %', '10 %', '20 %'])], [
            ('Ceramic capacitors', [('Dielectric', 'choice', ['C0G / NP0', 'X5R', 'X7R', 'X7S', 'Y5V'])], []),
            ('Electrolytic capacitors', [('Life', 'integer', 'h'), ('Max. temperature', 'integer', '°C')], []),
            ('Tantalum capacitors', [], []),
            ('Film capacitors', [('Dielectric', 'choice', ['Polyester (PET)', 'Polypropylene (PP)', 'Polyphenylene (PPS)'])], []),
            ('Supercapacitors', [], []),
        ]),
        ('Inductors and ferrites', [('Inductance', 'decimal', 'µH'), ('Current', 'decimal', 'A'), ('DC resistance', 'decimal', 'mΩ')], [
            ('Inductors', [('Shielded', 'yesno')], []),
            ('Ferrite beads', [('Impedance at 100 MHz', 'decimal', 'Ω')], []),
            ('Common mode chokes', [], []),
        ]),
        ('Diodes', [('Reverse voltage', 'decimal', 'V'), ('Forward current', 'decimal', 'A')], [
            ('Rectifier diodes', [], []),
            ('Schottky diodes', [], []),
            ('Zener diodes', [('Zener voltage', 'decimal', 'V'), ('Power', 'decimal', 'W')], []),
            ('TVS diodes', [('Stand-off voltage', 'decimal', 'V'), ('Direction', 'choice', ['Unidirectional', 'Bidirectional'])], []),
            ('Small signal diodes', [], []),
            ('Bridge rectifiers', [], []),
        ]),
        ('LEDs', [('Colour', 'choice', ['red', 'orange', 'yellow', 'green', 'blue', 'white', 'warm white', 'RGB', 'infrared', 'UV']),
                  ('Size', 'choice', ['3 mm', '5 mm', '0603', '0805', '1206', 'PLCC-2', 'PLCC-4']),
                  ('Forward voltage', 'decimal', 'V'), ('Current', 'decimal', 'mA')], []),
        ('Transistors', [('Voltage', 'decimal', 'V'), ('Current', 'decimal', 'A')], [
            ('Bipolar transistors', [('Type', 'choice', ['NPN', 'PNP'])], []),
            ('MOSFETs', [('Type', 'choice', ['N-channel', 'P-channel']), ('On resistance', 'decimal', 'mΩ'), ('Gate threshold', 'decimal', 'V')], []),
        ]),
        ('Integrated circuits', [('Function', 'text')], [
            ('Microcontrollers', [('Core', 'text'), ('Flash', 'integer', 'kB')], []),
            ('Voltage regulators', [('Type', 'choice', ['Linear (LDO)', 'Switching buck', 'Switching boost', 'Buck-boost', 'Reference']),
                                    ('Output voltage', 'decimal', 'V'), ('Output current', 'decimal', 'A')], []),
            ('Op-amps and comparators', [('Channels', 'integer', '')], []),
            ('Logic', [('Family', 'choice', ['74HC', '74HCT', '74LVC', '74AHC', 'CD4000'])], []),
            ('Interface ICs', [('Interface', 'choice', ['RS-232', 'RS-485', 'CAN', 'USB', 'Ethernet', 'I²C', 'SPI', 'LIN'])], []),
            ('Memory', [('Size', 'integer', 'kbit')], []),
            ('Sensors ICs', [('Measures', 'text')], []),
        ]),
        ('Crystals and oscillators', [('Frequency', 'decimal', 'MHz'), ('Load capacitance', 'decimal', 'pF'),
                                      ('Type', 'choice', ['Crystal', 'Oscillator', 'Resonator'])], []),
        ('Fuses', [('Current', 'decimal', 'A'), ('Voltage', 'decimal', 'V'), ('Speed', 'choice', ['Fast', 'Slow (time-lag)']),
                   ('Size', 'choice', ['5 × 20 mm', '6.3 × 32 mm', 'Blade (mini)', 'Blade (standard)', 'SMD', 'PTC resettable'])], []),
        ('Relays', [('Coil voltage', 'decimal', 'V'), ('Contacts', 'choice', ['SPST-NO', 'SPST-NC', 'SPDT', 'DPDT']),
                    ('Switching current', 'decimal', 'A'), ('Type', 'choice', ['Electromechanical', 'Solid state', 'Reed'])], []),
        ('Switches and buttons', [('Type', 'choice', ['Push button', 'Toggle', 'Slide', 'Rocker', 'DIP', 'Tactile', 'Rotary', 'Micro switch']),
                                  ('Contacts', 'choice', ['SPST', 'SPDT', 'DPST', 'DPDT']), ('Current', 'decimal', 'A')], []),
        ('Buzzers and speakers', [('Type', 'choice', ['Magnetic buzzer', 'Piezo buzzer', 'Speaker']), ('Voltage', 'decimal', 'V')], []),
    ]),
    ('Connectors', [('Positions', 'integer', ''), ('Contact type', 'choice', ['pin', 'socket', 'genderless']),
                    ('Mounting', 'choice', ['cable', 'PCB', 'panel'])], [
        ('D-sub', [('Size', 'choice', ['DE-9', 'DA-15', 'DB-25', 'DC-37', 'DD-50', 'HD-15', 'HD-26', 'HD-44']), ('Shielded', 'yesno')], []),
        ('Circular', [('Series', 'choice', ['M8', 'M12', 'M16', 'M23', '7/8"', 'MIL-DTL-38999', 'DIN', 'XLR']),
                      ('IP rating', 'choice', ['IP40', 'IP54', 'IP65', 'IP67', 'IP68', 'IP69K'])], []),
        ('Rectangular', [('Series', 'text'), ('Pitch', 'decimal', 'mm'), ('Rows', 'integer', '')], []),
        ('Pin headers and sockets', [('Pitch', 'choice', ['1.27 mm', '2.0 mm', '2.54 mm']), ('Rows', 'integer', '')], []),
        ('Terminal blocks', [('Pitch', 'choice', ['3.5 mm', '3.81 mm', '5.0 mm', '5.08 mm', '7.5 mm', '7.62 mm']),
                             ('Wire size', 'choice', MM2), ('Clamp', 'choice', ['Screw', 'Spring (push-in)', 'IDC'])], []),
        ('RF connectors', [('Series', 'choice', ['SMA', 'RP-SMA', 'BNC', 'N', 'TNC', 'MCX', 'U.FL', 'F']),
                           ('Impedance', 'choice', ['50 Ω', '75 Ω'])], []),
        ('USB and data', [('Type', 'choice', ['USB-A', 'USB-B', 'USB-C', 'Micro USB', 'Mini USB', 'RJ45', 'RJ11', 'HDMI'])], []),
        ('Contacts', [('Wire gauge', 'choice', AWG), ('Plating', 'choice', ['Gold', 'Tin', 'Silver'])], []),
        ('Backshells and hoods', [('Fits', 'text')], []),
        ('Cable lugs and terminals', [('Type', 'choice', ['Ring', 'Fork', 'Pin', 'Blade (flat)', 'Bullet', 'Butt splice']),
                                      ('Stud size', 'choice', ['M2.5', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10']),
                                      ('Wire size', 'choice', MM2), ('Insulated', 'yesno')], []),
        ('Ferrules', [('Wire size', 'choice', MM2), ('Length', 'decimal', 'mm'), ('Insulated', 'yesno'), ('Twin', 'yesno')], []),
    ]),
    ('Wire', [('Gauge', 'choice', AWG), ('Cross-section', 'choice', MM2), ('Colour', 'choice', COLOURS),
              ('Insulation', 'choice', ['PVC', 'Silicone', 'PTFE', 'PE', 'FEP', 'XLPE']), ('Max. temperature', 'integer', '°C')], [
        ('Hook-up wire', [('Stranded', 'yesno')], []),
        ('Multi-core cable', [('Cores', 'integer', ''), ('Shielded', 'yesno')], []),
        ('Twisted pair', [('Pairs', 'integer', ''), ('Shielded', 'yesno')], []),
        ('Coaxial cable', [('Impedance', 'choice', ['50 Ω', '75 Ω']), ('Type', 'text')], []),
        ('Ribbon cable', [('Ways', 'integer', ''), ('Pitch', 'choice', ['1.27 mm', '2.54 mm'])], []),
    ]),
    ('Cable management', [('Colour', 'choice', COLOURS)], [
        ('Heat-shrink tubing', [('Diameter', 'decimal', 'mm'), ('Shrink ratio', 'choice', ['2:1', '3:1', '4:1']), ('Adhesive lined', 'yesno')], []),
        ('Braided sleeving', [('Diameter', 'decimal', 'mm')], []),
        ('Cable ties', [('Length', 'integer', 'mm'), ('Width', 'decimal', 'mm'), ('Material', 'choice', ['Nylon', 'Stainless steel'])], []),
        ('Cable glands', [('Thread', 'choice', ['M12', 'M16', 'M20', 'M25', 'M32', 'PG7', 'PG9', 'PG11', 'PG13.5', 'PG16']),
                          ('Cable range', 'text'), ('Material', 'choice', ['Nylon', 'Brass', 'Stainless steel'])], []),
        ('Grommets', [('Hole', 'decimal', 'mm')], []),
        ('Cable markers and labels', [('Type', 'choice', ['Clip-on', 'Heat-shrink', 'Self-laminating', 'Flag'])], []),
    ]),
    ('Fasteners', [('Thread', 'choice', THREADS), ('Material', 'choice', ['Steel, zinc plated', 'Steel, black oxide', 'Stainless A2',
                                                                           'Stainless A4', 'Brass', 'Nylon', 'Aluminium']),
                   ('Standard', 'text')], [
        ('Screws and bolts', [('Length', 'decimal', 'mm'), ('Head', 'choice', ['Socket cap', 'Button', 'Countersunk', 'Pan', 'Cheese', 'Hex', 'Flange']),
                              ('Drive', 'choice', ['Hex socket', 'Torx', 'Pozidriv', 'Phillips', 'Slotted', 'External hex']),
                              ('Strength', 'choice', ['4.8', '8.8', '10.9', '12.9', 'A2-70', 'A4-80'])], []),
        ('Nuts', [('Type', 'choice', ['Hex', 'Nyloc', 'Flange', 'Thin (jam)', 'Wing', 'Square', 'Cage', 'Rivet nut', 'Cap'])], []),
        ('Washers', [('Type', 'choice', ['Flat', 'Large (fender)', 'Spring', 'Serrated', 'Wave', 'Shoulder (insulating)']),
                     ('Outer diameter', 'decimal', 'mm')], []),
        ('Standoffs and spacers', [('Length', 'decimal', 'mm'), ('Ends', 'choice', ['Female-female', 'Male-female', 'Male-male', 'Unthreaded'])], []),
        ('Threaded inserts', [('Length', 'decimal', 'mm'), ('For', 'choice', ['Plastic (heat-set)', 'Wood', 'Metal (helicoil)'])], []),
        ('Rivets', [('Diameter', 'decimal', 'mm'), ('Grip range', 'text')], []),
        ('Pins and retaining rings', [('Type', 'choice', ['Dowel pin', 'Spring pin', 'Circlip (external)', 'Circlip (internal)', 'E-clip']),
                                      ('Diameter', 'decimal', 'mm')], []),
    ]),
    ('Mechanical', [], [
        ('O-rings and seals', [('Inner diameter', 'decimal', 'mm'), ('Cross-section', 'decimal', 'mm'),
                               ('Material', 'choice', ['NBR', 'FKM (Viton)', 'EPDM', 'Silicone'])], []),
        ('Springs', [('Type', 'choice', ['Compression', 'Extension', 'Torsion']), ('Outer diameter', 'decimal', 'mm'), ('Length', 'decimal', 'mm')], []),
        ('Bearings and bushings', [('Bore', 'decimal', 'mm'), ('Outer diameter', 'decimal', 'mm'), ('Width', 'decimal', 'mm')], []),
        ('Feet and bumpers', [('Diameter', 'decimal', 'mm'), ('Height', 'decimal', 'mm')], []),
        ('Hinges, latches and handles', [('Type', 'text')], []),
        ('DIN rail accessories', [('Type', 'choice', ['End stop', 'Clip', 'Marker strip'])], []),
    ]),
    ('Consumables', [], [
        ('Solder and flux', [('Alloy', 'choice', ['Sn60Pb40', 'Sn63Pb37', 'SAC305', 'Sn99.3Cu0.7']), ('Diameter', 'decimal', 'mm'),
                             ('Form', 'choice', ['Wire', 'Paste', 'Bar', 'Flux pen', 'Liquid flux'])], []),
        ('Adhesives and tapes', [('Type', 'choice', ['Kapton tape', 'Insulating tape', 'Double-sided tape', 'Epoxy', 'Cyanoacrylate',
                                                     'Hot glue', 'Threadlocker', 'Silicone'])], []),
        ('Thermal interface', [('Type', 'choice', ['Paste', 'Pad', 'Tape']), ('Conductivity', 'decimal', 'W/mK')], []),
        ('Cleaning', [('Type', 'choice', ['Isopropyl alcohol', 'Flux remover', 'Contact cleaner', 'Wipes'])], []),
    ]),
]


def standard_categories():
    """Add the standard part categories not there yet, with the attributes they lack: (categories, attributes) added."""
    from django.db import transaction

    from .models import Attribute, Category
    made = [0, 0]

    def attribute(category, spec):
        name, kind = spec[0], spec[1]
        above = [a.name for a in category.all_attributes()]
        below = Attribute.objects.filter(category_id__in=category.below()).values_list('name', flat=True)
        if name.lower() in {n.lower() for n in [*above, *below]}:   # there already, above it or below it
            return
        extra = spec[2] if len(spec) > 2 else ''
        Attribute.objects.create(category=category, name=name, kind=kind, position=category.attributes.count(),
                                 unit=extra if kind in ('integer', 'decimal') else '',
                                 choices='\n'.join(extra) if kind == 'choice' else '')
        made[1] += 1

    def add(parent, nodes):
        for name, attributes, children in nodes:
            category = Category.objects.filter(kind=Category.Kind.PARTS, parent=parent, name__iexact=name).first()
            if category is None:
                category = Category.objects.create(kind=Category.Kind.PARTS, parent=parent, name=name)
                made[0] += 1
            for spec in attributes:
                attribute(category, spec)
            add(category, children)

    with transaction.atomic():
        add(None, TREE)
    return tuple(made)
