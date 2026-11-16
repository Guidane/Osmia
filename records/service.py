"""What happens to assets (records with an asset tag): checked out and brought back, calibrated, sent away
(calibration, repair), retired, put in use, moved. Each keeps a RecordEvent."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Record, RecordEvent

AWAY = (Record.Status.CALIBRATION, Record.Status.REPAIR, Record.Status.RETIRED, Record.Status.IN_USE)


def event(asset, kind, user, note=''):
    return RecordEvent.objects.create(record=asset, kind=kind, user=user, note=str(note or '').strip()[:300])


def _locked(asset):
    return Record.objects.select_for_update().get(pk=asset.pk)


@transaction.atomic
def check_out(asset, user, to=None, note=''):
    """``to`` (else ``user``) has the asset now."""
    asset = _locked(asset)
    if asset.status != Record.Status.AVAILABLE:
        raise ValidationError(f'{asset} is {asset.get_status_display().lower()}' + (f' ({asset.holder})' if asset.holder else '') + '.')
    asset.status, asset.holder = Record.Status.OUT, to or user
    asset.save(update_fields=['status', 'holder'])
    event(asset, RecordEvent.Kind.OUT, user, f'to {asset.holder}' + (f': {note}' if note else ''))
    return asset


@transaction.atomic
def bring_back(asset, user, note=''):
    """Back at its location, from being checked out, in use or sent away."""
    asset = _locked(asset)
    if asset.status in (Record.Status.AVAILABLE, Record.Status.RETIRED, Record.Status.BUILDING):
        raise ValidationError(f'{asset} is {asset.get_status_display().lower()}.')
    asset.status, asset.holder = Record.Status.AVAILABLE, None
    asset.save(update_fields=['status', 'holder'])
    event(asset, RecordEvent.Kind.BACK, user, note)
    return asset


@transaction.atomic
def calibrated(asset, user, on=None, note=''):
    """It was calibrated (``on``, else today): due again after its interval. An asset away for calibration is back."""
    asset = _locked(asset)
    on = on or date.today()
    if on > date.today():
        raise ValidationError('A calibration can\'t be in the future.')
    asset.calibrated_on = on
    if asset.status == Record.Status.CALIBRATION:
        asset.status = Record.Status.AVAILABLE
    asset.save(update_fields=['calibrated_on', 'status'])
    event(asset, RecordEvent.Kind.CALIBRATED, user, f'on {on:%d %b %Y}' + (f': {note}' if note else ''))
    return asset


@transaction.atomic
def send_away(asset, user, why, note=''):
    """Away for calibration or repair, in use (installed somewhere), or retired (``why``: an Record.Status)."""
    asset = _locked(asset)
    if why not in AWAY:
        raise ValidationError('Where is it going?')
    if asset.status == Record.Status.OUT:
        raise ValidationError(f'{asset.holder} has {asset} out: bring it back first.')
    asset.status, asset.holder = why, None
    if why == Record.Status.RETIRED:   # no longer there: not counted as stock
        asset.quantity = 0
    asset.save(update_fields=['status', 'holder', 'quantity'])
    event(asset, RecordEvent.Kind.AWAY, user, Record.Status(why).label + (f': {note}' if note else ''))
    return asset


def due(within_days=14):
    """The assets due for calibration within ``within_days`` (and overdue ones), soonest first."""
    limit = date.today() + timedelta(days=within_days)
    found = [a for a in Record.objects.exclude(status=Record.Status.RETIRED).exclude(calibration_months=None).select_related('keeper', 'definition', 'harness', 'device')
             if a.calibration_due <= limit]
    return sorted(found, key=lambda a: a.calibration_due)


def next_tag(prefix):
    """The first free asset tag ``<prefix>-001``, ``<prefix>-002``…"""
    return next_tags(prefix, 1)[0]


def next_tags(prefix, n):
    """The first ``n`` free asset tags ``<prefix>-001``, ``<prefix>-002``…"""
    found, i = [], Record.objects.filter(tag__startswith=f'{prefix}-').count() + 1
    while len(found) < n:
        if not Record.objects.filter(tag__iexact=f'{prefix}-{i:03d}').exists():
            found.append(f'{prefix}-{i:03d}')
        i += 1
    return found


@transaction.atomic
def move(asset, location, user, note=''):
    """An asset put in another location."""
    asset = _locked(asset)
    if location is None or location == asset.location:
        raise ValidationError('Pick another location to move it to.')
    was = asset.location
    asset.location = location
    asset.save(update_fields=['location'])
    event(asset, RecordEvent.Kind.NOTE, user, f'moved from {was.path if was else "nowhere"} to {location.path}' + (f': {note}' if note else ''))
    return asset
