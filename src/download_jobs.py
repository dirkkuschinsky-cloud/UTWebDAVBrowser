"""One bounded, sequential download worker. No QML or networking implementation here."""
from translations import tr
import copy
import os
import shutil
import threading
import unicodedata
import uuid

from webdav import DownloadControl


class JobValidationError(ValueError):
    pass


def safe_name(name):
    if (not isinstance(name, str) or not name.strip() or name in ('.', '..')
            or any(c in name for c in ('/', '\\'))
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise JobValidationError(tr('Invalid file name.'))
    return name


class DownloadJobs:
    def __init__(self, prepare, download, release, cache_root):
        self.prepare_files = prepare
        self.download = download
        self.release = release
        self.cache_root = cache_root
        self.lock = threading.RLock()
        self.job = None
        self.thread = None

    @property
    def busy(self):
        with self.lock:
            return self.job is not None and self.job['state'] != 'finished'

    def owns(self, job_id):
        with self.lock:
            return bool(self.job and self.job['jobId'] == job_id)

    def prepare(self, parent, paths):
        with self.lock:
            if self.job is not None:
                return {'success': False, 'message': tr('Finish or discard the previous download job first.')}
            job_id = uuid.uuid4().hex
            self.control = DownloadControl()
            self.job = {'jobId': job_id, 'state': 'preparing', 'seq': 0, 'files': [], 'currentId': ''}
        try:
            # Network metadata validation runs on the PyOtherSide thread; GETs
            # only run after start(), which returns immediately to that thread.
            entries, worker_client = self.prepare_files(parent, paths)
            if not entries:
                raise JobValidationError(tr('Select valid files from the current directory.'))
            names = set()
            files = []
            for entry in entries:
                name = safe_name(entry['name'])
                key = unicodedata.normalize('NFC', name).casefold()
                if key in names:
                    raise JobValidationError(tr('Conflicting file names. Please correct the selection; files will not be renamed.'))
                names.add(key)
                files.append(dict(entry, fileId=uuid.uuid4().hex, state='queued', received=0,
                                  total=None, info=None, message=''))
            os.makedirs(self.cache_root(), exist_ok=True)
            known = sum(f['sizeHint'] for f in files if f['sizeHint'] is not None)
            try:
                free = shutil.disk_usage(self.cache_root()).free
            except OSError:
                free = None
            if free is not None and free < known + 1024 * 1024:
                raise JobValidationError(tr('There is not enough free space for the selected downloads.'))
            with self.lock:
                self.worker_client = worker_client
                if self.control.event.is_set():
                    for item in files:
                        item['state'] = 'cancelled'
                self.job.update(state='finished' if self.control.event.is_set() else 'ready', files=files, seq=1)
                return {'success': True, 'jobId': job_id}
        except Exception as error:
            with self.lock:
                self.job = None
            # Only our own validation messages may be shown, never exceptions
            # from HTTP libraries, paths, authentication or XML parsers.
            message = str(error) if type(error) is JobValidationError else tr('The selected files could not be checked.')
            return {'success': False, 'message': message}

    def start(self, job_id):
        with self.lock:
            if not self.owns(job_id) or self.job['state'] != 'ready':
                return {'success': False, 'message': tr('Unknown or already started download job.')}
            self.job['state'] = 'running'
            self.job['seq'] += 1
            self.thread = threading.Thread(target=self._run, args=(job_id,), daemon=True,
                                           name='WebDAV-download')
            try:
                self.thread.start()
            except Exception:
                for item in self.job['files']:
                    item.update(state='failed', message=tr('The download worker could not start.'))
                self.job.update(state='finished', seq=self.job['seq'] + 1)
                self.thread = None
                return {'success': False, 'message': tr('The download worker could not start.')}
            return {'success': True}

    def _run(self, job_id):
        try:
            for item in self.job['files']:
                with self.lock:
                    if self.control.event.is_set():
                        break
                    item['state'] = 'running'
                    self.job['currentId'] = item['fileId']
                    self.job['seq'] += 1
                def progress(received, total):
                    with self.lock:
                        item.update(received=received, total=total)
                        self.job['seq'] += 1
                result = self.download(item['path'], job_id, self.control, progress,
                                       self.worker_client, item['name'])
                with self.lock:
                    if result.get('success'):
                        item.update(state='succeeded', info=result)
                    elif result.get('cancelled') or self.control.event.is_set():
                        item.update(state='cancelled', message=tr('Download cancelled.'))
                    else:
                        item.update(state='failed', message=result.get('message', tr('Download failed.')))
                    self.job['seq'] += 1
        except Exception:
            # No raw worker exceptions/URLs are printed from background threads.
            pass
        finally:
            with self.lock:
                for item in self.job['files']:
                    if item['state'] in ('queued', 'running'):
                        item.update(state='cancelled' if self.control.event.is_set() else 'failed',
                                    message=tr('Download cancelled.') if self.control.event.is_set() else tr('The download worker stopped unexpectedly.'))
                self.job.update(state='finished', currentId='', seq=self.job['seq'] + 1)

    def cancel(self, job_id):
        with self.lock:
            if not self.owns(job_id):
                return {'success': False}
            self.control.cancel()
            if self.job['state'] == 'ready':
                for item in self.job['files']:
                    item['state'] = 'cancelled'
                self.job['state'] = 'finished'
            elif self.job['state'] != 'finished':
                self.job['state'] = 'cancelling'
            self.job['seq'] += 1
            return {'success': True}

    def status(self, job_id):
        with self.lock:
            if not self.owns(job_id):
                return {'success': False}
            snapshot = copy.deepcopy(self.job)
        # Paths are only carried by cache infos for the existing export API.
        for item in snapshot['files']:
            item.pop('path', None)
            item.pop('sizeHint', None)
        return dict(snapshot, success=True)

    def discard(self, job_id):
        with self.lock:
            if not self.owns(job_id) or self.job['state'] != 'finished':
                return {'success': False, 'message': tr('Wait until the download has stopped.')}
            # No new worker may start before the previous worker really exited.
            if self.thread and self.thread.is_alive():
                return {'success': False, 'message': tr('The worker is finishing. Please try again.')}
            infos = [item['info'] for item in self.job['files'] if item['info']]
            self.job = None
            self.thread = None
        errors = []
        for info in infos:
            result = self.release(info['cacheRef'])
            if not result['success']:
                errors.append(result['message'])
        return {'success': True, 'warning': '\n'.join(errors)}
