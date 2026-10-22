"""Bounded, conditional text editing. Sessions and text live only in memory."""
from translations import tr
import codecs
import http.client
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

LIMIT = 256 * 1024

# Only fixed, application-owned messages cross the Python/QML boundary.
ERROR_MESSAGES = {
    'too_large': tr('The file exceeds the editor limit of 256 KiB.'),
    'encoding': tr('This text is not valid UTF-8.'),
    'format': tr('This text format is not supported. Use UTF-8 with consistent line endings.'),
    'changed': tr('The file changed on the server. Reload or save under a new name.'),
    'verification': tr('The file or path could not be checked safely. Reload before saving.'),
    'name': tr('Use a valid file name ending in .txt or .md.'),
    'name_conflict': tr('A file with this name already exists. Choose another name.'),
    'version': tr('This version cannot be overwritten safely. Reload or save under a new name.'),
    'network': tr('The connection failed. Check the network.'),
    'save_unknown': tr('Saving could not be confirmed. Check the server before trying again.'),
    'response': tr('The server returned an invalid response. Try loading the file again.'),
    'server': tr('The server could not complete this request.'),
    'busy': tr('Wait until the current transfer has finished.'),
    'session': tr('The connection changed. Open the file again.'),
    'unknown': tr('The editor operation failed. The file could not be checked safely.'),
}


class EditorFailure(ValueError):
    def __init__(self, code, status=None):
        super().__init__()
        self.code = code
        self.status = status


def failure(code):
    code = code if code in ERROR_MESSAGES else 'unknown'
    return {'success': False, 'errorCode': code,
            'message': ERROR_MESSAGES.get(code, ERROR_MESSAGES['unknown'])}


