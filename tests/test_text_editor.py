import codecs
import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from webdav import WebDavClient
from text_editor import Editor, LIMIT, decode, encode, valid_name
from test_deletes import stat_xml


class Response(io.BytesIO):
    def __init__(self, status=200, data=b'', headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.client = WebDavClient()
        self.client.server = 'https://example.org/dav/'
        self.parent = '/dav/parent/'
        self.path = self.parent + 'note.txt'
        self.editor = Editor(lambda: self.client, lambda: False)
        self.requests = []
        self.etag = '"v1"'
        self.data = b'hello\n'
        self.exists = True
        self.put_etag = '"v2"'
        self.failure = None

    def server(self, req):
        self.requests.append(req)
        if req.method == 'PROPFIND':
            if req.full_url.endswith('/parent/'):
                return Response(207, stat_xml(href=self.parent, directory=True))
            if not self.exists:
                raise urllib.error.HTTPError(req.full_url, 404, '', {}, None)
            return Response(207, stat_xml(href=__import__('urllib.parse', fromlist=['urlsplit']).urlsplit(req.full_url).path, etag=self.etag))
        if req.method == 'GET':
            return Response(200, self.data, {'ETag': self.etag})
        if req.method == 'PUT':
            if self.failure:
                raise self.failure
            self.data = req.data
            self.etag = self.put_etag
            self.exists = True
            return Response(201, headers={'ETag': self.put_etag})
        self.fail('Unexpected method')

    def open(self):
        result = self.editor.call('open', self.parent, self.path)
        self.assertTrue(result['success'], result)
        return result

    def test_new_unicode_percent_and_conditions(self):
        for name in ('Neu Grüße.txt', '%2F %?#.md', 'UPPER.TXT'):
            with self.subTest(name=name), patch.object(self.client, '_delete_open', side_effect=self.server):
                self.exists = False
                opened = self.editor.call('open', self.parent, '', name)
                self.assertTrue(opened['success'])
                saved = self.editor.call('save', opened['token'], 'Grüße\n')
                self.assertTrue(saved['success'], saved)
                req = [r for r in self.requests if r.method == 'PUT'][-1]
                self.assertEqual(req.get_header('If-none-match'), '*')
                self.assertIsNone(req.get_header('If-match'))
                self.assertEqual(req.data, 'Grüße\n'.encode())
                if '%2F' in name:
                    self.assertIn('%252F', req.full_url)

    def test_repeated_edit_uses_current_strong_version(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            for before, after in [('"v1"', '"v2"'), ('"v2"', '"v3"')]:
                self.put_etag = after
                result = self.editor.call('save', opened['token'], after)
                self.assertTrue(result['canOverwrite'], result)
                self.assertEqual([r for r in self.requests if r.method == 'PUT'][-1].get_header('If-match'), before)

    def test_weak_or_missing_etag_save_as_only(self):
        for etag in ('', 'W/"weak"'):
            with self.subTest(etag=etag), patch.object(self.client, '_delete_open', side_effect=self.server):
                self.etag = etag
                opened = self.open()
                self.assertFalse(opened['canOverwrite'])
                self.assertFalse(self.editor.call('save', opened['token'], 'edit')['success'])
                self.exists = False
                self.assertTrue(self.editor.call('save', opened['token'], 'edit', 'copy.md')['success'])

    def test_missing_post_put_validator_blocks_overwrite(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            self.put_etag = ''
            result = self.editor.call('save', opened['token'], 'edited')
            self.assertTrue(result['success'])
            self.assertFalse(result['canOverwrite'])
            self.assertFalse(self.editor.call('save', opened['token'], 'again')['success'])

    def test_conflict_timeout_disconnect_no_retry_or_text_logs(self):
        for failure in (TimeoutError('SECRET-TEXT'), ConnectionResetError('SECRET-TEXT'),
                        urllib.error.HTTPError('https://u:SECRET-TEXT@example.org', 412, '', {}, None)):
            with self.subTest(failure=type(failure)), patch.object(self.client, '_delete_open', side_effect=self.server):
                opened = self.open()
                self.failure = failure
                result = self.editor.call('save', opened['token'], 'SECRET-TEXT')
                self.assertFalse(result['success'])
                count = len([r for r in self.requests if r.method == 'PUT'])
                self.assertFalse(self.editor.call('save', opened['token'], 'SECRET-TEXT')['success'])
                self.assertEqual(count, len([r for r in self.requests if r.method == 'PUT']))
                self.assertNotIn('SECRET-TEXT', str(result))
                self.failure = None

    def test_changed_identity_type_or_version_never_put(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            self.etag = '"changed"'
            self.assertFalse(self.editor.call('save', opened['token'], 'edit')['success'])
            self.assertFalse(any(r.method == 'PUT' for r in self.requests))

    def test_invalid_names_paths_and_connection(self):
        for name in ('', ' ', '..', '../a.txt', 'a/b.md', 'a\\b.txt', 'a\n.txt', 'x.pdf'):
            self.assertFalse(valid_name(name))
        with patch.object(self.client, '_delete_open') as send:
            for path in ('/dav/', '/outside/a.txt', '/dav/parent/a%2Fb.txt', '/dav/parent/../a.txt', 'https://other.org/a.txt'):
                self.assertFalse(self.editor.call('open', self.parent, path)['success'])
            send.assert_not_called()
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            self.client.user = 'changed'
            self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])

    def test_utf8_bom_newlines_and_byte_limits(self):
        for data in (b'a\n', b'a\r\nb\r\n', codecs.BOM_UTF8 + 'Grüße\r\n'.encode()):
            text, bom, newline = decode(data)
            self.assertEqual(encode(text, bom, newline), data)
        for data in (b'\xff', b'\x00', b'a\r\nb\n', b'a\rb', '\u2029'.encode(), b'x'*(LIMIT+1)):
            with self.assertRaises((ValueError, UnicodeError)):
                decode(data)
        self.assertEqual(len(encode('ä'*(LIMIT//2), False, '\n')), LIMIT)
        with self.assertRaises(ValueError):
            encode('ä'*(LIMIT//2), True, '\n')
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            self.data = b'x'*(LIMIT+1)
            self.assertFalse(self.editor.call('open', self.parent, self.path)['success'])

    def test_busy_and_session_cleanup(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            with self.editor.lock:
                self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])
            self.editor.close(opened['token'])
            self.assertEqual(self.editor.sessions, {})
            self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])

    def test_load_bom_crlf_save_exact_and_oversize_save_no_put(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            self.data = codecs.BOM_UTF8 + 'Grüße\r\nText\r\n'.encode()
            opened = self.open()
            self.assertEqual(opened['text'], 'Grüße\nText\n')
            self.assertTrue(self.editor.call('save', opened['token'], opened['text'])['success'])
            self.assertEqual(self.data, codecs.BOM_UTF8 + 'Grüße\r\nText\r\n'.encode())
            count = len(self.requests)
            self.assertFalse(self.editor.call('save', opened['token'], 'ä'*LIMIT)['success'])
            self.assertEqual(len(self.requests), count)

    def test_existing_new_name_conflict_and_http_failures(self):
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.editor.call('open', self.parent, '', 'note.txt')
            self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])
            self.assertFalse(any(r.method == 'PUT' for r in self.requests))
        for status in (401, 403, 404, 409, 423, 500, 507):
            with patch.object(self.client, '_delete_open', side_effect=self.server):
                opened = self.open()
                self.failure = urllib.error.HTTPError(self.path, status, 'SECRET', {}, None)
                result = self.editor.call('save', opened['token'], 'x')
                self.assertFalse(result['success'])
                self.assertEqual(result['status'], status)
                self.assertNotIn('SECRET', str(result))
                self.failure = None

    def test_parent_or_target_type_and_identity_change(self):
        for field in ('directory', 'identity', 'parent'):
            with patch.object(self.client, '_delete_open', side_effect=self.server):
                opened = self.open()
            def changed(req):
                if req.method != 'PROPFIND':
                    self.fail('Unsafe PUT')
                is_parent = req.full_url.endswith('/parent/')
                return Response(207, stat_xml(href=self.parent if is_parent else self.path,
                    directory=(False if field == 'parent' else True) if is_parent else field == 'directory',
                    identity='changed' if field == 'identity' and not is_parent else 'urn:uuid:one'))
            with patch.object(self.client, '_delete_open', side_effect=changed):
                self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])

    def test_get_validator_not_propfind_validator_is_used(self):
        def missing(req):
            response = self.server(req)
            if req.method == 'GET':
                response.headers = {}
            return response
        with patch.object(self.client, '_delete_open', side_effect=missing):
            opened = self.open()
            self.assertFalse(opened['canOverwrite'])
            self.assertFalse(self.editor.call('save', opened['token'], 'x')['success'])

    def test_no_draft_files_or_sensitive_error_output(self):
        import contextlib
        with patch.object(self.client, '_delete_open', side_effect=self.server), patch('builtins.open') as disk:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                opened = self.open()
                self.failure = TimeoutError('PRIVATE-TEXT')
                result = self.editor.call('save', opened['token'], 'PRIVATE-TEXT')
            disk.assert_not_called()
            self.assertNotIn('PRIVATE-TEXT', str(result) + output.getvalue())

    def test_post_put_mismatched_version_and_identity_block(self):
        for changed in ('etag', 'identity'):
            with patch.object(self.client, '_delete_open', side_effect=self.server):
                opened = self.open()
            put = [False]
            def server(req):
                if put[0] and req.method == 'PROPFIND':
                    return Response(207, stat_xml(href=self.path,
                        etag='"other"' if changed == 'etag' else self.put_etag,
                        identity='other' if changed == 'identity' else 'urn:uuid:one'))
                response = self.server(req)
                if req.method == 'PUT':
                    put[0] = True
                return response
            with patch.object(self.client, '_delete_open', side_effect=server):
                result = self.editor.call('save', opened['token'], 'x')
                self.assertTrue(result['success'])
                self.assertFalse(result['canOverwrite'])

    def test_backend_busy_gates_other_actions(self):
        import main
        with main._editor.lock:
            for function, args in ((main.list_directory, ('/',)),
                (main.create_directory, ('/', 'x')), (main.prepare_delete, ('/', '/dav/x')),
                (main.upload_file, ('x', '/')), (main.download_file, ('/dav/x',)),
                (main.prepare_download_job, ('/', ['/dav/x'])),
                (main.start_download_job, ('job',)), (main.connect, ('url', 'u', 'p'))):
                self.assertFalse(function(*args)['success'])

    def test_specific_size_encoding_and_format_messages(self):
        cases = [(b'x'*(LIMIT+1), 'too_large', 'The file exceeds the editor limit of 256 KiB.'),
                 (b'\xffPRIVATE', 'encoding', 'This text is not valid UTF-8.'),
                 (b'a\r\nb\n', 'format', 'This text format is not supported. Use UTF-8 with consistent line endings.'),
                 (b'a\x00PRIVATE', 'format', 'This text format is not supported. Use UTF-8 with consistent line endings.')]
        for data, code, message in cases:
            with self.subTest(code=code), patch.object(self.client, '_delete_open', side_effect=self.server):
                self.data = data
                result = self.editor.call('open', self.parent, self.path)
                self.assertEqual(result['errorCode'], code)
                self.assertEqual(result['message'], message)
                self.assertNotIn('PRIVATE', str(result))
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            self.data = b'original'
            opened = self.open()
            count = len(self.requests)
            self.assertEqual(self.editor.call('save', opened['token'], 'ä'*LIMIT)['errorCode'], 'too_large')
            self.assertEqual(self.editor.call('save', opened['token'], 'a\rb')['errorCode'], 'format')
            self.assertEqual(self.editor.call('save', opened['token'], '\ud800')['errorCode'], 'encoding')
            self.assertEqual(len(self.requests), count)
            self.assertEqual(self.editor.sessions[opened['token']]['text'], 'original')

    def test_conflict_messages_distinguish_name_and_version(self):
        from text_editor import ERROR_MESSAGES
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
            self.etag = '"changed"'
            result = self.editor.call('save', opened['token'], 'changed locally')
            self.assertEqual(result['message'], ERROR_MESSAGES['changed'])
            self.assertEqual(result['errorCode'], 'changed')
            self.assertFalse(any(r.method == 'PUT' for r in self.requests))
            opened = self.open()
            self.failure = urllib.error.HTTPError(self.path, 412, 'PRIVATE', {}, None)
            result = self.editor.call('save', opened['token'], 'changed locally')
            self.assertEqual(result['message'], ERROR_MESSAGES['changed'])
            self.assertEqual(result['status'], 412)
            self.failure = None
            result = self.editor.call('save', opened['token'], 'changed locally', 'existing.md')
            self.assertEqual(result['message'], ERROR_MESSAGES['name_conflict'])
            self.assertEqual(result['status'], 412)
            self.exists = False
            self.failure = urllib.error.HTTPError(self.path, 412, 'PRIVATE', {}, None)
            result = self.editor.call('save', opened['token'], 'changed locally', 'new.md')
            self.assertEqual(result['errorCode'], 'name_conflict')
            self.assertNotIn('PRIVATE', str(result))

    def test_verification_and_network_messages_do_not_guess_conflict(self):
        from text_editor import ERROR_MESSAGES
        with patch.object(self.client, '_delete_open') as send:
            result = self.editor.call('open', self.parent, '/dav/parent/%ff.txt')
            self.assertEqual(result['errorCode'], 'verification')
            self.assertEqual(result['message'], ERROR_MESSAGES['verification'])
            send.assert_not_called()
        for error in (ValueError('https://u:PRIVATE@example.org'),
                      TimeoutError('PRIVATE'), urllib.error.URLError('PRIVATE')):
            with patch.object(self.client, '_delete_open', side_effect=error):
                result = self.editor.call('open', self.parent, self.path)
                self.assertEqual(result['errorCode'], 'verification' if isinstance(error, ValueError) else 'network')
                self.assertNotIn('PRIVATE', str(result))
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
        with patch.object(self.client, '_delete_open', side_effect=TimeoutError('PRIVATE')) as send:
            result = self.editor.call('save', opened['token'], 'retained text')
            self.assertEqual(result['errorCode'], 'network')
            self.assertEqual(send.call_args.args[0].method, 'PROPFIND')
            self.assertFalse(self.editor.sessions[opened['token']]['blocked'])

    def test_ambiguous_put_messages_preserve_existing_no_retry_guard(self):
        from text_editor import ERROR_MESSAGES
        for error in (TimeoutError('PRIVATE'), ConnectionResetError('PRIVATE'),
                      urllib.error.URLError('PRIVATE'), ValueError('PRIVATE')):
            with patch.object(self.client, '_delete_open', side_effect=self.server):
                opened = self.open()
                self.failure = error
                result = self.editor.call('save', opened['token'], 'retained text')
                self.assertEqual(result['errorCode'], 'save_unknown')
                self.assertEqual(result['message'], ERROR_MESSAGES['save_unknown'])
                self.assertTrue(self.editor.sessions[opened['token']]['blocked'])
                count = len(self.requests)
                self.assertEqual(self.editor.call('save', opened['token'], 'retained text')['errorCode'], 'version')
                self.assertEqual(count, len(self.requests))
                self.assertNotIn('PRIVATE', str(result))
                self.failure = None

    def test_unknown_errors_and_internal_codes_never_expose_details(self):
        from text_editor import EditorFailure, failure
        for error in (RuntimeError('PRIVATE'), EditorFailure('PRIVATE')):
            with patch.object(self.client, '_delete_open', side_effect=error):
                result = self.editor.call('open', self.parent, self.path)
                self.assertEqual(result['errorCode'], 'unknown')
                self.assertNotIn('PRIVATE', str(result))
        self.assertEqual(failure('https://u:PRIVATE@example.org')['errorCode'], 'unknown')

    def test_412_only_claims_version_conflict_for_conditional_requests(self):
        from text_editor import ERROR_MESSAGES
        error = urllib.error.HTTPError(self.path, 412, 'PRIVATE', {}, None)
        with patch.object(self.client, '_delete_open', side_effect=error):
            self.assertEqual(self.editor.call('open', self.parent, self.path)['errorCode'], 'verification')
        def conditional_get(req):
            if req.method == 'GET':
                self.assertEqual(req.get_header('If-match'), self.etag)
                raise error
            return self.server(req)
        with patch.object(self.client, '_delete_open', side_effect=conditional_get):
            result = self.editor.call('open', self.parent, self.path)
            self.assertEqual(result['message'], ERROR_MESSAGES['changed'])
            self.assertEqual(result['status'], 412)

    def test_metadata_identity_failure_is_not_reported_as_encoding_or_size(self):
        from text_editor import ERROR_MESSAGES
        with patch.object(self.client, '_delete_open', side_effect=self.server):
            opened = self.open()
        def changed_id(req):
            if req.full_url.endswith('/parent/'):
                return self.server(req)
            return Response(207, stat_xml(href=self.path, etag=self.etag, identity='new-id'))
        with patch.object(self.client, '_delete_open', side_effect=changed_id) as send:
            result = self.editor.call('save', opened['token'], 'PRIVATE')
            self.assertEqual(result['message'], ERROR_MESSAGES['verification'])
            self.assertFalse(any(call.args[0].method == 'PUT' for call in send.call_args_list))

    def test_bounded_get_with_real_content_length_reports_size_not_bad_response(self):
        self.data = b'x' * (LIMIT + 10000)
        def server(req):
            response = self.server(req)
            if req.method == 'GET':
                response.headers['Content-Length'] = str(len(self.data))
            return response
        with patch.object(self.client, '_delete_open', side_effect=server):
            result = self.editor.call('open', self.parent, self.path)
            self.assertEqual(result['errorCode'], 'too_large')
            self.assertEqual(result['message'], 'The file exceeds the editor limit of 256 KiB.')
