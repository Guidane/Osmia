"""Finding what a sheet or a data file names: a user, a department, a setup, a project, a budget, an item definition,
a location, a device, a vendor (as Osmia shows it; any case). Each refuses, saying where, when there is none or more
than one."""
from django.core.exceptions import ValidationError
from django.db.models import Q

from .sheets import at


def key(text):
    return ' '.join(str(text or '').split()).lower()


def one(found, n, what, text):
    found = list(found[:2])
    if len(found) != 1:
        raise ValidationError(f'{at(n)}: there is {"no" if not found else "more than one"} {what} "{text}".')
    return found[0]


def user(text, n):
    from accounts.models import User
    found = User.objects.filter(Q(username__iexact=text) | Q(email__iexact=text))
    return one(found if found.exists() else [u for u in User.objects.all() if key(u) == key(text)], n, 'user', text)


def department(text, n):
    from accounts.models import Department
    return one([d for d in Department.objects.all() if key(text) in (key(d.name), key(d.path), key(d.path.replace(' / ', '/')))],
               n, 'department', text)


def setup(text, n):
    from setups.models import Setup
    found = Setup.objects.filter(code__iexact=text).exclude(code='')
    return one(found if found.exists() else [s for s in Setup.objects.all() if key(text) in (key(s), key(s.name))], n, 'setup', text)


def project(text, n):
    from work.models import Project
    found = Project.objects.filter(code__iexact=text).exclude(code='')
    return one(found if found.exists() else [p for p in Project.objects.all() if key(text) in (key(p), key(p.name))], n, 'project', text)


def budget(text, n):
    from budgets.models import Budget
    found = Budget.objects.filter(number__iexact=text).exclude(number='')
    return one(found if found.exists() else [b for b in Budget.objects.all() if key(text) in (key(b), key(b.name))], n, 'budget', text)


def definition(text, n):
    from inventory.models import ItemDefinition
    return one(ItemDefinition.objects.filter(number__iexact=str(text).strip()), n, 'item definition', text)


def vendor(text, n):
    from inventory.models import Vendor
    return one(Vendor.objects.filter(name__iexact=str(text).strip()), n, 'vendor', text)


def device(text, n):
    from devices.models import Device
    return one(Device.objects.filter(number__iexact=str(text).strip()), n, 'device', text)