def strong(etag):
    return bool(isinstance(etag, str) and re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"', etag))


def valid_name(name):
    return (isinstance(name, str) and bool(name.strip()) and name.lower().endswith(('.txt', '.md'))
            and not any(c in name for c in '/\\')
            and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def decode(data):
    if len(data) > LIMIT:
        raise EditorFailure('too_large')
    bom = data.startswith(codecs.BOM_UTF8)
    try:
        text = data[len(codecs.BOM_UTF8):].decode('utf-8', 'strict') if bom else data.decode('utf-8', 'strict')
    except UnicodeError:
        raise EditorFailure('encoding') from None
    rest = text.replace('\r\n', '')
    if '\r' in rest or ('\r\n' in text and '\n' in rest) or any(
            (ord(c) < 32 and c not in '\r\n\t') or c in '\u2028\u2029\x7f' for c in text):
        raise EditorFailure('format')
    return text.replace('\r\n', '\n'), bom, '\r\n' if '\r\n' in text else '\n'


def encode(text, bom, newline):
    if not isinstance(text, str) or '\r' in text:
        raise EditorFailure('format')
    try:
        data = (codecs.BOM_UTF8 if bom else b'') + text.replace('\n', newline).encode('utf-8', 'strict')
    except UnicodeError:
        raise EditorFailure('encoding') from None
    decode(data)  # Same format and actual byte limit in both directions.
    return data


class Editor:
    def __init__(self, get_client, busy):
        self.client = get_client
        self.busy = busy
        self.sessions = {}
        self.lock = threading.Lock()
        self._put_started = False  # Diagnostics only; never used to permit a PUT.
        self._conditional_get = False

    def close(self, token):
        with self.lock:
            self.sessions.pop(token, None)
        return {'success': True}

    def call(self, operation, *args):
        if not self.lock.acquire(False):
            return failure('busy')
        self._put_started = False
        self._conditional_get = False
        try:
            if self.busy():
                raise EditorFailure('busy')
            return getattr(self, operation)(*args)
        except EditorFailure as error:
            result = failure(error.code)
            if error.status is not None:
                result["status"] = error.status
            return result
        except urllib.error.HTTPError as error:
            if error.code == 412:
                creating = (operation == 'save' and args and
                            ((len(args) > 2 and args[2]) or
                             self.sessions.get(args[0], {}).get('snapshot') is None))
                code = ('name_conflict' if creating else 'changed') if (self._put_started or self._conditional_get) else 'verification'
                result = failure(code)
                result['status'] = error.code
                return result
            messages = {401: tr('Authentication failed.'), 403: tr('Access to this file was denied.'),
                        404: tr('The file or folder was not found. Reload before saving.'),
                        409: tr('The destination conflicts with another file or folder.'),
                        423: tr('The file is locked.'), 507: tr('The server has insufficient storage.')}
            message = messages.get(error.code)
            if message is None:
                result = failure('save_unknown' if self._put_started else 'server')
                result['status'] = error.code
                return result
            return {'success': False, 'status': error.code, 'message': message}
        except (OSError, urllib.error.URLError, http.client.HTTPException):
            return failure('save_unknown' if self._put_started else 'network')
        except ValueError:
            return failure('save_unknown' if self._put_started else 'verification')
        except Exception:
            return failure('save_unknown' if self._put_started else 'unknown')
        finally:
            self.lock.release()

    def target(self, client, parent, name):
        if not valid_name(name):
            raise EditorFailure('name')
        url, _ = client._delete_url(parent, root_alias=True)
        target = url.rstrip('/') + '/' + urllib.parse.quote(name, safe='')
        return client._delete_target(parent, target)[0]

    def stat(self, client, parent, path):
        stat = client.inspect_delete(parent, path, editor=True)
        if stat['isDirectory']:
            raise ValueError()
        return stat

    def open(self, parent, path='', name=''):
        client = self.client()
        if path:
            snapshot = self.stat(client, parent, path)
            if not valid_name(snapshot['name']):
                raise EditorFailure('format')
            req = urllib.request.Request(snapshot['url'], method='GET', headers={
                'Authorization': client._auth_header(), 'Accept-Encoding': 'identity'})
            expected = snapshot['metadata']['getetag']
            if strong(expected):
                req.add_header('If-Match', expected)
            self._conditional_get = strong(expected)
            with client._delete_open(req) as response:
                if response.status != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity':
                    raise EditorFailure('response')
                data = response.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise EditorFailure('too_large')
                length = response.headers.get('Content-Length')
                if length is not None and int(length) != len(data):
                    raise EditorFailure('response')
                etag = response.headers.get('ETag', '')
                if strong(expected) and strong(etag) and etag != expected:
                    raise EditorFailure('changed')
            text, bom, newline = decode(data)
            path, name = snapshot['url'], snapshot['name']
        else:
            path = self.target(client, parent, name)
            snapshot, etag, text, bom, newline = None, '', '', False, '\n'
        token = uuid.uuid4().hex
        self.sessions[token] = dict(parent=parent, path=path, name=name, snapshot=snapshot,
            etag=etag, text=text, bom=bom, newline=newline, blocked=False,
            connection=(client.server, client.user, client.password))
        return self.info(token, text=text)

    def info(self, token, **extra):
        s = self.sessions[token]
        return dict(success=True, token=token, name=s['name'],
                    canOverwrite=not s['blocked'] and (s['snapshot'] is None or strong(s['etag'])), **extra)

    def save(self, token, text, new_name=''):
        s = self.sessions[token]
        client = self.client()
        if s['connection'] != (client.server, client.user, client.password):
            raise EditorFailure('session')
        data = encode(text, s['bom'], s['newline'])
        path = self.target(client, s['parent'], new_name) if new_name else s['path']
        client._delete_target(s['parent'], path)
        creating = bool(new_name) or s['snapshot'] is None
        if not new_name and (s['blocked'] or (not creating and not strong(s['etag']))):
            raise EditorFailure('version')
        # Verify the actual parent collection, including root, before every PUT.
        parent = client.inspect_delete(s['parent'], s['parent'], editor=True, parent=True)
        if not parent['isDirectory']:
            raise ValueError()
        if creating:
            try:
                self.stat(client, s['parent'], path)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            else:
                raise EditorFailure('name_conflict', status=412)
        else:
            current = self.stat(client, s['parent'], path)
            if current != s['snapshot']:
                previous_etag = s['snapshot']['metadata']['getetag']
                current_etag = current['metadata']['getetag']
                # A validator mismatch proves a conflict. Other metadata/path
                # failures remain a safety-check failure, without guessing why.
                if strong(previous_etag) and strong(current_etag) and previous_etag != current_etag:
                    raise EditorFailure('changed')
                raise EditorFailure('verification')
        req = urllib.request.Request(path, data=data, method='PUT', headers={
            'Authorization': client._auth_header(),
            'Content-Type': ('text/markdown' if (new_name or s['name']).lower().endswith('.md') else 'text/plain') + '; charset=utf-8',
            'If-None-Match' if creating else 'If-Match': '*' if creating else s['etag']})
        # From this point every failure is potentially ambiguous. Never reuse
        # the old condition until an explicit fresh load; Save As remains safe.
        s['blocked'] = True
        self._put_started = True
        with client._delete_open(req) as response:
            if response.status not in (200, 201, 204):
                raise ValueError()
            etag = response.headers.get('ETag', '')
        s.update(path=path, name=new_name or s['name'], text=text, etag=etag)
        # Recheck DAV identity/type and bind the next overwrite to this PUT's
        # validator. No validator from a later unrelated GET is substituted.
        try:
            snapshot = self.stat(client, s['parent'], path)
            identity_matches = (creating or s['snapshot'] is None or all(
                not s['snapshot']['metadata'][key] or
                s['snapshot']['metadata'][key] == snapshot['metadata'][key]
                for key in ('resource-id', 'creationdate')))
            if strong(etag) and snapshot['metadata']['getetag'] == etag and identity_matches:
                s.update(snapshot=snapshot, blocked=False)
        except Exception:
            pass
        return self.info(token, message='' if not s['blocked'] else
                         tr('Saved. Reload the file before saving again.'))
