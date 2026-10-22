import contextlib
import errno
import io
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from batch_cache import BatchCache
from download_jobs import DownloadJobs, safe_name
from webdav import DownloadControl, DownloadCancelled


class Response(io.BytesIO):
    status = 200
    def __init__(self, content, total=None):
        super().__init__(content)
        self.headers = {} if total is None else {'Content-Length': str(total)}
    def read(self, size=-1):
        assert 0 < size <= 65536
        return super().read(size)


class DownloadJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'XDG_CACHE_HOME': self.temp.name})
        self.env.start(); self.addCleanup(self.env.stop)
        bridge = patch.dict(sys.modules, {'pyotherside': types.SimpleNamespace(send=lambda *args: None)})
        bridge.start(); self.addCleanup(bridge.stop)
        self.old = main._jobs
        main._jobs = DownloadJobs(main._prepare_job_files,
            lambda path, jid, control, progress, client, name: main.download_file(path, jid, control, progress, client, name),
            main.release_download, main._cache_root)
        self.addCleanup(self.restore)
        self.server = patch.object(main.client, 'server', 'https://example.org/dav/')
        self.server.start(); self.addCleanup(self.server.stop)
        self.paths = ['/dav/parent/one', '/dav/parent/two', '/dav/parent/three']
        self.items = [{'path': path, 'name': path.rsplit('/', 1)[1], 'size': '3',
                       'isDirectory': False, 'resourceTypeKnown': True, 'resourceId': ''} for path in self.paths]
        listing = patch.object(main.client, 'list_directory', side_effect=lambda parent: self.items)
        listing.start(); self.addCleanup(listing.stop)

    def restore(self):
        if main._jobs.job:
            main._jobs.cancel(main._jobs.job['jobId'])
        if main._jobs.thread:
            main._jobs.thread.join(3)
        for reference in list(main._download_leases):
            main.release_download(reference)
        main._jobs = self.old

    def prepare(self, paths=None):
        result = main.prepare_download_job('/dav/parent/', self.paths if paths is None else paths)
        self.assertTrue(result['success'], result)
        return result['jobId']

    def wait(self):
        main._jobs.thread.join(3)
        self.assertFalse(main._jobs.thread.is_alive())
        return main.download_job_status(main._jobs.job['jobId'])

    def test_three_sequential_successes_and_ids(self):
        active = 0
        maximum = 0
        seen = []
        def send(request, **kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            seen.append(request.full_url)
            response = Response(b'abc', 3)
            original = response.close
            def close():
                nonlocal active
                active -= 1
                original()
            response.close = close
            return response
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', side_effect=send):
            self.assertTrue(main.start_download_job(jid)['success'])
            state = self.wait()
        self.assertEqual(maximum, 1)
        self.assertEqual(seen, ['https://example.org' + path for path in self.paths])
        self.assertEqual([f['state'] for f in state['files']], ['succeeded'] * 3)
        self.assertEqual(len({f['fileId'] for f in state['files']}), 3)
        for f in state['files']:
            self.assertNotEqual(f['fileId'], jid)
            self.assertEqual(Path(f['info']['localFile']).read_bytes(), b'abc')
            self.assertEqual(f['total'], 3)
            self.assertEqual(f['received'], 3)
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
        self.assertTrue(main.discard_download_job(jid)['success'])
        self.assertFalse(main._download_leases)

    def test_failure_second_continues_third(self):
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', side_effect=[Response(b'one', 3), ConnectionResetError('SECRET'), Response(b'end', 3)]):
            main.start_download_job(jid)
            state = self.wait()
        self.assertEqual([f['state'] for f in state['files']], ['succeeded', 'failed', 'succeeded'])
        self.assertNotIn('SECRET', str(state))
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_cancel_during_blocked_read_stops_remaining(self):
        entered, unblock = threading.Event(), threading.Event()
        response = Response(b'x' * 200000, 200000)
        read = response.read
        def blocking(size):
            entered.set()
            self.assertTrue(unblock.wait(2))
            return read(size)
        response.read = blocking
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', return_value=response) as send:
            main.start_download_job(jid)
            self.assertTrue(entered.wait(2))
            self.assertTrue(main.cancel_download_job(jid)['success'])
            self.assertEqual(main.download_job_status(jid)['state'], 'cancelling')
            self.assertFalse(main.start_download_job(jid)['success'])
            unblock.set()
            state = self.wait()
            self.assertEqual(send.call_count, 1)
        self.assertEqual([f['state'] for f in state['files']], ['cancelled'] * 3)
        self.assertFalse(main._download_leases)
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
        self.assertFalse(list(Path(main._cache_root()).glob('batch-*')))

    def test_cancel_immediately_before_atomic_publish(self):
        jid = self.prepare(self.paths[:1])
        def fsync(fd):
            main.cancel_download_job(jid)
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)), patch('webdav.os.fsync', side_effect=fsync), patch('webdav.os.replace') as publish:
            main.start_download_job(jid)
            state = self.wait()
            publish.assert_not_called()
        self.assertEqual(state['files'][0]['state'], 'cancelled')
        self.assertFalse(main._download_leases)
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_completed_before_cancel_is_retained(self):
        original = main._jobs.download
        def finish_then_cancel(*args):
            result = original(*args)
            main.cancel_download_job(args[1])
            return result
        main._jobs.download = finish_then_cancel
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)) as send:
            main.start_download_job(jid)
            state = self.wait()
            self.assertEqual(send.call_count, 1)
        self.assertEqual([f['state'] for f in state['files']], ['succeeded', 'cancelled', 'cancelled'])
        self.assertTrue(Path(state['files'][0]['info']['localFile']).is_file())

    def test_ready_cancel_and_stale_job_ids(self):
        jid = self.prepare()
        self.assertFalse(main.start_download_job('stale')['success'])
        self.assertFalse(main.cancel_download_job('stale')['success'])
        self.assertFalse(main.download_job_status('stale')['success'])
        main.cancel_download_job(jid)
        self.assertFalse(main.start_download_job(jid)['success'])
        main.discard_download_job(jid)
        other = self.prepare()
        self.assertNotEqual(jid, other)
        self.assertFalse(main.download_job_status(jid)['success'])

    def test_busy_guards_and_no_second_job(self):
        jid = self.prepare()
        with patch('webdav.WebDavClient._open') as send:
            self.assertFalse(main.prepare_download_job('/dav/parent/', self.paths)['success'])
            calls = [lambda: main.connect('https://example.org/', 'u', 'p'),
                     lambda: main.list_directory('/'), lambda: main.upload_file('local', '/remote'),
                     lambda: main.create_directory('/', 'folder'), lambda: main.prepare_delete('/', '/dav/a'),
                     lambda: main.delete_resource('token'), lambda: main.download_file('/dav/a'),
                     lambda: main.download_file('/dav/a', jid),
                     lambda: main.acquire_download({'remotePath': '/dav/a'}),
                     lambda: main.acquire_batch_exports([])]
            for call in calls:
                self.assertFalse(call()['success'])
            send.assert_not_called()
        main.cancel_download_job(jid)

    def test_duplicate_paths_aliases_and_resource_ids(self):
        self.items.append(dict(self.items[0], path='/dav/parent/%6fne'))
        jid = self.prepare([self.paths[0], '/dav/parent/%6fne', self.paths[0]])
        self.assertEqual(len(main.download_job_status(jid)['files']), 1)
        main.cancel_download_job(jid); main.discard_download_job(jid)
        self.items[0]['resourceId'] = self.items[1]['resourceId'] = 'urn:uuid:same'
        jid = self.prepare(self.paths[:2])
        self.assertEqual(len(main.download_job_status(jid)['files']), 1)

    def test_foreign_traversal_directory_and_unknown_type_rejected(self):
        for path in ('/dav/other/file', '/dav/parent/../file', '/dav/parent/%2f',
                     '/dav/parent/%2e%2e', 'https://other.org/dav/parent/one', '/dav/'):
            self.assertFalse(main.prepare_download_job('/dav/parent/', [path])['success'])
        for changes in ({'isDirectory': True}, {'resourceTypeKnown': False}):
            self.items[0].update(changes)
            self.assertFalse(main.prepare_download_job('/dav/parent/', self.paths[:1])['success'])
            self.items[0].update(isDirectory=False, resourceTypeKnown=True)

    def test_name_conflicts_without_renaming(self):
        for first, second in (('A', 'a'), ('Grüße', 'Grüße'), ('ä', 'a\u0308')):
            self.items[0]['path'] = '/dav/parent/' + first
            self.items[1]['path'] = '/dav/parent/' + second
            result = main.prepare_download_job('/dav/parent/', [self.items[0]['path'], self.items[1]['path']])
            if first == second:
                self.assertTrue(result['success'])  # Same checked resource is deduplicated.
                main.cancel_download_job(result['jobId']); main.discard_download_job(result['jobId'])
            else:
                self.assertFalse(result['success'], result)
        for name in ('', '.', '..', 'a/b', 'a\\b', '\x00', '\n'):
            with self.assertRaises(ValueError): safe_name(name)

    def test_unicode_percent_and_unknown_length_stream(self):
        path = '/dav/parent/Gr%C3%BC%C3%9Fe%20%252F%23.txt'
        self.items = [dict(self.items[0], path=path, size='')]
        jid = self.prepare([path])
        with patch('webdav.WebDavClient._open', return_value=Response(b'bytes', None)) as send:
            main.start_download_job(jid)
            state = self.wait()
        info = state['files'][0]['info']
        self.assertEqual(info['fileName'], 'Grüße %2F#.txt')
        self.assertEqual(Path(info['localFile']).read_bytes(), b'bytes')
        self.assertIsNone(state['files'][0]['total'])
        self.assertTrue(send.call_args.args[0].full_url.endswith('Gr%C3%BC%C3%9Fe%20%252F%23.txt'))

    def test_preflight_and_unknown_disk_usage(self):
        with patch('download_jobs.shutil.disk_usage', return_value=types.SimpleNamespace(free=0)):
            result = main.prepare_download_job('/dav/parent/', self.paths)
        self.assertFalse(result['success'])
        with patch('download_jobs.shutil.disk_usage', side_effect=OSError()):
            jid = self.prepare()
        self.assertTrue(jid)

    def test_partial_write_and_space_failures_continue_without_files(self):
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', return_value=Response(b'abc', 3)), patch('webdav.shutil.disk_usage', return_value=types.SimpleNamespace(free=0)):
            main.start_download_job(jid)
            state = self.wait()
        self.assertEqual([f['state'] for f in state['files']], ['failed'] * 3)
        self.assertFalse(main._download_leases)
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_empty_files_and_export_without_preflight_information(self):
        self.items[0]['size'] = '0'
        jid = self.prepare(self.paths[:1])
        with patch('webdav.WebDavClient._open', return_value=Response(b'', 0)):
            main.start_download_job(jid)
            state = self.wait()
        self.assertEqual(state['files'][0]['state'], 'succeeded')
        self.assertEqual(state['files'][0]['total'], 0)
        with patch('main.shutil.disk_usage', side_effect=OSError()):
            export = main.acquire_batch_exports([state['files'][0]['info']])
        self.assertTrue(export['success'])
        for info in export['files']:
            main.release_download(info['cacheRef'])

    def test_flush_failure_cleans_files_and_continues(self):
        jid = self.prepare()
        with patch('webdav.WebDavClient._open', side_effect=lambda *args, **kwargs: Response(b'abc', 3)) as sends, patch(
                'webdav.os.fsync', side_effect=OSError(errno.ENOSPC, 'SECRET')):
            main.start_download_job(jid)
            state = self.wait()
        self.assertEqual(sends.call_count, 3)
        self.assertEqual([f['state'] for f in state['files']], ['failed'] * 3)
        self.assertNotIn('SECRET', str(state))
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
        self.assertFalse(main._download_leases)

    def completed_infos(self):
        jid = self.prepare(self.paths[:2])
        with patch('webdav.WebDavClient._open', side_effect=[Response(b'one', 3), Response(b'two', 3)]):
            main.start_download_job(jid)
            state = self.wait()
        return jid, [f['info'] for f in state['files']]

    def test_export_copies_survive_move_and_release_once(self):
        jid, infos = self.completed_infos()
        with patch('webdav.WebDavClient._open') as network:
            export = main.acquire_batch_exports(infos)
            self.assertTrue(export['success'], export)
            self.assertEqual(len(export['files']), 2)
            for original, copied in zip(infos, export['files']):
                self.assertNotEqual(original['cacheRef'], copied['cacheRef'])
                self.assertNotEqual(original['localFile'], copied['localFile'])
                self.assertEqual(Path(original['localFile']).read_bytes(), Path(copied['localFile']).read_bytes())
                Path(copied['localFile']).unlink()  # Simulated receiver moves the export file.
                self.assertTrue(main.release_download(copied['cacheRef'])['success'])
                self.assertFalse(main.release_download(copied['cacheRef'])['success'])
                self.assertTrue(Path(original['localFile']).exists())
            again = main.acquire_batch_exports(infos)
            self.assertTrue(again['success'])
            for f in again['files']: main.release_download(f['cacheRef'])
            network.assert_not_called()
        main.discard_download_job(jid)
        self.assertFalse(main._download_leases)

    def test_export_error_leaves_originals_and_cleans_partial_copies(self):
        jid, infos = self.completed_infos()
        with patch('main.os.fsync', side_effect=OSError(errno.ENOSPC, 'SECRET')):
            result = main.acquire_batch_exports(infos)
        self.assertFalse(result['success'])
        self.assertNotIn('SECRET', str(result))
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
        self.assertEqual(len(main._download_leases), 2)
        for info in infos: self.assertTrue(Path(info['localFile']).is_file())
        self.assertFalse(main.acquire_batch_exports([{'cacheRef': 'fake', 'localFile': '/etc/passwd'}])['success'])
        self.assertFalse(main.acquire_batch_exports([infos[0], infos[0]])['success'])
        with patch('main.shutil.disk_usage', return_value=types.SimpleNamespace(free=0)):
            self.assertFalse(main.acquire_batch_exports(infos)['success'])

    def test_orphan_recovery_skips_live_and_legacy_and_symlinks(self):
        cache = BatchCache()
        directory = cache.create(self.temp.name)
        Path(directory, 'file.part').write_bytes(b'partial')
        other = BatchCache()
        other.cleanup(self.temp.name)
        self.assertTrue(Path(directory).exists())
        cache.forget(directory)
        legacy = Path(self.temp.name, 'download-pinned-pdf'); legacy.mkdir()
        outside = Path(self.temp.name, 'outside'); outside.mkdir()
        Path(self.temp.name, 'batch-' + 'a' * 32).symlink_to(outside, target_is_directory=True)
        other.cleanup(self.temp.name)
        self.assertFalse(Path(directory).exists())
        self.assertTrue(legacy.exists())
        self.assertTrue(outside.exists())

    def test_sanitized_preparation_errors(self):
        with patch.object(main.client, 'list_directory', side_effect=ValueError('https://u:SECRET@example.org')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main.prepare_download_job('/dav/parent/', self.paths)
            self.assertFalse(result['success'])
            self.assertNotIn('SECRET', str(result) + output.getvalue())
