"""Real PyOtherSide bridge smoke fixture. All HTTP traffic is simulated."""
import io
import os
import tempfile
import time
import urllib.request

_state = {}


def setup():
    _state['temp'] = tempfile.TemporaryDirectory(prefix='utwebdav-batch-smoke-')
    _state['old_cache'] = os.environ.get('XDG_CACHE_HOME')
    os.environ['XDG_CACHE_HOME'] = _state['temp'].name
    import main
    _state['main'] = main
    _state['listing'] = main.client.list_directory
    main.client.server = 'https://example.invalid/dav/'
    main.client.list_directory = lambda path: [
        {'path': '/dav/test/' + name, 'name': name, 'isDirectory': False,
         'resourceTypeKnown': True, 'size': str(4 * 1024 * 1024)} for name in ('large', 'next')]
    from webdav import WebDavClient
    _state['open'] = WebDavClient._open
    _state['gets'] = 0
    _state['reads'] = 0
    class Response(io.BytesIO):
        status = 200
        headers = {'Content-Length': str(4 * 1024 * 1024)}
        def read(self, size=-1):
            assert 0 < size <= 65536
            _state['reads'] += 1
            time.sleep(0.05)
            return super().read(size)
    def get(client, request, **kwargs):
        assert request.method == 'GET'
        _state['gets'] += 1
        return Response(b'x' * (4 * 1024 * 1024))
    WebDavClient._open = get
    return True


def cleanup():
    from pathlib import Path
    main = _state['main']
    result = {'gets': _state['gets'], 'reads': _state['reads'],
              'partial': len(list(Path(_state['temp'].name).rglob('*.part'))),
              'leases': len(main._download_leases)}
    from webdav import WebDavClient
    WebDavClient._open = _state['open']
    main.client.list_directory = _state['listing']
    if _state['old_cache'] is None:
        os.environ.pop('XDG_CACHE_HOME', None)
    else:
        os.environ['XDG_CACHE_HOME'] = _state['old_cache']
    _state['temp'].cleanup()
    return result
