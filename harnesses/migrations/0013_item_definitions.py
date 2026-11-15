"""Parts are item definitions (``inventory`` 0015): what a harness end, a wire or another item is made of is its
``definition``, in the saved versions too."""
import django.db.models.deletion
from django.db import migrations, models



def rename_keys(data, old, new):
    if isinstance(data, dict):
        return {(new if k == old else k): rename_keys(v, old, new) for k, v in data.items()}
    if isinstance(data, list):
        return [rename_keys(v, old, new) for v in data]
    return data


def versions(old, new):
    def run(apps, schema_editor):
        for v in apps.get_model('harnesses', 'HarnessVersion').objects.all():
            v.data = rename_keys(v.data, old, new)
            v.save(update_fields=['data'])
    return run


class Migration(migrations.Migration):

    dependencies = [
        ('harnesses', '0012_setup'),
        ('inventory', '0015_item_definitions'),
    ]

    operations = [
        migrations.RenameField('harnessend', 'part', 'definition'),
        migrations.RenameField('wire', 'part', 'definition'),
        migrations.RenameField('harnessitem', 'part', 'definition'),
        migrations.AlterField('harnessitem', 'definition', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='harness_items', to='inventory.itemdefinition')),
        migrations.RunPython(versions('part', 'definition'), versions('definition', 'part')),
    ]
