"""Parts are item definitions (``inventory`` 0015): the labels of parts and the demo's records of them are renamed."""
from django.db import migrations

MODELS = {'inventory.Part': 'inventory.ItemDefinition', 'inventory.PartValue': 'inventory.DefinitionValue',
          'inventory.PartLink': 'inventory.DefinitionLink', 'assets.PartAsset': 'assets.DefinitionAsset'}


def rename(names, kinds):
    def run(apps, schema_editor):
        for old, new in names.items():
            apps.get_model('web', 'DemoRecord').objects.filter(model=old).update(model=new)
        for old, new in kinds.items():
            apps.get_model('web', 'LabelLayout').objects.filter(kind=old).update(kind=new)
    return run


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0006_drop_old_documents'),
        ('inventory', '0015_item_definitions'),
        ('assets', '0004_item_definitions'),
    ]

    operations = [
        migrations.RunPython(rename(MODELS, {'part': 'definition'}),
                             rename({v: k for k, v in MODELS.items()}, {'definition': 'part'})),
    ]
