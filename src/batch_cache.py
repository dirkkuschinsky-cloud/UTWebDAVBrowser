"""Private batch directories with process leases for safe crash recovery."""
import fcntl
import os
import re
import shutil
import stat
import threading
import uuid


class BatchCache:
    def __init__(self):
        self.owners = {}
        self.lock = threading.RLock()

    def create(self, root):
        os.makedirs(root, exist_ok=True)
        directory = os.path.join(root, 'batch-' + uuid.uuid4().hex)
        os.mkdir(directory, 0o700)
        fd = None
        try:
            fd = os.open(os.path.join(directory, '.owner'), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.lock:
                self.owners[directory] = fd
            return directory
        except BaseException:
            if fd is not None:
                os.close(fd)
            shutil.rmtree(directory)
            raise

    def forget(self, directory):
        with self.lock:
            fd = self.owners.pop(directory, None)
            if fd is not None:
                os.close(fd)

    def cleanup(self, root):
        # Do not touch legacy preview/PDF downloads, symlinks or active jobs.
        try:
            names = os.listdir(root)
        except OSError:
            return
        for name in names:
            if not re.fullmatch(r'batch-[0-9a-f]{32}', name):
                continue
            directory = os.path.join(root, name)
            fd = None
            try:
                with self.lock:
                    if directory in self.owners:
                        continue
                if not stat.S_ISDIR(os.lstat(directory).st_mode):
                    continue
                fd = os.open(os.path.join(directory, '.owner'), os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    continue
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                shutil.rmtree(directory)
            except OSError:
                pass
            finally:
                if fd is not None:
                    os.close(fd)
