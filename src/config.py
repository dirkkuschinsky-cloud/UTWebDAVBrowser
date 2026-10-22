"""Non-secret connection settings, scoped to this Click application."""
import json
import os
import stat
import tempfile
import urllib.parse


APP_ID = 'utwebdavbrowser.dkuschinsky'


def validate_server(server):
    if not isinstance(server, str):
        raise ValueError('Enter an HTTP or HTTPS WebDAV URL.')
    server = server.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in server):
        raise ValueError('The WebDAV URL contains invalid characters.')
    try:
        parts = urllib.parse.urlsplit(server)
        port = parts.port
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.netloc.endswith(':'):
            raise ValueError()
        if parts.username is not None or parts.password is not None or '@' in parts.netloc:
            raise ValueError('credentials')
        # A WebDAV base URL is not a token-bearing login URL. Reject rather than
        # silently strip query/fragment values which could contain credentials.
        if '?' in server or '#' in server:
            raise ValueError('credentials')
    except ValueError:
        raise ValueError('Use a valid HTTP(S) URL without embedded credentials, query or fragment.') from None
    return server


class Config:
    def __init__(self, directory=None):
        self.directory = directory or os.path.join(
            os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), APP_ID)
        self.filename = os.path.join(self.directory, 'connection.json')

    def _directory(self, create=False):
        if create:
            os.makedirs(self.directory, mode=0o700, exist_ok=True)
        try:
            mode = os.lstat(self.directory).st_mode
        except FileNotFoundError:
            return False
        if not stat.S_ISDIR(mode):
            raise ValueError('Invalid configuration directory.')
        os.chmod(self.directory, 0o700)
        return True

    def load(self):
        if not self._directory():
            return {'server': '', 'username': ''}
        try:
            fd = os.open(self.filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {'server': '', 'username': ''}
        with os.fdopen(fd, 'r', encoding='utf-8') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError('Invalid configuration file.')
            os.fchmod(source.fileno(), 0o600)
            data = source.read(65537)
        if len(data) > 65536:
            raise ValueError('Configuration too large.')
        values = json.loads(data)
        if (not isinstance(values, dict) or set(values) != {'server', 'username'}
                or not isinstance(values['username'], str) or not values['username']):
            raise ValueError('Invalid connection settings.')
        return {'server': validate_server(values['server']), 'username': values['username']}

    def save(self, server, username):
        values = {'server': validate_server(server), 'username': username}
        if not isinstance(username, str) or not username:
            raise ValueError('Invalid username.')
        self._directory(create=True)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.connection-', suffix='.tmp', dir=self.directory)
            with os.fdopen(fd, 'w', encoding='utf-8') as target:
                os.fchmod(target.fileno(), 0o600)
                json.dump(values, target, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.filename)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)

    def delete(self):
        if self._directory():
            try:
                os.unlink(self.filename)
            except FileNotFoundError:
                pass
