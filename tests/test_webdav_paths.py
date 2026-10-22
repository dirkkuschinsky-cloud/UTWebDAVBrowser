import sys
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from webdav import WebDavClient


class WebDavPathTests(unittest.TestCase):
    def setUp(self):
        self.client = WebDavClient()
        self.client.server = 'https://example.org:8443/custom/dav/'

    def test_root_and_directory_paths(self):
        cases = {
            '': '',
            '/': '',
            'BSW/file.json': 'BSW/file.json',
            '/custom/dav/BSW/file.json': 'BSW/file.json',
            '/custom/dav/BSW/deeper/file.json': 'BSW/deeper/file.json',
            '/custom/dav/': '',
            '/custom/dav/B%C3%BCro/a%20b%23%25.json': 'B%C3%BCro/a%20b%23%25.json',
            '/custom/dav/Büro/a b.json': 'B%C3%BCro/a%20b.json',
        }
        for path, suffix in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.client._resolve_url(path), self.client.server + suffix)

    def test_absolute_href_and_other_origin(self):
        url = self.client.server + 'BSW/file.json'
        self.assertEqual(self.client._resolve_url(url), url)
        with self.assertRaises(ValueError):
            self.client._resolve_url('https://other.example/file.json')

    def test_server_without_base_path(self):
        self.client.server = 'https://example.org/'
        self.assertEqual(self.client._resolve_url('/BSW/file.json'),
                         'https://example.org/BSW/file.json')

    def test_magenta_upload_regression(self):
        self.client.server = 'https://magentacloud.de/remote.php/webdav/'
        self.assertEqual(self.client._resolve_url('/remote.php/webdav/BSW/file.json'),
                         self.client.server + 'BSW/file.json')

    def test_operations_use_resolved_url(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 201
        response.read.return_value = b'<d:multistatus xmlns:d="DAV:"/>'
        with patch('webdav.WebDavClient._open', return_value=response) as request:
            self.client.list_directory('/custom/dav/BSW/')
            self.assertEqual(request.call_args[0][0].full_url, self.client.server + 'BSW/')
            self.assertEqual(request.call_args[0][0].method, 'PROPFIND')
            response.status = 200
            response.headers = {'Content-Length': '4'}
            response.read.side_effect = io.BytesIO(b'test').read
            with tempfile.TemporaryDirectory() as directory:
                self.client.download_file('/custom/dav/BSW/file.json', directory + '/file.json')
            response.status = 201
            self.assertEqual(request.call_args[0][0].full_url, self.client.server + 'BSW/file.json')
            self.assertEqual(request.call_args[0][0].method, 'GET')
            with tempfile.NamedTemporaryFile() as source:
                source.write(b'test')
                source.flush()
                self.assertTrue(self.client.upload_file(source.name, '/custom/dav/BSW/file.json'))

            self.assertEqual(request.call_args[0][0].full_url, self.client.server + 'BSW/file.json')
            self.assertEqual(request.call_args[0][0].method, 'PUT')
            self.assertEqual(request.call_args[0][0].get_header('Content-length'), '4')


if __name__ == '__main__':
    unittest.main()
