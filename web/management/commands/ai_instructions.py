from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from web import ai


class Command(BaseCommand):
    help = 'Write the instructions for an AI (how to make files Osmia imports) to AI-INSTRUCTIONS.md, without this Osmia\'s names.'

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', help='where to write it (default: AI-INSTRUCTIONS.md next to manage.py)')
        parser.add_argument('--names', action='store_true', help='with what this Osmia has (its families, item definitions, ...)')

    def handle(self, file=None, names=False, **options):
        target = Path(file) if file else Path(settings.BASE_DIR) / 'AI-INSTRUCTIONS.md'
        target.write_text(ai.describe(names=names), encoding='utf-8', newline='\n')
        self.stdout.write(self.style.SUCCESS(f'Written to {target}.'))
