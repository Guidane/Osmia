"""Only the migrations of assets from before records (``records.migrations.0001`` moves its tables to ``records``: an
asset is a record with an asset tag). Kept so a database of any age is brought up to date; there is no code here."""
from django.apps import AppConfig


class OldAssetsConfig(AppConfig):
    name = 'assets'
    label = 'assets'
    verbose_name = 'assets (before records)'
