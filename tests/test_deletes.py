import contextlib
import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from webdav import WebDavClient, DeleteSafetyError, NoDeleteRedirect


class Response(io.BytesIO):
    def __init__(self, status=207, data=b''):
        super().__init__(data)
        self.status = status


def stat_xml(href='/dav/parent/item', directory=False, etag='"v1"', identity='urn:uuid:one', extra=''):
    resource_type = '<d:collection/>' if directory else ''
    return (f'<d:multistatus xmlns:d="DAV:"><d:response><d:href>{escape(href)}</d:href>'
            f'<d:propstat><d:prop><d:resourcetype>{resource_type}</d:resourcetype>'
            f'<d:getetag>{escape(etag)}</d:getetag><d:resource-id><d:href>{escape(identity)}</d:href></d:resource-id>'
            f'<d:creationdate>2026-01-01</d:creationdate>{extra}</d:prop>'
            '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>').encode()


def multi(entries):
    return ('<d:multistatus xmlns:d="DAV:">' + ''.join(
        f'<d:response><d:href>{escape(href)}</d:href><d:status>HTTP/1.1 {status} Result</d:status></d:response>'
        for href, status in entries) + '</d:multistatus>').encode()


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.client = WebDavClient()
        self.client.server = 'https://example.org/dav/'
        self.parent = '/dav/parent/'
        self.path = '/dav/parent/item'
        main._delete_selections.clear()
        self.addCleanup(main._delete_selections.clear)

    def inspect(self, data=None):
        with patch.object(self.client, '_delete_open', return_value=Response(data=stat_xml() if data is None else data)):
            return self.client.inspect_delete(self.parent, self.path)

    def test_safe_paths_and_literal_percent_names(self):
        for suffix, decoded in [('Gr%C3%BC%C3%9Fe%20a', 'Grüße a'), ('Grüße a', 'Grüße a'),
                                ('%25', '%'), ('%252F', '%2F'), ('%252e%252e', '%2e%2e'),
                                ('%23%3F%26', '#?&'), ('a%2Eb', 'a.b')]:
            path = '/dav/parent/' + suffix
            for form in (path, 'https://example.org' + path):
                with self.subTest(path=form):
                    url, segments = self.client._delete_target(self.parent, form)
                    self.assertEqual(segments[-1], decoded)
                    self.assertNotIn(' ', url)
                    if suffix == '%252F':
                        self.assertTrue(url.endswith('%252F'))
        self.assertEqual(self.client._delete_target('/', '/dav/item')[1], ('dav', 'item'))
        self.client.server = 'https://example.org/'
        self.assertEqual(self.client._delete_target('/', '/item')[1], ('item',))

    def test_invalid_or_outside_targets_never_network(self):
        paths = ['', None, '/', '/dav', '/dav/', '/dav/parent', '/dav/parent/',
                 '/dav/parent/a/b', '/dav/sibling/item', '/davish/parent/item',
                 '/dav/parent/../item', '/dav/parent/%2e%2e', '/dav/parent/%2E',
                 '/dav/parent/a%2fb', '/dav/parent/a%5Cb', '/dav/parent//item',
                 '/dav/parent/%', '/dav/parent/%GG', '/dav/parent/%ff',
                 '/dav/parent/%00', '/dav/parent/%0a', '/dav/parent/it\nem',
                 '/dav/parent/a\\b', '/dav/parent/item?secret=1', '/dav/parent/item#x',
                 'https://other.org/dav/parent/item', '//other.org/dav/parent/item',
                 'https://u:p@example.org/dav/parent/item', 'https://example.org/outside/item']
        with patch.object(self.client, '_delete_open') as send:
            for path in paths:
                with self.subTest(path=path), self.assertRaises((ValueError, TypeError)):
                    self.client.inspect_delete(self.parent, path)
            send.assert_not_called()

    def test_invalid_parent_and_segment_boundaries(self):
        for parent in ('/dav/parent/../', '/outside/', '/davish/', 'https://other.org/dav/parent/',
                       '/dav/parent/%2F/', '/dav/parent?x', '/dav/parent//'):
            with self.subTest(parent=parent), patch.object(self.client, '_delete_open') as send:
                with self.assertRaises(ValueError):
                    self.client.inspect_delete(parent, self.path)
                send.assert_not_called()
        for path in ('/dav/%70arent/', 'https://example.org/dav/parent', '/dav/parent/.'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.client._delete_target(self.parent, path)

    def test_actual_type_and_propfind_request(self):
        for directory in (True, False):
            # A collection need not have a trailing slash; a file may have one.
            data = stat_xml(directory=directory)
            with patch.object(self.client, '_delete_open', return_value=Response(data=data)) as send:
                snapshot = self.client.inspect_delete(self.parent, self.path)
                self.assertEqual(snapshot['isDirectory'], directory)
                request = send.call_args.args[0]
                self.assertEqual(request.method, 'PROPFIND')
                self.assertEqual(request.get_header('Depth'), '0')
                self.assertIn(b'resourcetype', request.data)
                self.assertIn(b'getetag', request.data)

    def test_missing_ambiguous_failed_or_foreign_metadata(self):
        good = stat_xml()
        bad = [good.replace(b'<d:resourcetype></d:resourcetype>', b''),
               good.replace(b'200 OK', b'404 Missing'),
               good.replace(b'<d:resourcetype>', b'<d:resourcetype><d:unknown/>'),
               good.replace(b'</d:prop>', b'<d:resourcetype/></d:prop>'),
               stat_xml(href='/dav/parent/other'), stat_xml(href='https://other.org/dav/parent/item'),
               b'<d:multistatus xmlns:d="DAV:"/>', b'not xml', b'<other/>',
               b'<!DOCTYPE foo><d:multistatus xmlns:d="DAV:"/>', b'x' * (1024 * 1024 + 1),
               good.replace(b'</d:multistatus>', good.split(b'>', 1)[1])]
        for data in bad:
            with self.subTest(data=data[:60]), self.assertRaises(Exception):
                self.inspect(data)

    def test_success_file_empty_and_nonempty_folder(self):
        for directory, children in ((False, []), (True, []), (True, ['sub/a', 'b'])):
            data = stat_xml(directory=directory)
            snapshot = self.inspect(data)
            resources = {self.path} | {self.path + '/' + child for child in children}
            def server(request):
                if request.method == 'PROPFIND':
                    return Response(data=data)
                self.assertEqual(request.method, 'DELETE')
                resources.clear()  # Simulated server-side recursive deletion.
                return Response(status=204)
            with patch.object(self.client, '_delete_open', side_effect=server) as send:
                self.assertEqual(self.client.delete_resource(self.parent, self.path, snapshot), {'success': True})
                self.assertEqual(resources, set())
                self.assertEqual([call.args[0].method for call in send.call_args_list], ['PROPFIND', 'DELETE'])
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, snapshot['url'])
                self.assertIsNotNone(request.get_header('Authorization'))
                self.assertEqual(request.get_header('If-match'), None if directory else '"v1"')

    def test_weak_missing_invalid_etags_not_used_as_if_match(self):
        for etag in ('', 'W/"v1"', 'unquoted', '"a", "b"', '"bad\nvalue"'):
            data = stat_xml(etag=etag)
            snapshot = self.inspect(data)
            with patch.object(self.client, '_delete_open', side_effect=[Response(data=data), Response(status=204)]) as send:
                self.client.delete_resource(self.parent, self.path, snapshot)
                self.assertIsNone(send.call_args.args[0].get_header('If-match'))

    def test_type_identity_etag_and_metadata_changes_abort(self):
        snapshot = self.inspect()
        for data in (stat_xml(directory=True), stat_xml(identity='urn:uuid:two'),
                     stat_xml(etag='"v2"'), stat_xml(etag=''),
                     stat_xml(extra='<d:getcontentlength>20</d:getcontentlength>')):
            with self.subTest(data=data), patch.object(self.client, '_delete_open', return_value=Response(data=data)) as send:
                with self.assertRaises(DeleteSafetyError):
                    self.client.delete_resource(self.parent, self.path, snapshot)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.args[0].method, 'PROPFIND')

    def test_multistatus_never_claims_complete_success(self):
        snapshot = self.inspect(stat_xml(directory=True))
        payloads = [multi([('/dav/parent/item/sub/a', 204), ('/dav/parent/item/sub/b', 423)]),
                    multi([('/dav/parent/item', 204)]), multi([]), b'bad xml',
                    multi([('https://other.org/a', 403)]), multi([('/dav/parent/itemish/a', 403)]),
                    multi([('/dav/parent/item', 403)]).replace(b'403 Result', b'broken')]
        for data in payloads:
            with self.subTest(data=data), patch.object(self.client, '_delete_open', side_effect=[
                    Response(data=stat_xml(directory=True)), Response(status=207, data=data)]):
                result = self.client.delete_resource(self.parent, self.path, snapshot)
                self.assertFalse(result['success'])
                self.assertEqual(result['status'], 207)
                self.assertTrue(result['refresh'])
                self.assertTrue(result['message'])
                if b'423' in data:
                    self.assertEqual(result['failureStatuses'], [423])

    def prepare(self):
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open', return_value=Response(data=stat_xml())):
            result = main.prepare_delete(self.parent, self.path)
        self.assertTrue(result['success'])
        self.assertNotIn('url', result)
        self.assertNotIn('metadata', result)
        return result['token']

    def test_cancel_and_single_use_token(self):
        token = self.prepare()
        main.cancel_delete(token)
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open') as send:
            self.assertFalse(main.delete_resource(token)['success'])
            send.assert_not_called()
        token = self.prepare()
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open', side_effect=[Response(data=stat_xml()), Response(status=204)]) as send:
            self.assertTrue(main.delete_resource(token)['success'])
            self.assertFalse(main.delete_resource(token)['success'])
            self.assertEqual(send.call_count, 2)

    def test_connection_change_and_reselection_invalidate_token(self):
        token = self.prepare()
        self.client.user = 'changed'
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open') as send:
            self.assertFalse(main.delete_resource(token)['success'])
            send.assert_not_called()
        old = self.prepare()
        new = self.prepare()
        self.assertNotEqual(old, new)
        self.assertNotIn(old, main._delete_selections)

    def test_http_failures_sanitized_no_retry(self):
        for status in (401, 403, 404, 405, 409, 412, 423, 500, 502, 503, 507):
            token = self.prepare()
            failure = urllib.error.HTTPError('https://u:SECRET@example.org', status, 'SECRET', {}, None)
            with self.subTest(status=status), patch.object(main, 'client', self.client), patch.object(
                    self.client, '_delete_open', side_effect=[Response(data=stat_xml()), failure]) as send:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = main.delete_resource(token)
                self.assertFalse(result['success'])
                self.assertEqual(result['status'], status)
                self.assertNotIn('SECRET', str(result) + output.getvalue())
                self.assertEqual(send.call_count, 2)
                self.assertFalse(main.delete_resource(token)['success'])

    def test_disconnects_unclear_responses_and_invalid_xml(self):
        for response in (TimeoutError('SECRET'), ConnectionResetError('SECRET'),
                         urllib.error.URLError('SECRET'), Response(status=202),
                         Response(status=207, data=b'bad')):
            token = self.prepare()
            with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open', side_effect=[Response(data=stat_xml()), response]) as send:
                result = main.delete_resource(token)
                self.assertFalse(result['success'])
                self.assertTrue(result['refresh'])
                self.assertNotIn('SECRET', str(result))
                self.assertEqual(send.call_count, 2)

    def test_redirects_refused_and_private_opener(self):
        handler = NoDeleteRedirect()
        for method in ('PROPFIND', 'DELETE'):
            request = __import__('urllib.request', fromlist=['Request']).Request('https://example.org/dav/parent/item', method=method)
            for status in (301, 302, 303, 307, 308):
                with self.assertRaises(DeleteSafetyError):
                    handler.redirect_request(request, None, status, '', {}, 'https://other.org/')
        with patch('urllib.request.build_opener') as build:
            request = object()
            self.client._delete_open(request)
            self.assertIsInstance(build.call_args.args[0], NoDeleteRedirect)
            build.return_value.open.assert_called_once_with(request, timeout=30)

    def test_second_stat_failure_cannot_delete(self):
        token = self.prepare()
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open',
                side_effect=urllib.error.HTTPError('https://example.org', 404, 'gone', {}, None)) as send:
            self.assertFalse(main.delete_resource(token)['success'])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0].method, 'PROPFIND')

    def test_without_identity_metadata_refused(self):
        data = stat_xml(etag='', identity='').replace(b'<d:creationdate>2026-01-01</d:creationdate>', b'')
        with self.assertRaises(DeleteSafetyError):
            self.inspect(data)

    def test_preflight_path_failure_and_logs_are_safe(self):
        with patch.object(main, 'client', self.client), patch.object(self.client, '_delete_open') as send:
            result = main.prepare_delete('/', '/dav/')
            self.assertFalse(result['success'])
            send.assert_not_called()
        with patch.object(main.client, 'list_directory', side_effect=ValueError('https://u:SECRET@example.org')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main.list_directory('/')
            self.assertNotIn('SECRET', str(result) + output.getvalue())

    def test_listing_collection_type_and_self_alias(self):
        data = stat_xml(href='https://example.org/dav/parent/', directory=True)
        child = stat_xml(href='/dav/parent/file.pdf', directory=True).decode()
        fragment = child.split('<d:multistatus xmlns:d="DAV:">')[1].split('</d:multistatus>')[0]
        data = data.replace(b'</d:multistatus>', fragment.encode() + b'</d:multistatus>')
        with patch('webdav.WebDavClient._open', return_value=Response(data=data)):
            items = self.client.list_directory(self.parent)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]['isDirectory'])
        self.assertEqual(items[0]['name'], 'file.pdf')
