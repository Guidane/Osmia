"""Parts are item definitions: what something bought from another company is, physical or not (``kind``). The models,
their ``part`` fields and the names kept in the data (a category of parts, an attribute linking to a part) are renamed."""
import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


def forward(apps, schema_editor):
    apps.get_model('inventory', 'Category').objects.filter(kind='parts').update(kind='definitions')
    apps.get_model('inventory', 'Attribute').objects.filter(links_to='part').update(links_to='definition')


def back(apps, schema_editor):
    apps.get_model('inventory', 'Category').objects.filter(kind='definitions').update(kind='parts')
    apps.get_model('inventory', 'Attribute').objects.filter(links_to='definition').update(links_to='part')


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_location_notes'),
        ('contenttypes', '0002_remove_content_type_name'),
        # what names a part in the apps that do: those migrations run with it still a part
        ('assets', '0003_asset_number'),
        ('devices', '0008_diagram_places'),
        ('harnesses', '0012_setup'),
        ('orders', '0006_order_in_project'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='part', name='unique_part_number'),
        migrations.RemoveConstraint(model_name='partvalue', name='unique_part_value'),
        migrations.RemoveConstraint(model_name='partlink', name='unique_part_link'),
        migrations.RemoveConstraint(model_name='stock', name='unique_stock'),

        migrations.RenameModel('Part', 'ItemDefinition'),
        migrations.RenameModel('PartValue', 'DefinitionValue'),
        migrations.RenameModel('PartLink', 'DefinitionLink'),
        migrations.RenameField('definitionvalue', 'part', 'definition'),
        migrations.RenameField('definitionlink', 'part', 'definition'),
        migrations.RenameField('stock', 'part', 'definition'),
        migrations.RenameField('movement', 'part', 'definition'),

        migrations.AlterModelOptions(name='itemdefinition', options={'ordering': ['number'], 'verbose_name': 'item definition'}),
        migrations.AlterModelOptions(name='stock', options={'ordering': ['definition__number', 'location__name']}),
        migrations.AddField('itemdefinition', 'kind', models.CharField(
            choices=[('physical', 'Physical'), ('service', 'Service'), ('subscription', 'Subscription'), ('licence', 'Licence'),
                     ('work', 'Statement of work')], default='physical', max_length=12)),
        migrations.AlterField('itemdefinition', 'number', models.CharField(max_length=100, verbose_name='item number')),
        migrations.AlterField('itemdefinition', 'unit', models.CharField(
            choices=[('pcs', 'pieces'), ('m', 'metres'), ('kg', 'kilograms'), ('l', 'litres'), ('set', 'sets'), ('roll', 'rolls'),
                     ('h', 'hours'), ('month', 'months'), ('year', 'years')], default='pcs', max_length=10)),
        migrations.AlterField('itemdefinition', 'category', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='definitions', to='inventory.category')),
        migrations.AlterField('itemdefinition', 'vendor', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='definitions', to='inventory.vendor')),
        migrations.AlterField('itemdefinition', 'family', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='definitions', to='inventory.family')),
        migrations.AlterField('itemdefinition', 'branch', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='definitions', to='inventory.branch')),
        migrations.AlterField('category', 'kind', models.CharField(
            choices=[('definitions', 'Item definitions'), ('assets', 'Assets')], default='definitions', max_length=12)),
        migrations.AlterField('attribute', 'links_to', models.CharField(
            blank=True, choices=[('definition', 'An item definition (of any category)'), ('asset', 'An asset (a tool, lab equipment…)')],
            max_length=10)),
        migrations.AlterField('attribute', 'kind', models.CharField(
            choices=[('text', 'Text'), ('integer', 'Whole number'), ('decimal', 'Number (with decimals)'), ('choice', 'Choice from a list'),
                     ('yesno', 'Yes / no'), ('auto', 'Auto number (an ID)'), ('interacts', 'Interacts with item definitions of a category'),
                     ('link', 'Link to an item definition or an asset')], default='text', max_length=10, verbose_name='type')),

        migrations.AddConstraint('itemdefinition', models.UniqueConstraint(
            django.db.models.functions.text.Lower('number'), name='unique_definition_number',
            violation_error_message='There is already an item definition with this number.')),
        migrations.AddConstraint('definitionvalue', models.UniqueConstraint(fields=('definition', 'attribute'), name='unique_definition_value')),
        migrations.AddConstraint('definitionlink', models.UniqueConstraint(
            fields=('definition', 'attribute', 'target'), name='unique_definition_link')),
        migrations.AddConstraint('stock', models.UniqueConstraint(fields=('definition', 'location'), name='unique_stock')),
        migrations.RunPython(forward, back),
    ]
