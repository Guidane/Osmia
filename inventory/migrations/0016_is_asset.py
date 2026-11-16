"""An item definition that is an asset: each one of it is a record of its own, with an asset tag (``records``)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0015_item_definitions'),
    ]

    operations = [
        migrations.AddField('itemdefinition', 'is_asset', models.BooleanField(default=False, verbose_name='is asset')),
    ]
