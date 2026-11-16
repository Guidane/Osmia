"""Stock is records (``records`` 0001 made one of each item definition in each location); the categories are one tree
(the asset categories joined it); an attribute links to item definitions only."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0016_is_asset'),
        ('records', '0001_initial'),
        ('assets', '0005_moved_to_records'),
    ]

    operations = [
        migrations.DeleteModel('Stock'),
        migrations.RemoveField('category', 'kind'),
        migrations.RemoveField('attribute', 'links_to'),
        migrations.AlterField('attribute', 'kind', models.CharField(
            choices=[('text', 'Text'), ('integer', 'Whole number'), ('decimal', 'Number (with decimals)'), ('choice', 'Choice from a list'),
                     ('yesno', 'Yes / no'), ('auto', 'Auto number (an ID)'), ('interacts', 'Interacts with item definitions of a category'),
                     ('link', 'Link to an item definition')], default='text', max_length=10, verbose_name='type')),
    ]
