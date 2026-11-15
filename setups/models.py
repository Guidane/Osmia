"""Setups: each a set of devices and the harnesses between them, drawn as a diagram (``Placement`` rows: a device or
a harness placed, where it sits, how a harness's ends plug in). Setups are grouped by the project they are in (and its
sub-projects); a copy of one is a setup of its own. See ``setups.contents``. Someone can ask for a harness between two
devices of a setup (``HarnessRequest``)."""
from django.conf import settings
from django.db import models
from django.urls import reverse


class Setup(models.Model):
    code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    department = models.ForeignKey('accounts.Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='setups')
    in_project = models.ForeignKey('work.Project', null=True, blank=True, on_delete=models.SET_NULL, related_name='setups',
                                   verbose_name='project')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'setup'

    def __str__(self):
        return f'{self.code} {self.name}'.strip()

    def get_absolute_url(self):
        return reverse('setups:setup', args=[self.pk])


class Placement(models.Model):
    """A device or a harness in a setup, under its ``key`` (in the setup's diagram and its harnesses' ``ends``)."""
    class Kind(models.TextChoices):
        DEVICE = 'device', 'Device'
        HARNESS = 'harness', 'Harness'

    setup = models.ForeignKey(Setup, on_delete=models.CASCADE, related_name='placements')
    key = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=Kind)
    device = models.ForeignKey('devices.Device', null=True, blank=True, on_delete=models.PROTECT, related_name='placements')
    label = models.CharField(max_length=100, blank=True)          # a device's name in the setup, e.g. Load board 2
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    harness = models.ForeignKey('harnesses.Harness', null=True, blank=True, on_delete=models.CASCADE, related_name='placements')
    ends = models.JSONField(default=dict, blank=True)              # a harness's {end id: key of the device it plugs into}
    handles = models.JSONField(default=dict, blank=True)           # a harness's {end id: [x, y] its line is pinned at}

    class Meta:
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['setup', 'key'], name='unique_placement_key')]

    def __str__(self):
        return f'{self.setup}: {self.key}'


class HarnessRequest(models.Model):
    """Someone asks for a harness between two devices of a setup (``a`` and ``b``: their keys). Who is asked
    (else the administrators) hears of it; a harness made between the two closes it, and who asked hears."""
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        DONE = 'done', 'Made'
        CANCELLED = 'cancelled', 'Cancelled'

    setup = models.ForeignKey(Setup, on_delete=models.CASCADE, related_name='harness_requests')
    a = models.CharField(max_length=40)
    b = models.CharField(max_length=40)
    request = models.TextField('what is needed')
    ask = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                            verbose_name='who should make it')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.OPEN)
    harness = models.ForeignKey('harnesses.Harness', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-pk']

    def __str__(self):
        return f'Harness request {self.pk}'

    def get_absolute_url(self):
        return f'{self.setup.get_absolute_url()}#req-{self.pk}'
