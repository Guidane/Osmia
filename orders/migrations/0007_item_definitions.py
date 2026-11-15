"""Parts are item definitions (``inventory`` 0015): an order line's ``part`` is its ``definition``."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_order_in_project'),
        ('inventory', '0015_item_definitions'),
    ]

    operations = [
        migrations.RenameField('orderline', 'part', 'definition'),
        migrations.AlterField('orderline', 'definition', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='order_lines', to='inventory.itemdefinition')),
    ]
