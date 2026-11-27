# Osmia: instructions for an AI

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

## The Osmia data file

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
- `kind`: one of `physical`, `service`, `subscription`, `licence`, `work`. Left out: physical.
- `description`, `manufacturer`, `mpn` (the manufacturer's part number), `datasheet` (a URL), `notes`.
- `category`: its path, `"Connectors / D-sub"` (made when it isn't there).
- `unit`: what it is counted in: one of `pcs`, `m`, `kg`, `l`, `set`, `roll`, `h`, `month`, `year`.
- `vendor`: the vendor's name (made when it isn't there); `vendor_number`: the vendor's part number.
- `price`: the last price paid, each. `minimum`: the stock to keep at least; `reorder_quantity`: how many to order then.
- `is_asset`: true when each one is kept on its own with an asset tag (tools, instruments).
- `active`: false for one no longer used.

### projects

- `name` (needed), `code` (short, e.g. "BR-4"), `part_of` (the code or name of the project it is part of), `status`
  (one of `active`, `on_hold`, `done`), `description`, `owner` (a user name), `department` (its path), `notes`.

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
`asset_number` (the company's own number), `status` (one of `building`, `available`, `out`, `in_use`, `calibration`, `repair`, `retired`), `keeper` (a user name), `price`,
`calibrated_on` (date), `calibration_months` (months between calibrations), `notes`. An asset with a tag Osmia has
already is changed.

### orders

- `number` (e.g. "PO-0012"; left out: Osmia gives one), `vendor` (needed unless a draft), `status` (one of
  `draft`, `ordered`, `partly`, `received`, `cancelled`), `budget` (number or name), `project`, `vendor_reference` (the vendor's order number),
  `ordered_on`, `expected_on`, `received_on`, `notes`.
- `lines` (needed): each `{"item": "DSUB-9-PLUG", "quantity": 20, "price": 2.5, "received": 20}`: `item` an item
  number (in `item_definitions` or in Osmia), `price` each, `received` how many have come (left out: all of them when
  the order is received, else none).

Orders come in as a record of what was ordered: they don't add stock (give that in `stock` and `assets`).

## Item definitions or budgets as a CSV (or Excel) file

Instead of a data file: a CSV file (UTF-8, columns split by commas or semicolons) with a header row. Osmia's own ⬇ CSV
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

## Osmia device file

A device for Osmia (a board, an instrument, a power supply: anything harnesses plug into) as one JSON file (UTF-8),
with its connectors and their pins. Osmia takes it in on the device list (⬆ Import) as a new device. ⬇ JSON on a
device's page gives a file of this kind to compare with.

```json
{
  "kind": "osmia device",
  "version": 1,
  "number": "LOAD-2",
  "name": "Load board",
  "origin": "in_house",
  "manufacturer": "",
  "model": "",
  "description": "",
  "notes": "",
  "connectors": [
    {"designator": "J1", "name": "Bus in", "family": "D-sub 9 / socket", "side": "left",
     "pins": [
       {"number": "1", "signal": "+24 V"},
       {"number": "6", "signal": "0 V"},
       {"number": "2", "signal": "CAN H", "set": "CAN", "set_type": "Twisted", "group": "Bus"},
       {"number": "7", "signal": "CAN L", "set": "CAN", "set_type": "Twisted", "group": "Bus"},
       {"number": "5", "signal": "Shield", "description": "to the case"}
     ]}
  ]
}
```

Only `number` and `name` are needed; everything else may be left out.

### The device

- `number`: its device number, unique in Osmia (at most 100 characters). A file with a number Osmia has already is
  refused.
- `name`: what it is called.
- `origin`: `in_house` (designed and made here) or `external` (bought). Left out: `in_house`.
- `manufacturer`, `model`: for one that is bought.
- `definition`: the item number it is bought or stocked as, when Osmia knows it.
- `description`, `notes`: free text.

### connectors

- `designator`: the connector's name on the device (J1, X3, CN2). Unique on the device.
- `name`: what it is for ("Bus in", "Mains").
- `family`: its connector family, with its gender after " / " ("D-sub 9 / socket", "M12 A-coded 8 / pin"), or the
  item number of an exact part. Pin: the connector has pins; socket: it has sockets. The families this Osmia knows are
  listed at the end of this file, when there is such a list. Leave it out when unknown: the device is still made, without the connector's face.
- `side`: where it sits on the device as drawn: one of `top`, `right`, `bottom`, `left`. Leave it out to let Osmia place it.
- `pins`: its contacts that are used (or all of them).

### pins

- `number`: the contact number as printed on the connector ("1", "A", "12"). Unique on the connector.
- `signal`: what it carries ("+24 V", "0 V", "CAN H").
- `set`: a short name (at most 20 characters) shared by pins whose wires go together: a twisted pair, a shielded pair.
- `set_type`: how a set's wires go together: one of `Straight`, `Twisted`, `Shielded twisted`, `Shielded`. The same for every pin of a set.
- `group`: a name tag over several sets (at most 40 characters): "Channel 1".
- `description`: anything else about the pin.

## Osmia harness file

A harness for Osmia as one JSON file (UTF-8). Osmia takes it in on the harness list (⬆ Import), as a new harness
(in the setup picked there, if any). ⬇ JSON on a harness's page gives a file of this kind to compare with.

```json
{
  "kind": "osmia harness",
  "version": 1,
  "name": "Controller to load board",
  "description": "",
  "notes": "",
  "connectors": [
    {"designator": "P1", "family": "D-sub 9 / socket", "side": "left"},
    {"designator": "P2", "family": "D-sub 9 / pin", "side": "right"}
  ],
  "wires": [
    {"from": "P1", "from_pin": "1", "to": "P2", "to_pin": "1", "signal": "+24 V", "colour": "red",
     "gauge": "22 AWG", "length": 450, "group": "Power", "set": "PWR", "set_type": "Twisted"},
    {"from": "P1", "from_pin": "5", "to": "P2", "to_pin": "5", "signal": "Shield", "colour": "grey",
     "set": "DATA", "set_type": "Shield"}
  ],
  "groups": [{"name": "Power", "length": 450, "bundled": 200}],
  "items": [{"definition": "HS-6-BLK", "quantity": 0.2, "note": "heat shrink"}]
}
```

Only `wires` is needed; everything else may be left out.

### connectors

- `designator`: the connector's name on the harness (P1, J3, X12). Unique in the harness.
- `family`: its connector family, with its gender after " / " ("D-sub 9 / pin", "M12 A-coded 8 / socket"), or the
  item number of an exact part. Pin: the connector has pins; socket: it has sockets. The families this Osmia knows are
  listed at the end of this file, when there is such a list. Leave it out when unknown: the harness is still made, without the connector's face.
- `side`: `left` or `right`, where it is drawn. Leave it out to let Osmia choose.

A connector a wire names that is not in `connectors` is made by Osmia, without a family.

### wires

One entry per wire, from a contact of a connector to a contact of a connector.

- `from`, `to`: the connectors' designators. The same one on both: a loopback.
- `from_pin`, `to_pin`: the contact numbers as printed on the connector ("1", "A", "12").
- `signal`: what the wire carries ("+24 V", "0 V", "CAN H"). `to_signal`: a loopback's signal at its other end.
- `colour`: one of `black`, `brown`, `red`, `orange`, `yellow`, `green`, `blue`, `violet`, `grey`, `white`, `green/yellow`.
- `gauge`: "22 AWG", "0.5 mm²". A bare number is taken as AWG.
- `length`: in mm, a number.
- `definition`: the item number of the wire it is cut from, when known.
- `set`: a short name (at most 20 characters) shared by the wires that go together: a twisted pair, a shielded cable.
- `set_type`: how a set's wires go together: one of `Straight`, `Twisted`, `Shielded twisted`, `Shielded`, `Shield`. Give every wire of a set the same type, but
  `Shield` for a shielded set's drain or shield wire.
- `group`: a name tag over several sets (at most 40 characters): "Channel 1".
- `from_bare`, `to_bare`: in a shielded set, how much of the wire (mm) is out of the shield at its `from` and `to` end:
  to its contact, or for a spliced end, to the splice.

A splice is several wires from the same contact: one entry for each wire.

### groups

For each `group` named by the wires, optionally: `length` (its total length, mm) and `bundled` (how much of that,
from its left-hand connector, runs bundled together with the other sets, mm).

### items

Other things the harness is made of: `definition` (an item number Osmia knows), `quantity`, `note`.

### splices

A splice (a contact with several wires) has a stretch of its own, from its contact to where its wires part: it can be in
a set with other splices' stretches (twisted, shielded) and in a group, apart from the wires after it.

```json
"splices": [{"at": "P1", "pin": "1", "set": "S1", "set_type": "Shielded twisted", "group": "Channel 1", "bare": 30, "splice_bare": 20}]
```

`bare`, `splice_bare`: in a shielded set, how much of the stretch (mm) is out of the shield at its contact and at the splice.

### bundle

How the harness is laid out, all in mm: one trunk, each connector at the end of a branch that leaves the trunk somewhere
along it, and what is put along it.

```json
"bundle": {
  "trunk": 1200,
  "connectors": {"P1": {"at": 0, "branch": 0}, "P2": {"at": 1200, "branch": 0}, "P3": {"at": 300, "branch": 250}},
  "marks": [
    {"kind": "tie", "from": 100},
    {"kind": "sleeve", "from": 50, "to": 1150, "definition": "SLEEVE-12", "text": "Braided sleeve"},
    {"kind": "shrink", "on": "P3", "from": 0, "to": 40},
    {"kind": "strip", "on": "P3", "from": 30, "set": "DATA1"},
    {"kind": "splice", "from": 1100, "text": "P1:1"},
    {"kind": "label", "on": "P3", "from": 60, "text": "X-P3"}
  ]
}
```

- `trunk`: the trunk's length.
- `connectors`: for each connector (by designator): `at`, where along the trunk its branch leaves it (0 to `trunk`),
  and `branch`, how long its branch is (0: right on the trunk, at one of its ends).
- `marks`: each with `kind` (one of `tie`, `sleeve`, `shrink`, `strip`, `splice`, `label`), `on` (a connector's designator: on its branch, measured from the
  connector; left out: on the trunk, measured from its start), `from`, and for `sleeve` and `shrink` `to`.
  `definition`: the item number of the tie, sleeve or shrink, when known (the parts list counts it). `text`: a label's
  text; for a splice, its contact ("P1:1"). `set`: for `strip`, the shielded set whose shield is stripped back.

## Before you answer

- The file is valid JSON (or CSV with a header row), in one of the formats above, with `"kind"` as shown.
- Every name a record points to (a category path, a vendor, an item number, a connector designator, a device number, a
  setup) is written exactly the same everywhere.
- Nothing is invented: unknown fields are left out.
- Counted values (on hand, spent, left, used, received totals) are left out.
- Below the file: what you left out or were not sure of.

(For Osmia 5.22.0.)
