"""Release security regressions: simulated responses only, no network."""
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from webdav import WebDavClient, DeleteSafetyError, UnsafeRedirectError
from test_downloads import Response


class ReleaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = WebDavClient()
        self.client.server = 'https://example.org:8443/dav/'
        self.client.user = 'synthetic-user'
        self.client.password = 'synthetic-secret'
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = str(Path(self.temp.name) / 'file')
        for fixture in (patch.object(main, 'client', self.client),
                        patch.dict(os.environ, {'XDG_CACHE_HOME': self.temp.name}),
                        patch.dict(sys.modules, {'pyotherside': types.SimpleNamespace(send=MagicMock())})):
            fixture.start()
            self.addCleanup(fixture.stop)
        self.addCleanup(main._downloads.clear)
        self.addCleanup(main._download_leases.clear)

    def test_real_opener_refuses_every_redirect_before_second_request(self):
        # Exercise urllib's HTTPErrorProcessor, not a mocked _open seam.
        real_build = urllib.request.build_opener
        for code in (301, 302, 303, 307, 308):
            for location in ('https://foreign.example/dav/file',
                             'http://example.org:8443/dav/file',
                             'https://example.org:9443/dav/file',
                             'https://user:secret@example.org:8443/dav/file',
                             '//foreign.example/dav/file', '/dav/next',
                             'https://example.org:bad/dav/file'):
                seen = []
                buffers = []
                class Transport(urllib.request.BaseHandler):
                    handler_order = 100
                    def https_open(self, request):
                        seen.append(request)
                        headers = Message()
                        # A same-origin first hop would lead to a foreign host.
                        headers['Location'] = location if len(seen) == 1 else 'https://foreign.example/'
                        stream = io.BytesIO(b'ignored')
                        buffers.append(stream)
                        response = urllib.response.addinfourl(stream, headers, request.full_url, code)
                        response.msg = 'Redirect'
                        return response
                    http_open = https_open
                with self.subTest(code=code, location=location), patch(
                        'webdav.urllib.request.build_opener',
                        side_effect=lambda *handlers: real_build(*handlers, Transport())):
                    Path(self.target).write_bytes(b'existing')
                    with self.assertRaises(UnsafeRedirectError):
                        self.client.download_file('/dav/file', self.target)
                    self.assertEqual(len(seen), 1)
                    self.assertEqual(seen[0].full_url, self.client.server + 'file')
                    self.assertEqual(seen[0].get_header('Authorization'), self.client._auth_header())
                    self.assertTrue(buffers[0].closed)
                    self.assertEqual(Path(self.target).read_bytes(), b'existing')
                    self.assertFalse(Path(self.target + '.part').exists())

    def test_legacy_operations_reject_unsafe_targets_without_network(self):
        invalid = ['/BSW/file.json', '//file.json', '/davish/file', '/outside/file',
                   '/dav/../file', '/dav/%2e%2e/file', '/dav/a%2Fb',
                   '/dav/a%5Cb', '/dav/%00', '/dav/%', '/dav//file',
                   'https://foreign.example/dav/file', 'http://example.org:8443/dav/file',
                   'https://example.org:443/dav/file',
                   'https://u:p@example.org:8443/dav/file', '/dav/file?secret=1',
                   '/dav/file#fragment', 'https:/dav/file']
        with tempfile.NamedTemporaryFile() as source, patch.object(self.client, '_open') as network:
            for path in invalid:
                for operation in (lambda: self.client.list_directory(path),
                                  lambda: self.client.download_file(path, self.target),
                                  lambda: self.client.upload_file(source.name, path),
                                  lambda: self.client.create_directory(path, 'new')):
                    with self.subTest(path=path):
                        with self.assertRaises(ValueError):
                            operation()
            network.assert_not_called()

    def test_invalid_configured_origins_never_receive_credentials(self):
        for server in ('https://u:p@example.org/dav/', 'https://example.org:bad/dav/',
                       'https://example.org/dav/../', 'https://example.org/dav/?secret=1',
                       'https://example.org/da\nv/', 'https://example.org/dav\\folder/'):
            with self.subTest(server=server), patch.object(self.client, '_open') as network:
                self.assertFalse(self.client.connect(server, 'synthetic', 'secret'))
                network.assert_not_called()

    def test_unicode_and_once_encoded_literal_percent_names(self):
        for path, expected in [('/dav/Grüße a.txt', 'Gr%C3%BC%C3%9Fe%20a.txt'),
                               ('/dav/%252F.txt', '%252F.txt'),
                               ('/dav/%25.txt', '%25.txt'),
                               ('/dav/a%23%3F.txt', 'a%23%3F.txt'),
                               ('Grüße/%252e%252e.txt', 'Gr%C3%BC%C3%9Fe/%252e%252e.txt')]:
            with self.subTest(path=path):
                self.assertEqual(self.client._resolve_url(path), self.client.server + expected)
        # Encoded equivalent base segments must not be appended twice.
        self.assertEqual(self.client._resolve_url('/%64av/file'),
                         'https://example.org:8443/%64av/file')
        for name, suffix in [('Grüße %.txt', 'Gr%C3%BC%C3%9Fe%20%25.txt/'),
                             ('%2F', '%252F/'), ('%2e%2e', '%252e%252e/')]:
            response = MagicMock()
            response.__enter__.return_value.status = 201
            with patch.object(self.client, '_open', return_value=response) as network:
                self.client.create_directory('/', name)
                self.assertEqual(network.call_args[0][0].full_url, self.client.server + suffix)

    def test_listing_excludes_outside_and_nonchild_entries(self):
        body = ('<d:multistatus xmlns:d="DAV:">' + ''.join(
            '<d:response><d:href>' + path + '</d:href></d:response>' for path in
            ('/dav/', '/outside/x', '/davish/x', '/dav/nested/file', '/dav/%2F', '/dav/Gr%C3%BC%C3%9Fe%20%252F.txt'))
            + '</d:multistatus>').encode()
        for root_alias in ('/', '', '/dav/', self.client.server):
            with patch.object(self.client, '_open', return_value=io.BytesIO(body)):
                items = self.client.list_directory(root_alias)
            self.assertEqual([item['name'] for item in items], ['Grüße %2F.txt'])

    def test_preview_limits_announced_unknown_and_false_lengths_and_cleans(self):
        content = b'x' * (main.TEXT_PREVIEW_LIMIT + 1)
        for length in (len(content), None, main.TEXT_PREVIEW_LIMIT):
            with self.subTest(length=length), patch.object(self.client, '_open', return_value=Response(content, length)), patch('webdav.os.replace') as publish:
                result = main.read_text_file('/dav/file.md', True)
                self.assertFalse(result['success'])
                self.assertEqual(result['message'], main.PREVIEW_SIZE_MESSAGE)
                self.assertNotIn('localFile', result)
                publish.assert_not_called()
                self.assertFalse(main._downloads)
                self.assertFalse(main._download_leases)
                self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
                self.assertFalse(list(Path(self.temp.name).rglob('download-*')))

    def test_preview_boundary_and_original_bytes_while_normal_download_is_unlimited(self):
        content = b'<b>literal</b>\r\n' + b'x' * (main.TEXT_PREVIEW_LIMIT - 16)
        self.assertEqual(len(content), main.TEXT_PREVIEW_LIMIT)
        with patch.object(self.client, '_open', return_value=Response(content, None)):
            result = main.read_text_file('/dav/file.md', True)
        self.assertTrue(result['success'])
        self.assertTrue(result['text'].startswith('<b>literal</b>\n'))
        self.assertEqual(Path(result['localFile']).read_bytes(), content)
        main.release_download(result['cacheRef'])
        bigger = content + b'large'
        with patch.object(self.client, '_open', return_value=Response(bigger, len(bigger))):
            result = main.download_file('/dav/file.md')
        self.assertTrue(result['success'])
        self.assertEqual(Path(result['localFile']).read_bytes(), bigger)
        main.release_download(result['cacheRef'])

    def test_bridge_errors_and_logs_never_expose_exception_details(self):
        secret = 'SYNTHETIC_PASSWORD Authorization: Basic SECRET https://private.example/dav/'
        errors = [RuntimeError(secret), ValueError(secret), OSError(secret),
                  urllib.error.URLError(secret), TimeoutError(secret),
                  urllib.error.HTTPError(secret, 500, secret, {}, None)]
        for error in errors:
            for method, operation in [('upload_file', lambda: main.upload_file('local', '/dav/file')),
                                      ('download_file', lambda: main.download_file('/dav/file')),
                                      ('list_directory', lambda: main.list_directory('/dav/')),
                                      ('create_directory', lambda: main.create_directory('/dav/', 'new'))]:
                output = io.StringIO()
                with self.subTest(error=type(error).__name__, method=method), patch.object(self.client, method, side_effect=error), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    result = operation()
                self.assertFalse(result['success'])
                self.assertTrue(result['message'])
                self.assertNotIn('SYNTHETIC', repr(result) + output.getvalue())
                self.assertNotIn('private.example', repr(result) + output.getvalue())
                self.assertEqual(output.getvalue(), '')

    def test_redirect_bridge_message_is_fixed_and_safe(self):
        with patch.object(self.client, 'download_file', side_effect=UnsafeRedirectError('secret-url')):
            self.assertEqual(main.download_file('/dav/file'),
                             {'success': False, 'message': main.REDIRECT_MESSAGE})
