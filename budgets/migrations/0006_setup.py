"""A budget's ``project`` is its ``setup`` (setups moved to their own app: ``setups.migrations.0001``)."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budgets', '0005_setup_name'),
        ('setups', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='budget', name='project',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='budgets', to='setups.setup', verbose_name='setup'),
        ),
        migrations.RenameField(model_name='budget', old_name='project', new_name='setup'),
    ]
