"""Setups now live in the setups app (``setups.migrations.0001`` renamed their tables): here they are only let go of,
nothing in the database changes."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0008_setup_name'),
        ('setups', '0001_initial'),
        ('harnesses', '0012_setup'),
        ('budgets', '0006_setup'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.DeleteModel(name='HarnessRequest'),
            migrations.DeleteModel(name='Placement'),
            migrations.DeleteModel(name='Configuration'),
            migrations.DeleteModel(name='Project'),
        ]),
    ]
