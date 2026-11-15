"""A harness's ``project`` is its ``setup`` (setups moved to their own app: ``setups.migrations.0001``)."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('harnesses', '0011_setup_name'),
        ('setups', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='harness', name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='harnesses', to='setups.setup', verbose_name='setup'),
        ),
        migrations.RenameField(model_name='harness', old_name='project', new_name='setup'),
    ]
