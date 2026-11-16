"""A project's assets are records (``records`` 0001): the same rows, under the records' name."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0002_project_parent'),
        ('records', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL('ALTER TABLE work_project_assets RENAME TO work_project_records'),
                migrations.RunSQL('ALTER TABLE work_project_records RENAME COLUMN asset_id TO record_id'),
            ],
            state_operations=[
                migrations.RemoveField('project', 'assets'),
                migrations.AddField('project', 'records', models.ManyToManyField(blank=True, related_name='work_projects', to='records.record')),
            ],
        ),
    ]
