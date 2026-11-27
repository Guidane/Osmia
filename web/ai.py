"""Instructions for an AI (a Markdown file): how to make files Osmia imports, from whatever it is given (screenshots
of an older Osmia, a spreadsheet, a datasheet, a drawing, a wire list). Downloaded from the Import page with the names
this Osmia has filled in (``describe()``); ``manage.py ai_instructions`` writes it without them to AI-INSTRUCTIONS.md."""
import re

INTRO = """# Osmia: instructions for an AI

This file tells an AI (you) how to make files that **Osmia** imports. Osmia keeps track of a lab's or workshop's
item definitions (what is bought: parts, tools, services), stock and assets, orders, budgets, projects, devices,
wiring harnesses and setups.

## For the person using this file

Give an AI this file together with what you have: screenshots (of an older Osmia, or of anything else), a
spreadsheet, a datasheet, a drawing, a wire list, a text. Ask it for the file you need, for example:

- "Make an Osmia data file of the item definitions in these screenshots."
- "Make an Osmia harness file of this pinout."
- "Make an Osmia data file of everything in these screenshots of our old Osmia."

Then in Osmia, open **Import** (the menu under your name) and import the file the AI made. Osmia checks it first: when
anything in it is wrong, nothing is imported and Osmia says what is wrong, row by row. Give that message to the AI to
correct the file.

## Your task, AI

1. Read what you are given. Work out which kinds of records it holds (see "Which file to make").
2. Make **one file**, exactly in one of the formats below, and give it as a file (or one code block the person can save
   as a file). JSON: UTF-8, valid JSON, no comments, no trailing commas. CSV: a header row, then one row per record.
3. **Never invent** what you can't read. Leave a field out when it is unknown; give only what is there. Don't guess
   item numbers, prices or pin numbers.
4. Copy names, numbers and codes **exactly** as they are written (same spelling; case does not matter to Osmia).
   Records point to each other by these names: an item definition's category by its path, a budget's owner by a user
   name, a harness's connector by its family, a wire by its connectors' designators.
5. After the file, list briefly (outside the file) what you left out or were not sure of, so the person can check it.
6. When the person gives you Osmia's error messages, correct the file and give it again whole.

## Which file to make

| What you are given | File to make |
|---|---|
| Anything, or several kinds of records at once | **Osmia data file** (JSON): any of its sections |
| A list of item definitions (parts) only | Osmia data file with `item_definitions`, or a CSV of item definitions |
| A list of budgets only | Osmia data file with `budgets`, or a CSV of budgets |
| One device (its connectors and pins) | Osmia data file with `devices`, or an Osmia device file |
| One harness (its connectors and wires, a pinout) | Osmia data file with `harnesses`, or an Osmia harness file |

The Osmia data file can hold all of it in one go; prefer it unless the person asks for another.

## Names in older versions of Osmia

Screenshots of an older Osmia may use older names. Use the names of this file.

| Older Osmia | Now |
|---|---|
| Parts, Part number | Item definitions, Item number |
| Part families | Connector families |
| Wire diagrams, configurations | Setups (grouped in projects) |
| Ends (of a harness) | Connectors (of a harness) |
| Male / female | `pin` / `socket` (the gender after " / " in a family: "D-sub 9 / pin") |
| Signal (of a wire) | `signal` (shown as the wire's purpose) |
| Where it is, Kept at, Where | Location |
| Received, Still to come, Spent, Left, Used %, On hand | Counted by Osmia from orders and stock: leave them out |

## Reading screenshots of Osmia

- **Lists** (Item definitions, Budgets, Assets, Stock, Orders, Devices, Harnesses, Setups, Projects, Locations, Vendors):
  one record per row; the column headers are the field names. The tree on the left gives categories, locations,
  budgets "part of" others, projects "part of" others.
- **A detail pane or page**: the fields of one record (number, description, category, vendor, price, ...).
- **A harness pinout drawing**: connectors left and right (their designator and family on top, "P1 · D-sub 9 / socket"),
  each wire a row from a contact number on one side to one on the other, in its colour, with tags: its gauge ("22
  AWG"), its purpose ("CAN H"), its length ("450 mm"). Wires that cross each other near the ends are a twisted set; an
  ellipse round wires is a shield (a shielded set); a dashed grey line under them is the set's shield wire. A
  dashed rounded box with a name tag on top ("Channel 1") is a group. A pointed box "Splice 1" is a splice: several
  wires on one contact (give each of those wires from the same contact). "2 wires · J1, J2" says where a splice's
  wires go.
- **A device page**: its connectors (designator, name, family) and each connector's pins (number, signal, set, set
  type, group).
- **A setup diagram**: devices as boxes (each with a key, e.g. D1, and a device), harnesses as lines between them,
  plugged into the devices' connectors.

"""

