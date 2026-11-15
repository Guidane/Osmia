"""Parts are item definitions (``inventory`` 0015): what links an asset and an item definition is renamed with them."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0003_asset_number'),
        ('inventory', '0015_item_definitions'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='partasset', name='unique_part_asset'),
        migrations.RenameModel('PartAsset', 'DefinitionAsset'),
        migrations.RenameField('definitionasset', 'part', 'definition'),
        migrations.RenameField('assetlink', 'part', 'definition'),
        migrations.AlterField('definitionasset', 'asset', models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, related_name='definition_links', to='assets.asset')),
        migrations.AddConstraint('definitionasset', models.UniqueConstraint(
            fields=('definition', 'attribute', 'asset'), name='unique_definition_asset')),
    ]
