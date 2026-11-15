"""Only the migrations of setups from before 5.18, when the app was called projects (``setups.migrations.0001``
moves its tables to ``setups``). Kept so a database of any age is brought up to date; there is no code here."""
from django.apps import AppConfig


class OldSetupsConfig(AppConfig):
    name = 'projects'
    label = 'projects'
    verbose_name = 'setups (before 5.18)'