DATAFILE = """## The Osmia data file

One JSON file holding any of the sections below (leave out those you have nothing for). Osmia takes them in the order
of this list, so a record can name one in an earlier section, or one Osmia already has.

```json
{
  "kind": "osmia data",
  "version": 1,
  "vendors": [{"name": "Acme Electronics", "website": "https://acme.example"}],
  "locations": [{"path": "Main building / Store / Shelf 3"}],
  "item_definitions": [
    {"number": "DSUB-9-PLUG", "description": "D-sub 9 plug housing, crimp", "category": "Connectors / D-sub",
     "vendor": "Acme Electronics", "price": 2.5, "unit": "pcs", "minimum": 10}
  ],
  "stock": [{"item": "DSUB-9-PLUG", "location": "Main building / Store / Shelf 3", "quantity": 25}]
}
```

Everything is matched to what Osmia has already (any case): a vendor by its name, a location or category by its path,
an item definition by its item number, a budget by its number, a project or setup by its code (else its name), an
asset by its tag. What matches is changed (only the fields the file gives); what doesn't is made. Devices,
harnesses and orders Osmia already has are kept as they are. Dates are written `2026-03-01`; numbers as numbers
(`2.5`) or text (`"2,5"`); yes/no as `true`/`false`.

### vendors

- `name` (needed), `code`, `website`, `email`, `phone`, `address`, `account_number` (our account with them), `notes`,
  `active` (true/false).

### locations

- `path` (needed): from the top down, joined by " / ": `"Main building / Store / Shelf 3"` (each level made when it
  isn't there). `description`, `notes`.

### categories

- `path` (needed): `"Connectors / D-sub"`. (Item definitions make their categories too.)

### departments

- `path` (needed): `"Engineering / Test"`. `description`, `manager` (a user name).

### connector_families

Connector families with their faces (how the contacts sit) are best moved with Osmia's own file of them (Connector
families › ⬇ Export). In a data file: `"connector_families": {"families": [...]}` as in that file. Families Osmia has
already are kept. Don't make faces up: name the families instead (see the list at the end, when there is one).

### item_definitions

What is bought from another company: a physical thing (a connector, a nut, a tool) or not one (a service, a
subscription, a licence, a statement of work).

- `number` (needed): the item number, unique in Osmia.
- `kind`: one of DEFINITION_KINDS_HERE. Left out: physical.
- `description`, `manufacturer`, `mpn` (the manufacturer's part number), `datasheet` (a URL), `notes`.
- `category`: its path, `"Connectors / D-sub"` (made when it isn't there).
- `unit`: what it is counted in: one of UNITS_HERE.
- `vendor`: the vendor's name (made when it isn't there); `vendor_number`: the vendor's part number.
- `price`: the last price paid, each. `minimum`: the stock to keep at least; `reorder_quantity`: how many to order then.
- `is_asset`: true when each one is kept on its own with an asset tag (tools, instruments).
- `active`: false for one no longer used.

### projects

- `name` (needed), `code` (short, e.g. "BR-4"), `part_of` (the code or name of the project it is part of), `status`
  (one of PROJECT_STATUSES_HERE), `description`, `owner` (a user name), `department` (its path), `notes`.

### setups

A setup is a set of devices and the harnesses between them (a test bench, a rack).

- `name` (needed), `code`, `description`, `owner`, `department`, `project` (code or name).
- `devices`: the devices placed in it, each `{"key": "D1", "device": "LOAD-2", "label": "Load board 1"}`: `key` its name
  in the setup (unique in it), `device` the device's number (in `devices` or in Osmia), `label` optional.

### budgets

- `name` (needed), `number` (e.g. "FY26-TE"), `part_of` (the budget it is part of: its number, or "number name" as
  Osmia shows it, "FY26 2026"), `amount`, `owner` (a user name), `setup` (code or name), `department`, `starts_on`,
  `ends_on`, `active`, `notes`.

### devices

Each as in "The Osmia device file" below (without `kind` and `version`). A device number Osmia has already: kept as it
is.

### harnesses

Each as in "The Osmia harness file" below (without `kind` and `version`), and:

- `setup`: the setup it belongs to (code or name), optional.
- `plugs`: what each of its connectors plugs into in that setup: `{"P1": "D1:J2", "P2": "D2:X1"}` (the device's key in
  the setup, ":", the device's connector designator; just `"D1"` when the connector is not known).

A harness with the same name in the same setup that Osmia has already: kept as it is.

### stock

How many of an item definition (physical, not an asset) there are in a location: `{"item": "DSUB-9-PLUG", "location":
"Main building / Store / Shelf 3", "quantity": 25}`. The location's stock of it **becomes** that quantity (as if
counted). The location must be in `locations` or in Osmia.

### assets

One each, with its asset tag: `tag` (e.g. "FLUKE-87V-001"; left out: Osmia gives one), `item` (its item number; the
item definition must have `is_asset` true), `location` (its path; needed for a physical one), `serial`,
`asset_number` (the company's own number), `status` (one of ASSET_STATUSES_HERE), `keeper` (a user name), `price`,
`calibrated_on` (date), `calibration_months` (months between calibrations), `notes`. An asset with a tag Osmia has
already is changed.

### orders

- `number` (e.g. "PO-0012"; left out: Osmia gives one), `vendor` (needed unless a draft), `status` (one of
  ORDER_STATUSES_HERE), `budget` (number or name), `project`, `vendor_reference` (the vendor's order number),
  `ordered_on`, `expected_on`, `received_on`, `notes`.
- `lines` (needed): each `{"item": "DSUB-9-PLUG", "quantity": 20, "price": 2.5, "received": 20}`: `item` an item
  number (in `item_definitions` or in Osmia), `price` each, `received` how many have come (left out: all of them when
  the order is received, else none).

Orders come in as a record of what was ordered: they don't add stock (give that in `stock` and `assets`).

## Item definitions or budgets as a CSV (or Excel) file

Instead of a data file: a CSV file (UTF-8, columns split by commas or semicolons) with a header row. Osmia's own ⬇ Excel
of these lists has the same columns; a CSV with only some of them changes only those.

Item definitions: `Item number` (needed), `Kind`, `Description`, `Category`, `Manufacturer`, `Manufacturer part
number`, `Unit`, `Vendor`, `Vendor's number`, `Last price`, `Minimum`, `Active`, `Reorder quantity`, `Is asset`,
`Datasheet`, `Notes`.

```csv
Item number,Description,Category,Unit,Vendor,Last price,Minimum
DSUB-9-PLUG,D-sub 9 plug housing,Connectors / D-sub,pcs,Acme Electronics,2.50,10
```

Budgets: `Number`, `Name` (needed), `Part of`, `Setup`, `Owner`, `Amount`, `Department`, `Starts`, `Ends`, `Active`,
`Notes`.

"""

