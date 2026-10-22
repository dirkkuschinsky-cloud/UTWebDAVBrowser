import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from webdav import WebDavClient


class UploadTests(unittest.TestCase):
    def test_streamed_bytes_length_and_progress(self):
        for content in (b'', b'abc', b'x' * 300000):
            with self.subTest(size=len(content)), tempfile.NamedTemporaryFile() as source:
                source.write(content)
                source.flush()
                client = WebDavClient()
                client.server = 'https://example.org/dav/'
                progress = []
                def send(request, **kwargs):
                    blocks = list(request.data)
                    self.assertTrue(all(len(block) <= 65536 for block in blocks))
                    self.assertEqual(b''.join(blocks), content)
                    self.assertEqual(request.get_header('Content-length'), str(len(content)))
                    response = MagicMock()
                    response.__enter__.return_value.status = 201
                    return response
                with patch('webdav.WebDavClient._open', side_effect=send):
                    self.assertTrue(client.upload_file(source.name, '/dav/BSW/file',
                                                      lambda sent, total: progress.append((sent, total))))
                self.assertEqual(progress[0], (0, len(content)))
                self.assertEqual(progress[-1], (len(content), len(content)))
                self.assertEqual(progress, sorted(progress))

    def test_qml_progress_and_errors(self):
        bridge = types.SimpleNamespace(send=MagicMock())
        with patch.dict(sys.modules, {'pyotherside': bridge}):
            def upload(local, remote, progress):
                progress(10, 20)
                return True
            with patch.object(main.client, 'upload_file', side_effect=upload):
                self.assertEqual(main.upload_file('local', '/file'), {'success': True})
                bridge.send.assert_called_once_with('uploadProgress', 10, 20)
            for status in (401, 403, 404, 409, 413, 500, 507):
                with self.subTest(status=status), patch.object(main.client, 'upload_file',
                        side_effect=urllib.error.HTTPError('https://example.org', status, 'error', {}, None)):
                    result = main.upload_file('local', '/file')
                    self.assertFalse(result['success'])
                    self.assertEqual(result['status'], status)
                    self.assertTrue(result['message'])
            for error in (TimeoutError(), urllib.error.URLError('offline'), FileNotFoundError()):
                with self.subTest(error=error), patch.object(main.client, 'upload_file', side_effect=error):
                    result = main.upload_file('local', '/file')
                    self.assertFalse(result['success'])
                    self.assertTrue(result['message'])
