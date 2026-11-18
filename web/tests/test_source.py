"""The source is UTF-8 everywhere: Python 3.12 and later refuse to load a file that is not, even for a byte in a
comment (a file once written in this machine's own code page crashed Osmia elsewhere)."""
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class SourceTests(SimpleTestCase):
    def test_every_file_is_utf8(self):
        base = Path(settings.BASE_DIR)
        found = subprocess.run(['git', 'ls-files'], cwd=base, capture_output=True, text=True).stdout.split('\n')
        files = [f for f in found if f.endswith(('.py', '.html', '.js', '.css', '.md', '.txt'))]
        if not files:   # not a git checkout (an installed release): every source file there is
            files = [str(p.relative_to(base)) for p in base.rglob('*') if p.suffix in ('.py', '.html', '.js', '.css')
                     and '.venv' not in p.parts and 'data' not in p.parts]
        bad = []
        for name in files:
            try:
                (base / name).read_bytes().decode('utf-8')
            except UnicodeDecodeError as exc:
                bad.append(f'{name} (byte {exc.start})')
        self.assertEqual(bad, [])
