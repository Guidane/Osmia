"""Parts are item definitions (``inventory`` 0015): a device's and a connector's ``part`` is its ``definition``, in the
saved versions too."""
from django.db import migrations


def rename_keys(data, old, new):
    if isinstance(data, dict):
        return {(new if k == old else k): rename_keys(v, old, new) for k, v in data.items()}
    if isinstance(data, list):
        return [rename_keys(v, old, new) for v in data]
    return data


def versions(old, new):
    def run(apps, schema_editor):
        for v in apps.get_model('devices', 'DeviceVersion').objects.all():
            v.data = rename_keys(v.data, old, new)
            v.save(update_fields=['data'])
    return run


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0008_diagram_places'),
        ('inventory', '0015_item_definitions'),
    ]

    operations = [
        migrations.RenameField('device', 'part', 'definition'),
        migrations.RenameField('connector', 'part', 'definition'),
        migrations.RunPython(versions('part', 'definition'), versions('definition', 'part')),
    ]
