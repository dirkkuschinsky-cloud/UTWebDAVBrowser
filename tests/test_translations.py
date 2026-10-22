"""Catalog completeness, system language and safe English fallback."""
import ast
import gettext
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import translations


def po_entries(path):
    entries = {}
    for block in path.read_text(encoding='utf-8').split('\n\n'):
        key, value, field = '', '', None
        for line in block.splitlines():
            if line.startswith('msgid '):
                key, field = ast.literal_eval(line[6:]), 'key'
            elif line.startswith('msgstr '):
                value, field = ast.literal_eval(line[7:]), 'value'
            elif line.startswith('"'):
                if field == 'key':
                    key += ast.literal_eval(line)
                elif field == 'value':
                    value += ast.literal_eval(line)
        if field is not None:
            entries[key] = value
    return entries


def fixture_mo(entries):
    """Create a standard MO fixture without depending on a host msgfmt binary."""
    keys = sorted(entries)
    originals = [key.encode('utf-8') for key in keys]
    translated = [entries[key].encode('utf-8') for key in keys]
    count = len(keys)
    offset = 28 + 16 * count
    table = []
    payload = b''
    for strings in (originals, translated):
        for value in strings:
            table.append(struct.pack('<II', len(value), offset + len(payload)))
            payload += value + b'\0'
    return struct.pack('<7I', 0x950412de, 0, count, 28, 28 + 8 * count, 0, 0) + b''.join(table) + payload


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = po_entries(ROOT / 'po/de.po')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = Path(self.temp.name) / 'de/LC_MESSAGES' / (translations.DOMAIN + '.mo')
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_bytes(fixture_mo(self.entries))

    def test_catalog_complete_utf8_and_preserves_placeholders(self):
        template = po_entries(ROOT / 'po/utwebdavbrowser.dkuschinsky.pot')
        self.assertEqual(set(template) - {''}, set(self.entries) - {''})
        self.assertIn('Language: de', self.entries[''])
        for source, target in self.entries.items():
            if not source:
                continue
            self.assertTrue(target.strip(), source)
            self.assertEqual(sorted(re.findall(r'%\d+', source)), sorted(re.findall(r'%\d+', target)), source)
            self.assertEqual(source.startswith(' '), target.startswith(' '), source)
            self.assertEqual(source.endswith(' '), target.endswith(' '), source)
        self.assertEqual(self.entries['Password'], 'Passwort')
        self.assertIn('überschreitet', self.entries['The file exceeds the editor limit of 256 KiB.'])

    def test_system_language_regions_and_english_fallback(self):
        for language, expected in [('de_DE.UTF-8', 'Passwort'), ('de_CH.UTF-8', 'Passwort'),
                                   ('en_GB.UTF-8', 'Password'), ('fr_FR.UTF-8', 'Password'),
                                   ('C.UTF-8', 'Password')]:
            with self.subTest(language=language), patch.dict(os.environ, {'LANG': language}, clear=True):
                catalog = translations.load_translation(localedir=self.temp.name)
                self.assertEqual(catalog.gettext('Password'), expected)
                self.assertEqual(catalog.gettext('Unknown future message'), 'Unknown future message')

    def test_language_preference_and_lc_messages_override(self):
        for environment in ({'LANGUAGE': 'fr:de', 'LANG': 'en_GB.UTF-8'},
                            {'LC_MESSAGES': 'de_DE.UTF-8', 'LANG': 'en_GB.UTF-8'},
                            {'LC_ALL': 'de_DE.UTF-8', 'LANG': 'en_GB.UTF-8'}):
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(translations.load_translation(localedir=self.temp.name).gettext('Password'), 'Passwort')

    def test_missing_and_damaged_catalog_never_blocks_startup(self):
        self.catalog.unlink()
        self.assertEqual(translations.load_translation(['de'], self.temp.name).gettext('Password'), 'Password')
        for damaged in (b'broken', b'\xde\x12\x04\x95', b'\0' * 28):
            self.catalog.write_bytes(damaged)
            self.assertEqual(translations.load_translation(['de'], self.temp.name).gettext('Password'), 'Password')

    def test_python_messages_localized_without_translating_data_or_exceptions(self):
        code = '''
import json, sys, translations
translations._translation = translations.load_translation(localedir=sys.argv[1])
import main, text_editor, download_jobs
from unittest.mock import patch
with patch.object(main.client, 'list_directory', side_effect=RuntimeError('SYNTHETIC_SECRET https://private.invalid')):
    listing = main.list_directory('/')
with patch.object(main.config, 'load', return_value={'server':'https://example.org/Grüße/', 'username':'Jörg'}):
    connection = main.load_connection()
print(json.dumps([listing, text_editor.failure('changed'), text_editor.failure('too_large'),
    str(download_jobs.JobValidationError(download_jobs.tr('Invalid file name.'))),
    main.PREVIEW_SIZE_MESSAGE, connection], ensure_ascii=False))
'''
        for language in ('de_DE.UTF-8', 'en_GB.UTF-8', 'fr_FR.UTF-8'):
            environment = dict(os.environ, LANG=language, LC_ALL=language,
                               PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')
            environment.pop('LANGUAGE', None)
            with self.subTest(language=language):
                process = subprocess.run([sys.executable, '-B', '-c', code, self.temp.name],
                                         env=environment, capture_output=True, text=True, check=True)
                result = json.loads(process.stdout)
                expected = self.entries if language.startswith('de') else {}
                for actual, source in [(result[0]['message'], 'The directory could not be loaded. Please check the connection and permissions.'),
                                       (result[1]['message'], 'The file changed on the server. Reload or save under a new name.'),
                                       (result[2]['message'], 'The file exceeds the editor limit of 256 KiB.'),
                                       (result[3], 'Invalid file name.'),
                                       (result[4], 'The file is too large for text preview (limit: 1 MiB). Use Download to save it.')]:
                    self.assertEqual(actual, expected.get(source, source))
                self.assertEqual(result[1]['errorCode'], 'changed')
                self.assertEqual(result[5]['username'], 'Jörg')
                self.assertEqual(result[5]['server'], 'https://example.org/Grüße/')
                self.assertNotIn('SYNTHETIC_SECRET', process.stdout + process.stderr)
                self.assertNotIn('private.invalid', process.stdout + process.stderr)

    def test_python_catalog_only_wraps_fixed_literals_and_covers_ui_messages(self):
        for name in ('main', 'webdav', 'download_jobs', 'text_editor'):
            tree = ast.parse((ROOT / 'src' / (name + '.py')).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr':
                    self.assertEqual(len(node.args), 1)
                    self.assertIsInstance(node.args[0], ast.Constant)
                    self.assertIn(node.args[0].value, self.entries)
            # UI error dictionaries and direct message values must use tr(),
            # or already-localized variables rather than bare English literals.
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if isinstance(key, ast.Constant) and key.value in ('message', 'warning'):
                            self.assertFalse(isinstance(value, ast.Constant) and bool(value.value), name)
