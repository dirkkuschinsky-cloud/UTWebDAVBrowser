import errno
import io
import os
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


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, length):
        super().__init__(data)
        self.headers = {} if length is None else {'Content-Length': str(length)}
        self.read_sizes = []

    def read(self, size=-1):
        assert 0 < size <= 65536, 'Download must use bounded reads'
        self.read_sizes.append(size)
        return super().read(size)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = str(Path(self.directory.name) / 'Grüße %.txt')
        self.client = WebDavClient()
        self.client.server = 'https://example.org/dav/'
        server = patch.object(main.client, 'server', self.client.server)
        server.start()
        self.addCleanup(server.stop)
        self.bridge = types.SimpleNamespace(send=MagicMock())
        self.modules = patch.dict(sys.modules, {'pyotherside': self.bridge})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.env = patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(main._downloads.clear)
        self.addCleanup(main._download_leases.clear)

    def test_atomic_stream_known_unknown_and_empty(self):
        for data, length in [(b'', 0), (b'abc', None), (b'x' * 200000, 200000)]:
            with self.subTest(length=length):
                Path(self.target).unlink(missing_ok=True)
                progress = []
                response = Response(data, length)
                real_replace = os.replace
                def replace(source, target):
                    self.assertTrue(source.endswith('.part'))
                    self.assertFalse(Path(target).exists())
                    self.assertEqual(Path(source).read_bytes(), data)
                    real_replace(source, target)
                with patch('webdav.WebDavClient._open', return_value=response), patch('webdav.os.replace', side_effect=replace) as rename:
                    self.assertEqual(self.client.download_file('/dav/file', self.target,
                        lambda count, total: progress.append((count, total))), len(data))
                self.assertEqual(Path(self.target).read_bytes(), data)
                self.assertFalse(Path(self.target + '.part').exists())
                self.assertEqual(progress[-1], (len(data), length))
                rename.assert_called_once()

    def test_truncated_and_oversized_responses_remove_partial(self):
        for length in (2, 100):
            with self.subTest(length=length), patch('webdav.WebDavClient._open', return_value=Response(b'abc', length)):
                with self.assertRaises(ValueError):
                    self.client.download_file('/dav/file', self.target)
                self.assertFalse(Path(self.target).exists())
                self.assertFalse(Path(self.target + '.part').exists())

    def test_preflight_full_disk(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)), patch('webdav.shutil.disk_usage', return_value=types.SimpleNamespace(free=0)):
            with self.assertRaises(OSError) as error:
                self.client.download_file('/dav/file', self.target)
            self.assertEqual(error.exception.errno, errno.ENOSPC)
            self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_write_flush_and_rename_failures(self):
        for operation in ('write', 'flush', 'rename'):
            with self.subTest(operation=operation):
                real_open = open
                def open_target(*args, **kwargs):
                    target = real_open(*args, **kwargs)
                    proxy = MagicMock(wraps=target)
                    proxy.__enter__.return_value = proxy
                    proxy.__exit__.side_effect = lambda *args: target.close()
                    if operation != 'rename':
                        getattr(proxy, operation).side_effect = OSError(errno.ENOSPC, 'full')
                    return proxy
                with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)), patch('builtins.open', side_effect=open_target), patch('webdav.os.replace', side_effect=OSError(errno.EIO, 'rename failed')):
                    with self.assertRaises(OSError):
                        self.client.download_file('/dav/file', self.target)
                self.assertFalse(Path(self.target).exists())
                self.assertFalse(Path(self.target + '.part').exists())

    def test_disconnect_removes_partial(self):
        response = Response(b'abc', 100)
        response.read = MagicMock(side_effect=[b'abc', ConnectionResetError()])
        with patch('webdav.WebDavClient._open', return_value=response):
            with self.assertRaises(ConnectionResetError):
                self.client.download_file('/dav/file', self.target)
        self.assertFalse(Path(self.target + '.part').exists())

    def test_existing_destination_survives_failure(self):
        Path(self.target).write_bytes(b'existing')
        with patch('webdav.WebDavClient._open', return_value=Response(b'bad', 100)):
            with self.assertRaises(ValueError):
                self.client.download_file('/dav/file', self.target)
        self.assertEqual(Path(self.target).read_bytes(), b'existing')

    def test_main_success_export_lifetime_and_release(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'data', 4)):
            result = main.download_file('/dav/Gr%C3%BC%C3%9Fe%20%25.txt')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['fileName'], 'Grüße %.txt')
        self.assertTrue(Path(result['localFile']).exists())
        self.assertTrue(result['localUrl'].endswith('Gr%C3%BC%C3%9Fe%20%25.txt'))
        self.bridge.send.assert_called_with('downloadProgress', 4, 4)
        self.assertTrue(main.release_download(result['localUrl'])['success'])
        self.assertFalse(Path(result['localFile']).parent.exists())
        self.assertFalse(main.release_download('/arbitrary/file')['success'])

    def test_main_failures_never_return_file_and_cleanup(self):
        for error in (OSError(errno.ENOSPC, 'full'), TimeoutError(),
                      urllib.error.HTTPError('url', 404, 'missing', {}, None), ValueError('short')):
            with self.subTest(error=error), patch.object(main.client, 'download_file', side_effect=error):
                result = main.download_file('/dav/file')
                self.assertFalse(result['success'])
                self.assertNotIn('localFile', result)
                self.assertEqual(list(Path(self.directory.name).rglob('download-*')), [])

    def test_text_preview_keeps_contract_and_releases_file(self):
        content = 'Grüße'.encode('utf-8')
        with patch('webdav.WebDavClient._open', return_value=Response(content, len(content))):
            self.assertEqual(main.read_text_file('/dav/file.txt'), {'success': True, 'text': 'Grüße'})
        self.assertFalse(main._downloads)
        self.assertEqual(list(Path(self.directory.name).rglob('download-*')), [])

    def test_disk_usage_unavailable_still_downloads(self):
        with patch('webdav.shutil.disk_usage', side_effect=OSError()), patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)):
            self.client.download_file('/dav/file', self.target)
        self.assertEqual(Path(self.target).read_bytes(), b'abc')

    def test_repeated_saves_reuse_cache_and_release_each_lease_once(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'original', 8)):
            preview = main.download_file('/dav/file.txt')
        with patch.object(main.client, 'download_file') as network:
            for unused in range(3):
                export = main.acquire_download(preview)
                self.assertNotEqual(export['cacheRef'], preview['cacheRef'])
                self.assertEqual(export['localFile'], preview['localFile'])
                self.assertTrue(main.release_download(export['cacheRef'])['success'])
                self.assertFalse(main.release_download(export['cacheRef'])['success'])
                self.assertTrue(Path(preview['localFile']).exists())
            network.assert_not_called()
        self.assertTrue(main.release_download(preview['cacheRef'])['success'])
        self.assertFalse(Path(preview['localFile']).exists())
        self.assertFalse(main._download_leases)

    def test_preview_closing_during_export_retains_file(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)):
            preview = main.download_file('/dav/file.png')
        export = main.acquire_download(preview)
        main.release_download(preview['cacheRef'])
        self.assertTrue(Path(export['localFile']).exists())
        self.assertFalse(main.release_download(preview['cacheRef'])['success'])
        self.assertTrue(Path(export['localFile']).exists())
        main.release_download(export['cacheRef'])
        self.assertFalse(Path(export['localFile']).exists())

    def test_text_preview_exports_original_bytes(self):
        content = b'\xff\xfeInvalid UTF-8\r\nline two\rline three\n\x00'
        with patch('webdav.WebDavClient._open', return_value=Response(content, len(content))):
            preview = main.read_text_file('/dav/original.txt', True)
        self.assertIn('\ufffd', preview['text'])
        with patch.object(main.client, 'download_file') as network:
            for unused in range(2):
                export = main.acquire_download(preview)
                self.assertEqual(Path(export['localFile']).read_bytes(), content)
                main.release_download(export['cacheRef'])
            network.assert_not_called()
        main.release_download(preview['cacheRef'])
        self.assertFalse(Path(preview['localFile']).exists())

    def test_pdf_pin_survives_preview_and_export_release(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'%PDF', 4)):
            preview = main.download_file('/dav/file.pdf')
        self.assertTrue(main.pin_download(preview['cacheRef'])['success'])
        export = main.acquire_download(preview)
        main.release_download(preview['cacheRef'])
        main.release_download(export['cacheRef'])
        self.assertTrue(Path(preview['localFile']).exists())
        self.assertFalse(main._download_leases)
        self.assertTrue(main._downloads[preview['localFile']]['pinned'])

    def test_missing_cache_uses_existing_streaming_downloader(self):
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)):
            preview = main.download_file('/dav/file.txt')
        Path(preview['localFile']).unlink()
        with patch('webdav.WebDavClient._open', return_value=Response(b'new', 3)) as network:
            export = main.acquire_download(preview)
        network.assert_called_once()
        self.assertTrue(export['success'])
        self.assertEqual(Path(export['localFile']).read_bytes(), b'new')
        main.release_download(preview['cacheRef'])
        main.release_download(export['cacheRef'])
        self.assertFalse(main._download_leases)

    def test_text_read_error_releases_reference(self):
        real_open = open
        def fail_text(*args, **kwargs):
            if len(args) > 1 and args[1] == 'rb':
                raise OSError('read failed')
            return real_open(*args, **kwargs)
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)), patch('builtins.open', side_effect=fail_text):
            result = main.read_text_file('/dav/file.txt', True)
        self.assertFalse(result['success'])
        self.assertFalse(main._downloads)
        self.assertFalse(main._download_leases)
