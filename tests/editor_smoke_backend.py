"""No real network: exercise the actual PyOtherSide editor boundary."""
import io
import urllib.parse
from xml.sax.saxutils import escape

class Response(io.BytesIO):
    def __init__(self, status, body=b'', headers=None):
        super().__init__(body)
        self.status, self.headers = status, headers or {}


def setup():
    import main
    main.client.server = 'https://example.org/dav/'
    state = {'data': b'\xef\xbb\xbfGr\xc3\xbc\xc3\x9fe\r\n', 'etag': '"v1"', 'puts': 0}
    def server(req):
        path = urllib.parse.urlsplit(req.full_url).path
        if req.method == 'PROPFIND':
            kind = '<d:collection/>' if path == '/dav/' else ''
            body = ('<d:multistatus xmlns:d="DAV:"><d:response><d:href>' + escape(path) +
                '</d:href><d:propstat><d:prop><d:resourcetype>' + kind +
                '</d:resourcetype><d:getetag>' + escape(state['etag']) +
                '</d:getetag><d:resource-id><d:href>urn:uuid:fixed</d:href></d:resource-id>' +
                '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>')
            return Response(207, body.encode())
        if req.method == 'GET':
            return Response(200, state['data'], {'ETag': state['etag']})
        if req.method == 'PUT':
            assert req.get_header('If-match') == state['etag']
            state.update(data=req.data, etag='"v2"', puts=state['puts']+1)
            return Response(204, headers={'ETag': state['etag']})
        raise AssertionError()
    main.client._delete_open = server
    globals()['state'] = state
    return {'success': True}


def verify():
    import main
    return state['puts'] == 1 and state['data'] == b'\xef\xbb\xbfGr\xc3\xbc\xc3\x9fe\r\nNeu\r\n' and not main._editor.sessions
