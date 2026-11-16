"""An order line is always of an item definition: what arrives of it are records (``records`` 0001 moved the lines of
assets to their item definitions)."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_item_definitions'),
        ('records', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField('orderline', 'asset'),
    ]
