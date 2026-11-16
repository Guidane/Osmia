"""Records: what is really there. The assets' tables become the records' (an asset is a record with an asset tag; its
ids, files, pages and history stay); each asset that was no harness or device gets an item definition that is an asset
(the same name, make and model share one), which takes its category and what it filled in for it; the asset categories
join the one tree of categories; links to assets become links to their item definitions; an asset still on order
becomes a line of its item definition; the stock (so many of an item definition in a location) becomes a record each."""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

RENAME = [
    'ALTER TABLE assets_asset RENAME TO records_record',
    'ALTER TABLE assets_assetvalue RENAME TO records_recordvalue',
    'ALTER TABLE records_recordvalue RENAME COLUMN asset_id TO record_id',
    'ALTER TABLE assets_assetcheck RENAME TO records_recordcheck',
    'ALTER TABLE records_recordcheck RENAME COLUMN asset_id TO record_id',
    'ALTER TABLE assets_assetevent RENAME TO records_recordevent',
    'ALTER TABLE records_recordevent RENAME COLUMN asset_id TO record_id',
]
STATUSES = [('building', 'Being built'), ('available', 'Available'), ('out', 'Checked out'), ('in_use', 'In use'),
            ('calibration', 'Away for calibration'), ('repair', 'In repair'), ('retired', 'Retired')]
MOVED = {('assets', 'asset'): ('records', 'record'), ('assets', 'assetvalue'): ('records', 'recordvalue'),
         ('assets', 'assetcheck'): ('records', 'recordcheck'), ('assets', 'assetevent'): ('records', 'recordevent')}
LABELS = {'assets.Asset': 'records.Record', 'assets.AssetValue': 'records.RecordValue', 'assets.AssetCheck': 'records.RecordCheck',
          'assets.AssetEvent': 'records.RecordEvent'}


