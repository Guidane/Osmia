"""Configurations go: each one becomes a setup of its own, holding everything it had (what it inherited from the
configurations above it, copied in). The first of a setup's configurations keeps the setup itself (its files, pages,
budgets); the others are new setups in the same project. A setup that had several configurations and no project gets
a project of its name to hold them. Each harness belongs to the first setup that has it placed; harness requests and
the links of notifications go to the setup their configuration became; the demo's records follow."""
import django.db.models.deletion
from django.db import migrations, models


def _resolved(config, by_parent_chain, own):
    """{key: placement} of ``config``: its ancestors' rows, then its own (a removed row takes the key away)."""
    out = {}
    for node in by_parent_chain(config):
        for p in own.get(node.pk, []):
            if p.removed:
                out.pop(p.key, None)
            else:
                out[p.key] = p
    return out


def split(apps, schema_editor):
    Setup = apps.get_model('setups', 'Setup')
    Configuration = apps.get_model('setups', 'Configuration')
    Placement = apps.get_model('setups', 'Placement')
    HarnessRequest = apps.get_model('setups', 'HarnessRequest')
    Harness = apps.get_model('harnesses', 'Harness')
    Work = apps.get_model('work', 'Project')
    DemoRecord = apps.get_model('web', 'DemoRecord')
    Notification = apps.get_model('web', 'Notification')
    demo = set(DemoRecord.objects.filter(model='setups.Setup').values_list('object_id', flat=True))
    fields = ('kind', 'device_id', 'label', 'x', 'y', 'harness_id', 'ends', 'handles')
    made_for_demo = {'setups.Setup': [], 'setups.Placement': [], 'work.Project': []}
    links = []   # (old address start, new address start)

    for setup in Setup.objects.order_by('pk'):
        configs = {c.pk: c for c in Configuration.objects.filter(setup=setup)}
        if not configs:
            continue
        children = {}
        for c in sorted(configs.values(), key=lambda c: c.pk):
            children.setdefault(c.parent_id, []).append(c)
        ordered = []

        def walk(parent):
            for c in children.get(parent, []):
                ordered.append(c)
                walk(c.pk)
        walk(None)
        ordered += [c for c in configs.values() if c not in ordered]   # (a loop can't happen; to be sure)

        def chain(c):
            out = []
            while c is not None:
                out.append(c)
                c = configs.get(c.parent_id)
            return out[::-1]
        own = {}
        for p in Placement.objects.filter(configuration_id__in=configs).order_by('pk'):
            own.setdefault(p.configuration_id, []).append(p)
        rows = {c.pk: [(key, {f: getattr(p, f) for f in fields}) for key, p in _resolved(c, chain, own).items()] for c in ordered}

        several = len(ordered) > 1
        project = setup.in_project
        if several and project is None:
            project = Work.objects.create(code=setup.code, name=setup.name, description=setup.description,
                                          owner=setup.owner, department=setup.department)
            if setup.pk in demo:
                made_for_demo['work.Project'].append(project.pk)
        target = {}
        for i, c in enumerate(ordered):
            if i == 0:
                new = setup
                if several:
                    new.name = c.name[:200]
                    new.description = c.description or setup.description
                new.in_project = project
                new.save()
            else:
                new = Setup.objects.create(code=f'{setup.code}.{i + 1}' if setup.code else '', name=c.name[:200],
                                           description=c.description, owner=setup.owner, department=setup.department,
                                           in_project=project)
                if setup.pk in demo:
                    made_for_demo['setups.Setup'].append(new.pk)
            target[c.pk] = new
        Placement.objects.filter(configuration_id__in=configs).delete()
        for c in ordered:
            for key, values in rows[c.pk]:
                p = Placement.objects.create(setup=target[c.pk], key=key, **values)
                if setup.pk in demo:
                    made_for_demo['setups.Placement'].append(p.pk)
        for harness in Harness.objects.filter(setup=setup):   # its setup: the first that has it placed
            first = next((target[c.pk] for c in ordered if any(v['harness_id'] == harness.pk for _, v in rows[c.pk])), setup)
            if first.pk != setup.pk:
                harness.setup = first
                harness.save(update_fields=['setup'])
        for wanted in HarnessRequest.objects.filter(configuration_id__in=configs):
            wanted.setup = target[wanted.configuration_id]
            wanted.save(update_fields=['setup'])
        for c in ordered:
            for prefix in ('/setups/', '/wire-diagrams/'):
                links.append((f'{prefix}{setup.pk}/?config={c.pk}', f'/setups/{target[c.pk].pk}/'))

    for n in Notification.objects.filter(url__contains='config='):
        for old, new in links:
            if n.url.startswith(old) and not n.url[len(old):len(old) + 1].isdigit():
                n.url = new + n.url[len(old):]
                n.save(update_fields=['url'])
                break
    DemoRecord.objects.filter(model='setups.Configuration').delete()
    DemoRecord.objects.filter(model='setups.Placement').exclude(object_id__in=Placement.objects.values('pk')).delete()
    DemoRecord.objects.bulk_create([DemoRecord(model=model, object_id=pk) for model, pks in made_for_demo.items() for pk in pks])


class Migration(migrations.Migration):

    dependencies = [
        ('setups', '0001_initial'),
        ('harnesses', '0012_setup'),
        ('work', '0002_project_parent'),
        ('web', '0006_drop_old_documents'),
        ('projects', '0009_moved_to_setups'),
    ]

    operations = [
        migrations.AddField(model_name='placement', name='setup',
                            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='setups.setup')),
        migrations.AddField(model_name='harnessrequest', name='setup',
                            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='harness_requests', to='setups.setup')),
        migrations.RemoveConstraint(model_name='placement', name='unique_placement_key'),
        migrations.AlterField(model_name='placement', name='configuration',
                              field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='setups.configuration')),
        migrations.RunPython(split, migrations.RunPython.noop),
        migrations.RemoveField(model_name='placement', name='configuration'),
        migrations.RemoveField(model_name='placement', name='removed'),
        migrations.RemoveField(model_name='harnessrequest', name='configuration'),
        migrations.RemoveField(model_name='configuration', name='parent'),
        migrations.RemoveField(model_name='configuration', name='setup'),
        migrations.DeleteModel(name='Configuration'),
        migrations.AlterField(model_name='placement', name='setup',
                              field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='setups.setup')),
        migrations.AlterField(model_name='harnessrequest', name='setup',
                              field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='harness_requests', to='setups.setup')),
        migrations.AddConstraint(model_name='placement',
                                 constraint=models.UniqueConstraint(fields=('setup', 'key'), name='unique_placement_key')),
    ]