CHECKLIST = """## Before you answer

- The file is valid JSON (or CSV with a header row), in one of the formats above, with `"kind"` as shown.
- Every name a record points to (a category path, a vendor, an item number, a connector designator, a device number, a
  setup) is written exactly the same everywhere.
- Nothing is invented: unknown fields are left out.
- Counted values (on hand, spent, left, used, received totals) are left out.
- Below the file: what you left out or were not sure of.
"""


def _demoted(text):
    """A file format's text as part of this one: each heading a level lower."""
    return re.sub(r'^(#+) ', lambda m: '#' + m.group(1) + ' ', text, flags=re.M)


def _filled(text):
    from harnesses.models import COLOURS
    from inventory.models import ItemDefinition
    from orders.models import Order
    from records.models import Record
    from work.models import Project

    def codes(choices):
        return ', '.join(f'`{value}`' for value, _ in choices)
    return (text.replace('DEFINITION_KINDS_HERE', codes(ItemDefinition.Kind.choices))
            .replace('UNITS_HERE', codes(ItemDefinition.Unit.choices))
            .replace('PROJECT_STATUSES_HERE', codes(Project.Status.choices))
            .replace('ASSET_STATUSES_HERE', codes(Record.Status.choices))
            .replace('ORDER_STATUSES_HERE', codes(Order.Status.choices))
            .replace('COLOURS_HERE', ', '.join(f'`{c}`' for c in COLOURS)))


