import contextlib
import io
import socket
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from webdav import WebDavClient


class MkcolTests(unittest.TestCase):
    def setUp(self):
        self.client = WebDavClient()
        self.client.server = 'https://example.org/custom/dav/'

    def test_literal_names_and_parent_resolution(self):
        for parent in ('/', '/custom/dav/', '/custom/dav/B%C3%BCro/',
                       'https://example.org/custom/dav/B%C3%BCro/'):
            for name in ('Neuer Ordner', 'Grüße', '%', '%2F', '%2e%2e', '#?&+;:@', ' a ', 'a.b'):
                with self.subTest(parent=parent, name=name):
                    response = MagicMock()
                    response.__enter__.return_value.status = 201
                    with patch('webdav.WebDavClient._open', return_value=response) as send:
                        self.assertTrue(self.client.create_directory(parent, name))
                    request = send.call_args.args[0]
                    prefix = self.client._resolve_url(parent).rstrip('/')
                    self.assertEqual(request.full_url, prefix + '/' + urllib.parse.quote(name, safe='') + '/')
                    self.assertEqual(request.method, 'MKCOL')
                    self.assertEqual(request.data, b'')
                    self.assertIsNotNone(request.get_header('Authorization'))
                    if name == '%2F':
                        self.assertTrue(request.full_url.endswith('/%252F/'))

    def test_invalid_names_never_send(self):
        for name in ('', '  ', '\t', '.', '..', '../evil', '/evil', 'a/b', 'a\\b', '\x00', 'a\n', '\x7f', None):
            with self.subTest(name=name), patch('webdav.WebDavClient._open') as send:
                with self.assertRaises(ValueError):
                    self.client.create_directory('/', name)
                send.assert_not_called()
        with patch('webdav.WebDavClient._open') as send:
            with self.assertRaises(ValueError):
                self.client.create_directory('https://other.example/dav/', 'safe')
            send.assert_not_called()

    def test_only_created_is_success(self):
        for status in (200, 204, 207):
            response = MagicMock()
            response.__enter__.return_value.status = status
            with patch('webdav.WebDavClient._open', return_value=response):
                with self.assertRaises(ValueError):
                    self.client.create_directory('/', 'safe')

    def test_http_errors_do_not_leak_or_retry(self):
        for status in (401, 403, 404, 405, 409, 500, 507):
            with self.subTest(status=status), patch.object(main, 'client', self.client), patch(
                    'webdav.WebDavClient._open', side_effect=urllib.error.HTTPError(
                        'https://secret:password@example.org/', status, 'SECRET', {}, None)) as send:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = main.create_directory('/', 'safe')
                self.assertFalse(result['success'])
                self.assertEqual(result['status'], status)
                self.assertNotIn('SECRET', str(result) + output.getvalue())
                self.assertNotIn('password', str(result) + output.getvalue())
                self.assertEqual(send.call_count, 1)
                if status == 405:
                    self.assertIn('may', result['message'])

    def test_disconnect_uncertain_no_retry(self):
        for error in (socket.timeout(), ConnectionResetError(), urllib.error.URLError('SECRET')):
            with patch.object(main, 'client', self.client), patch('webdav.WebDavClient._open', side_effect=error) as send:
                result = main.create_directory('/', 'safe')
                self.assertFalse(result['success'])
                self.assertIn('may already', result['message'])
                self.assertNotIn('SECRET', result['message'])
                self.assertEqual(send.call_count, 1)

    def test_bridge_success_and_validation(self):
        with patch.object(main.client, 'create_directory', return_value=True) as create:
            self.assertEqual(main.create_directory('/parent/', 'Grüße'), {'success': True})
            create.assert_called_once_with('/parent/', 'Grüße')
        with patch.object(main, 'client', self.client), patch('webdav.WebDavClient._open') as send:
            self.assertFalse(main.create_directory('/', '..')['success'])
            send.assert_not_called()
