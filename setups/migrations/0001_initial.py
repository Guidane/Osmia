"""Setups move here from the app once called projects (its migrations stay in ``projects/migrations``): their tables
are renamed (projects_project -> setups_setup, ...), nothing is copied; a configuration's ``project`` becomes its
``setup``. What names them by app and model is renamed too: their content types (files and documentation pages
belong through those) and the demo data's records."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import web.models

TABLES = [('projects_project', 'setups_setup'), ('projects_configuration', 'setups_configuration'),
          ('projects_placement', 'setups_placement'), ('projects_harnessrequest', 'setups_harnessrequest')]
MODELS = [('project', 'setup', 'Project', 'Setup'), ('configuration', 'configuration', 'Configuration', 'Configuration'),
          ('placement', 'placement', 'Placement', 'Placement'), ('harnessrequest', 'harnessrequest', 'HarnessRequest', 'HarnessRequest')]


def renamed(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    DemoRecord = apps.get_model('web', 'DemoRecord')
    for old, new, old_class, new_class in MODELS:
        if not ContentType.objects.filter(app_label='setups', model=new).exists():
            ContentType.objects.filter(app_label='projects', model=old).update(app_label='setups', model=new)
        if old != new:
            for p in Permission.objects.filter(content_type__app_label='setups', content_type__model=new, codename__endswith=f'_{old}'):
                p.codename = p.codename[:-len(old)] + new
                p.name = p.name.replace(old.replace('_', ' '), new)
                p.save()
        DemoRecord.objects.filter(model=f'projects.{old_class}').update(model=f'setups.{new_class}')


def back(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    DemoRecord = apps.get_model('web', 'DemoRecord')
    for old, new, old_class, new_class in MODELS:
        ContentType.objects.filter(app_label='setups', model=new).update(app_label='projects', model=old)
        DemoRecord.objects.filter(model=f'setups.{new_class}').update(model=f'projects.{old_class}')


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('projects', '0008_setup_name'),
        ('accounts', '0003_home_reports'),
        ('devices', '0008_diagram_places'),
        ('harnesses', '0011_setup_name'),
        ('budgets', '0005_setup_name'),
        ('work', '0002_project_parent'),
        ('web', '0006_drop_old_documents'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(f'ALTER TABLE "{a}" RENAME TO "{b}"', f'ALTER TABLE "{b}" RENAME TO "{a}"')
                                 for a, b in TABLES],
            state_operations=[
                migrations.CreateModel(
                    name='Setup',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('code', models.CharField(blank=True, max_length=50)),
                        ('name', models.CharField(max_length=200)),
                        ('description', models.TextField(blank=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='setups', to='accounts.department')),
                        ('in_project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='setups', to='work.project', verbose_name='project')),
                        ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={'verbose_name': 'setup', 'ordering': ['name']},
                ),
                migrations.CreateModel(
                    name='Configuration',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=200)),
                        ('description', models.TextField(blank=True)),
                        ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='setups.configuration')),
                        ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='configurations', to='setups.setup')),
                    ],
                    options={'ordering': ['name']},
                    bases=(web.models.TreeWalk, models.Model),
                ),
                migrations.CreateModel(
                    name='HarnessRequest',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('a', models.CharField(max_length=40)),
                        ('b', models.CharField(max_length=40)),
                        ('request', models.TextField(verbose_name='what is needed')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('status', models.CharField(choices=[('open', 'Open'), ('done', 'Made'), ('cancelled', 'Cancelled')], default='open', max_length=10)),
                        ('closed_at', models.DateTimeField(blank=True, null=True)),
                        ('ask', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='who should make it')),
                        ('configuration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='harness_requests', to='setups.configuration')),
                        ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('harness', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='harnesses.harness')),
                    ],
                    options={'ordering': ['-pk']},
                ),
                migrations.CreateModel(
                    name='Placement',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('key', models.CharField(max_length=40)),
                        ('kind', models.CharField(choices=[('device', 'Device'), ('harness', 'Harness')], max_length=10)),
                        ('removed', models.BooleanField(default=False)),
                        ('label', models.CharField(blank=True, max_length=100)),
                        ('x', models.IntegerField(default=0)),
                        ('y', models.IntegerField(default=0)),
                        ('ends', models.JSONField(blank=True, default=dict)),
                        ('handles', models.JSONField(blank=True, default=dict)),
                        ('configuration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='setups.configuration')),
                        ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='placements', to='devices.device')),
                        ('harness', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='harnesses.harness')),
                    ],
                    options={'ordering': ['pk'],
                             'constraints': [models.UniqueConstraint(fields=('configuration', 'key'), name='unique_placement_key')]},
                ),
            ],
        ),
        migrations.RenameField(model_name='configuration', old_name='project', new_name='setup'),
        migrations.RunPython(renamed, back),
    ]
