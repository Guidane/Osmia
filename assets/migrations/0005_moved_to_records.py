"""The assets are records now (``records`` 0001 took their tables): what is left of them here goes."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0004_item_definitions'),
        ('records', '0001_initial'),
        ('orders', '0008_no_asset_lines'),
        ('work', '0003_records'),
    ]

    operations = [
        migrations.DeleteModel('AssetLink'),
        migrations.DeleteModel('DefinitionAsset'),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.DeleteModel('AssetValue'),
            migrations.DeleteModel('AssetCheck'),
            migrations.DeleteModel('AssetEvent'),
            migrations.DeleteModel('Asset'),
        ]),
    ]