def _formats():
    """The device and harness file formats, as their pages describe them (without this Osmia's families)."""
    from devices import transfer as devices
    from harnesses import transfer as harnesses
    from harnesses.models import COLOURS, SET_TYPES, HarnessMark
    from devices.models import SET_TYPES as PIN_SET_TYPES
    device = devices.FORMAT.replace('SET_TYPES_HERE', ', '.join(f'`{t}`' for t in PIN_SET_TYPES))
    device = device.replace('SIDES_HERE', ', '.join(f'`{s}`' for s in devices.SIDES))
    harness = harnesses.FORMAT.replace('COLOURS_HERE', ', '.join(f'`{c}`' for c in COLOURS))
    harness = harness.replace('SET_TYPES_HERE', ', '.join(f'`{t}`' for t in SET_TYPES))
    harness = harness.replace('KINDS_HERE', ', '.join(f'`{k}`' for k in HarnessMark.Kind.values))
    for old, new in (('The families this Osmia knows are\n  listed at the end of this file.', 'The families this Osmia knows are\n  listed at the end of this file, when there is such a list.'),):
        device, harness = device.replace(old, new), harness.replace(old, new)
    return _demoted(device.strip()) + '\n\n' + _demoted(harness.strip()) + '\n\n'


def _names():
    """What this Osmia has, for the AI to point to: connector families, categories, locations, vendors, item
    definitions, devices, projects, setups, budgets, departments."""
    from accounts.models import Department
    from budgets.models import Budget
    from devices.models import Device
    from inventory.models import Category, Family, ItemDefinition, Location, Vendor
    from setups.models import Setup
    from work.models import Project
    MOST = 400

    def block(title, items):
        items = list(items)
        if not items:
            return []
        shown = items[:MOST]
        return [f'### {title}', ''] + [f'- {i}' for i in shown] + ([f'- … and {len(items) - MOST} more'] if len(items) > MOST else []) + ['']
    lines = ['## What this Osmia has', '',
             'Names to point to (copy them exactly). Records not listed here are made by the file, or are refused when they must be there already.', '']
    lines += block('Connector families (with their genders)',
                   [f.name + (f' ({", ".join(b.name for b in f.branches.all())})' if f.branches.exists() else '')
                    for f in Family.objects.prefetch_related('branches').order_by('name')])
    lines += block('Categories', [c.path for c, _ in Category.ordered()])
    lines += block('Locations', [loc.path for loc, _ in Location.ordered()])
    lines += block('Vendors', Vendor.objects.values_list('name', flat=True))
    lines += block('Item definitions', [f'{d.number}: {d.description}' if d.description else d.number
                                        for d in ItemDefinition.objects.filter(active=True).order_by('number')])
    lines += block('Devices', [f'{d.number}: {d.name}' for d in Device.objects.order_by('number')])
    lines += block('Projects', [str(p) for p in Project.objects.order_by('code', 'name')])
    lines += block('Setups', [str(s) for s in Setup.objects.order_by('code', 'name')])
    lines += block('Budgets', [str(b) for b, _ in Budget.ordered()])
    lines += block('Departments', [d.path for d, _ in Department.ordered()])
    return '\n'.join(lines)


def describe(names=True):
    """The instructions; ``names``: with what this Osmia has (its families, categories, item definitions, ...)."""
    from osmia.version import VERSION
    text = INTRO + _filled(DATAFILE) + _formats() + CHECKLIST
    text += f'\n(For Osmia {VERSION}.)\n'
    if names:
        text += '\n' + _names()
    return text