def convert(apps, schema_editor):
    Record = apps.get_model('records', 'Record')
    RecordValue = apps.get_model('records', 'RecordValue')
    Category = apps.get_model('inventory', 'Category')
    Attribute = apps.get_model('inventory', 'Attribute')
    ItemDefinition = apps.get_model('inventory', 'ItemDefinition')
    DefinitionValue = apps.get_model('inventory', 'DefinitionValue')
    DefinitionLink = apps.get_model('inventory', 'DefinitionLink')
    Stock = apps.get_model('inventory', 'Stock')
    OrderLine = apps.get_model('orders', 'OrderLine')
    AssetLink = apps.get_model('assets', 'AssetLink')
    DefinitionAsset = apps.get_model('assets', 'DefinitionAsset')
    DemoRecord = apps.get_model('web', 'DemoRecord')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    demo = {}
    for d in DemoRecord.objects.all():
        demo.setdefault(d.model, set()).add(d.object_id)
    made_demo = []

    def mark(label, pk, of_demo):
        if of_demo:
            made_demo.append(DemoRecord(model=label, object_id=pk))

    # the asset categories join the tree of the item definitions' (the same name under the same parent: one)
    merged = {}
    cats = {c.pk: c for c in Category.objects.filter(kind='assets')}

    def depth(c):
        return 0 if c.parent_id not in cats else 1 + depth(cats[c.parent_id])
    for c in sorted(cats.values(), key=depth):
        parent = merged.get(c.parent_id, c.parent_id)
        twin = Category.objects.filter(kind='definitions', parent_id=parent, name__iexact=c.name).first()
        if twin is not None:
            Attribute.objects.filter(category=c).update(category=twin)
            Attribute.objects.filter(target=c).update(target=twin)
            merged[c.pk] = twin.pk
        else:
            Category.objects.filter(pk=c.pk).update(kind='definitions', parent_id=parent)
            merged[c.pk] = c.pk
    gone = [pk for pk, to in merged.items() if pk != to]

    # each asset (not a harness or device built) gets an item definition that is an asset
    numbers = {n.lower() for n in ItemDefinition.objects.values_list('number', flat=True)}

    def free(number):
        number = (number or 'ASSET').strip()[:90]
        candidate, i = number, 2
        while candidate.lower() in numbers:
            candidate, i = f'{number}-{i}', i + 1
        numbers.add(candidate.lower())
        return candidate
    shared = {}
    for r in Record.objects.all().order_by('pk'):
        of_demo = r.pk in demo.get('assets.Asset', ())
        r.tag = r.number
        if r.status == 'retired':
            r.quantity = 0
        if r.device_id is None and r.harness_id is None:
            key = (r.name.strip().lower(), r.manufacturer.strip().lower(), r.model.strip().lower())
            definition = shared.get(key)
            if definition is None:
                definition = ItemDefinition.objects.create(
                    number=free(r.model or r.name), description=r.name, kind='physical', is_asset=True,
                    category_id=merged.get(r.category_id, r.category_id), manufacturer=r.manufacturer, mpn=r.model,
                    vendor_id=r.vendor_id, vendor_number=r.vendor_number, price=r.price)
                shared[key] = definition
                mark('inventory.ItemDefinition', definition.pk, of_demo)
            r.definition = definition
            for v in RecordValue.objects.filter(record=r).exclude(attribute__category=None):   # what it is, not this one
                if not DefinitionValue.objects.filter(definition=definition, attribute_id=v.attribute_id).exists():
                    made = DefinitionValue.objects.create(definition=definition, attribute_id=v.attribute_id, value=v.value, number=v.number)
                    mark('inventory.DefinitionValue', made.pk, of_demo)
        RecordValue.objects.filter(record=r).exclude(attribute__category=None).delete()
        lines = list(OrderLine.objects.filter(asset_id=r.pk).select_related('order'))
        if r.status == 'ordered':
            waiting = [l for l in lines if l.order.status not in ('received', 'cancelled')]
            if waiting and r.definition_id:   # still to come: a line of its item definition; it is made when it arrives
                OrderLine.objects.filter(pk__in=[l.pk for l in waiting]).update(definition_id=r.definition_id, asset=None, quantity=1)
                r.delete()
                continue
            r.status = 'available'
        for line in lines:
            if r.definition_id:
                OrderLine.objects.filter(pk=line.pk).update(definition_id=r.definition_id, asset=None)
            if line.order.status != 'cancelled':
                r.order_line_id = line.pk
        r.save()
    OrderLine.objects.exclude(asset=None).update(asset=None)

    # links to assets: links to their item definitions
    definition_of = dict(Record.objects.exclude(definition=None).values_list('pk', 'definition_id'))

    def link(source, attribute, target, of_demo):
        if source and target and source != target:
            made, new = DefinitionLink.objects.get_or_create(definition_id=source, attribute_id=attribute, target_id=target)
            if new:
                mark('inventory.DefinitionLink', made.pk, of_demo)
    for l in DefinitionAsset.objects.all():
        link(l.definition_id, l.attribute_id, definition_of.get(l.asset_id), l.pk in demo.get('assets.DefinitionAsset', ()))
    for l in AssetLink.objects.all():
        link(definition_of.get(l.asset_id), l.attribute_id, l.definition_id or definition_of.get(l.target_id),
             l.pk in demo.get('assets.AssetLink', ()))
    Attribute.objects.filter(links_to='asset').update(links_to='definition')
    Category.objects.filter(pk__in=gone).delete()

    # the stock: a record of each item definition in each location
    now = django.utils.timezone.now()
    for s in Stock.objects.filter(quantity__gt=0):
        made = Record.objects.create(definition_id=s.definition_id, location_id=s.location_id, quantity=s.quantity, status='available',
                                     created_at=now)
        mark('records.Record', made.pk, s.pk in demo.get('inventory.Stock', ()))

    # what the demo made, and what files and pages belong to, by their new names
    for old, new in LABELS.items():
        DemoRecord.objects.filter(model=old).update(model=new)
    DemoRecord.objects.filter(model__in=['assets.AssetLink', 'assets.DefinitionAsset', 'inventory.Stock']).delete()
    DemoRecord.objects.bulk_create(made_demo)
    for (app, model), (to_app, to_model) in MOVED.items():
        ContentType.objects.filter(app_label=to_app, model=to_model).delete()
        ContentType.objects.filter(app_label=app, model=model).update(app_label=to_app, model=to_model)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0002_remove_content_type_name'),
        ('assets', '0004_item_definitions'),
        ('inventory', '0016_is_asset'),
        ('orders', '0007_item_definitions'),
        ('devices', '0009_item_definitions'),
        ('harnesses', '0013_item_definitions'),
        ('web', '0007_item_definitions'),
        ('work', '0002_project_parent'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(sql) for sql in RENAME],
            state_operations=[
                migrations.CreateModel(
                    name='Record',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('number', models.CharField(max_length=100)),
                        ('name', models.CharField(max_length=200)),
                        ('kind', models.CharField(max_length=12)),
                        ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='inventory.category')),
                        ('manufacturer', models.CharField(blank=True, max_length=200)),
                        ('model', models.CharField(blank=True, max_length=200)),
                        ('asset_number', models.CharField(blank=True, max_length=100, verbose_name='asset number')),
                        ('serial', models.CharField(blank=True, max_length=100, verbose_name='serial number')),
                        ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='records', to='devices.device')),
                        ('harness', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='records', to='harnesses.harness')),
                        ('version', models.PositiveIntegerField(blank=True, null=True)),
                        ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='records', to='inventory.location')),
                        ('keeper', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kept_records', to=settings.AUTH_USER_MODEL)),
                        ('status', models.CharField(default='available', max_length=12)),
                        ('holder', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='held_records', to=settings.AUTH_USER_MODEL)),
                        ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='inventory.vendor')),
                        ('vendor_number', models.CharField(blank=True, max_length=200)),
                        ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                        ('calibrated_on', models.DateField(blank=True, null=True)),
                        ('calibration_months', models.PositiveIntegerField(blank=True, null=True, verbose_name='calibration every (months)')),
                        ('built_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('built_on', models.DateField(blank=True, null=True)),
                        ('notes', models.TextField(blank=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                    ],
                ),
                migrations.CreateModel(
                    name='RecordValue',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('value', models.CharField(max_length=200)),
                        ('number', models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
                        ('attribute', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='record_values', to='inventory.attribute')),
                        ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='values', to='records.record')),
                    ],
                    options={'constraints': [models.UniqueConstraint(fields=('record', 'attribute'), name='unique_asset_value')]},
                ),
                migrations.CreateModel(
                    name='RecordCheck',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('wire', models.CharField(max_length=100)),
                        ('between', models.CharField(max_length=70)),
                        ('signal', models.CharField(blank=True, max_length=100)),
                        ('colour', models.CharField(blank=True, max_length=20)),
                        ('wire_set', models.CharField(blank=True, max_length=20)),
                        ('placed', models.BooleanField(default=False)),
                        ('verified', models.BooleanField(default=False)),
                        ('position', models.PositiveIntegerField(default=0)),
                        ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checks', to='records.record')),
                    ],
                    options={'ordering': ['position']},
                ),
                migrations.CreateModel(
                    name='RecordEvent',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('kind', models.CharField(choices=[('out', 'Checked out'), ('back', 'Brought back'), ('calibrated', 'Calibrated'), ('away', 'Sent away'), ('received', 'Received'), ('built', 'Built'), ('note', 'Note')], max_length=12)),
                        ('note', models.CharField(blank=True, max_length=300)),
                        ('at', models.DateTimeField(auto_now_add=True)),
                        ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='records.record')),
                        ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={'ordering': ['-at', '-pk']},
                ),
            ],
        ),
        migrations.AddField('record', 'definition', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='records', to='inventory.itemdefinition',
            verbose_name='item definition')),
        migrations.AddField('record', 'quantity', models.DecimalField(decimal_places=3, default=1, max_digits=12)),
        migrations.AddField('record', 'order_line', models.ForeignKey(
            blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='records', to='orders.orderline')),
        migrations.AddField('record', 'tag', models.CharField(blank=True, max_length=100, null=True, verbose_name='asset tag')),
        migrations.AlterField('record', 'created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
        migrations.RunPython(convert, migrations.RunPython.noop, elidable=False),
        migrations.RemoveField('record', 'number'),
        migrations.RemoveField('record', 'name'),
        migrations.RemoveField('record', 'kind'),
        migrations.RemoveField('record', 'category'),
        migrations.RemoveField('record', 'manufacturer'),
        migrations.RemoveField('record', 'model'),
        migrations.RemoveField('record', 'vendor'),
        migrations.RemoveField('record', 'vendor_number'),
        migrations.AlterField('record', 'tag', models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name='asset tag')),
        migrations.AlterField('record', 'status', models.CharField(choices=STATUSES, default='available', max_length=12)),
        migrations.AlterField('record', 'price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='price each')),
        migrations.AlterField('record', 'location', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='records', to='inventory.location')),
        migrations.AlterModelOptions('record', {'ordering': ['created_at', 'pk']}),
        migrations.RemoveConstraint('recordvalue', 'unique_asset_value'),
        migrations.AddConstraint('recordvalue', models.UniqueConstraint(fields=('record', 'attribute'), name='unique_record_value')),
    ]
