import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from config import Config, validate_server
from webdav import WebDavClient


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(str(Path(self.temp.name) / 'app'))
        config = patch.object(main, 'config', self.config)
        config.start()
        self.addCleanup(config.stop)

    def test_first_start_is_empty_without_creating_files(self):
        self.assertEqual(main.load_connection(), {'success': True, 'server': '', 'username': ''})
        self.assertFalse(Path(self.config.directory).exists())

    def test_successful_login_and_restart_preserve_unicode(self):
        with patch.object(main.client, 'connect', return_value=True):
            self.assertTrue(main.connect('https://example.org/Büro/', 'Jörg 日本語', 'session-only')['saved'])
        restored = Config(self.config.directory).load()
        self.assertEqual(restored, {'server': 'https://example.org/Büro/', 'username': 'Jörg 日本語'})
        self.assertNotIn('session-only', Path(self.config.filename).read_text())
        self.assertEqual(set(json.loads(Path(self.config.filename).read_text())), {'server', 'username'})

    def test_failed_login_does_not_save_or_replace(self):
        with patch.object(main.client, 'connect', return_value=False):
            self.assertFalse(main.connect('https://example.org/', 'user', 'secret')['success'])
            self.assertFalse(Path(self.config.filename).exists())
            self.config.save('https://old.example/', 'old')
            before = Path(self.config.filename).read_bytes()
            main.connect('https://new.example/', 'new', 'secret')
            self.assertEqual(Path(self.config.filename).read_bytes(), before)

    def test_invalid_urls_rejected_without_network_or_secret_output(self):
        urls = ['https://user:VERY_SECRET@example.org/dav/',
                'https://VERY_SECRET@example.org/',
                'https://example.org/?password=VERY_SECRET',
                'https://example.org/#VERY_SECRET',
                'file:///tmp/VERY_SECRET', 'https://example.org:\nVERY_SECRET']
        for url in urls:
            with self.subTest(url=url), patch.object(main.client, 'connect') as connect, redirect_stdout(io.StringIO()) as output:
                result = main.connect(url, 'user', 'VERY_SECRET')
                self.assertFalse(result['success'])
                connect.assert_not_called()
                self.assertNotIn('VERY_SECRET', output.getvalue() + str(result))
        self.assertFalse(Path(self.config.filename).exists())

    def test_corrupted_or_unsafe_configuration_does_not_block_login(self):
        self.config._directory(create=True)
        for data in ['{', '[]', '{}', '{"server":1,"username":"user"}',
                     '{"server":"https://u:pass@example.org","username":"u"}',
                     '{"server":"https://example.org","username":"u","password":"SECRET"}',
                     '{"server":"https://example.org","username":null}']:
            with self.subTest(data=data):
                Path(self.config.filename).write_text(data)
                result = main.load_connection()
                self.assertFalse(result['success'])
                self.assertEqual(result['server'], '')
                self.assertNotIn('SECRET', str(result))
                with patch.object(main.client, 'connect', return_value=True):
                    self.assertTrue(main.connect('https://example.org/', 'user', 'pass')['success'])
        Path(self.config.filename).write_bytes(b'\xff')
        self.assertFalse(main.load_connection()['success'])
        Path(self.config.filename).write_text('x' * 65537)
        self.assertFalse(main.load_connection()['success'])

    def test_permissions_on_create_and_load(self):
        old_mask = os.umask(0)
        try:
            self.config.save('https://example.org/', 'user')
        finally:
            os.umask(old_mask)
        self.assertEqual(stat.S_IMODE(os.stat(self.config.directory).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.config.filename).st_mode), 0o600)
        os.chmod(self.config.directory, 0o755)
        os.chmod(self.config.filename, 0o644)
        self.config.load()
        self.assertEqual(stat.S_IMODE(os.stat(self.config.directory).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.config.filename).st_mode), 0o600)

    def test_atomic_write_and_failed_replace_preserve_previous_settings(self):
        self.config.save('https://old.example/', 'old')
        original = Path(self.config.filename).read_bytes()
        replace = os.replace
        def inspect(source, destination):
            self.assertEqual(Path(source).parent, Path(self.config.directory))
            self.assertEqual(stat.S_IMODE(os.stat(source).st_mode), 0o600)
            self.assertEqual(Path(destination).read_bytes(), original)
            self.assertEqual(json.loads(Path(source).read_text())['username'], 'new')
            replace(source, destination)
        with patch('config.os.replace', side_effect=inspect) as atomic:
            self.config.save('https://new.example/', 'new')
            atomic.assert_called_once()
        current = Path(self.config.filename).read_bytes()
        with patch('config.os.replace', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                self.config.save('https://third.example/', 'third')
        self.assertEqual(Path(self.config.filename).read_bytes(), current)
        self.assertEqual(list(Path(self.config.directory).glob('*.tmp')), [])

    def test_failed_flush_does_not_publish_incomplete_settings(self):
        self.config.save('https://old.example/', 'old')
        original = Path(self.config.filename).read_bytes()
        with patch('config.os.fsync', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                self.config.save('https://new.example/', 'new')
        self.assertEqual(Path(self.config.filename).read_bytes(), original)
        self.assertEqual(list(Path(self.config.directory).glob('*.tmp')), [])

    def test_storage_failure_does_not_block_successful_login(self):
        with patch.object(main.client, 'connect', return_value=True), patch.object(self.config, 'save', side_effect=OSError('SECRET')):
            result = main.connect('https://example.org/', 'user', 'SECRET')
        self.assertTrue(result['success'])
        self.assertFalse(result['saved'])
        self.assertTrue(result['warning'])
        self.assertNotIn('SECRET', str(result))

    def test_delete_and_next_start(self):
        self.assertTrue(main.delete_connection()['success'])
        self.config.save('https://example.org/', 'user')
        self.assertTrue(main.delete_connection()['success'])
        self.assertFalse(Path(self.config.filename).exists())
        self.assertEqual(Config(self.config.directory).load(), {'server': '', 'username': ''})
        self.assertTrue(main.delete_connection()['success'])

    def test_delete_failure_reported_without_exception_content(self):
        self.config.save('https://example.org/', 'user')
        with patch('config.os.unlink', side_effect=PermissionError('SECRET')):
            result = main.delete_connection()
        self.assertFalse(result['success'])
        self.assertNotIn('SECRET', str(result))
        self.assertTrue(Path(self.config.filename).exists())

    def test_symlinked_config_is_not_read(self):
        external = Path(self.temp.name) / 'outside'
        external.write_text('SECRET')
        self.config._directory(create=True)
        Path(self.config.filename).symlink_to(external)
        self.assertFalse(main.load_connection()['success'])
        self.assertEqual(external.read_text(), 'SECRET')

    def test_no_password_or_url_logging_on_success_and_failure(self):
        with redirect_stdout(io.StringIO()) as output:
            with patch.object(main.client, 'connect', return_value=True):
                main.connect('https://example.org/private/', 'private-user', 'SECRET')
            with patch.object(main.client, 'connect', side_effect=RuntimeError('SECRET')):
                main.connect('https://example.org/', 'private-user', 'SECRET')
            client = WebDavClient()
            with patch('webdav.WebDavClient._open', side_effect=RuntimeError('SECRET')):
                self.assertFalse(client.connect('https://example.org/', 'private-user', 'SECRET'))
        for value in ('SECRET', 'private-user', 'example.org'):
            self.assertNotIn(value, output.getvalue())
        for file in Path(self.temp.name).rglob('*'):
            if file.is_file():
                self.assertNotIn(b'SECRET', file.read_bytes())
