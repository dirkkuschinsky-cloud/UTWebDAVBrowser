from translations import tr
import base64
import os
import errno
import shutil
import time
import re
import threading
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


class DownloadCancelled(Exception):
    pass


class DownloadControl:
    """Cancellation and atomic publication have a single ordering point."""
    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()

    def cancel(self):
        with self.lock:
            self.event.set()

    def check(self):
        if self.event.is_set():
            raise DownloadCancelled()

    def publish(self, partial, destination):
        with self.lock:
            self.check()
            os.replace(partial, destination)


class DeleteSafetyError(ValueError):
    pass


class UnsafeRedirectError(DeleteSafetyError):
    pass


class DownloadSizeLimit(ValueError):
    pass


class NoDeleteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UnsafeRedirectError("Redirect refused.")

    def http_error_302(self, req, fp, code, msg, headers):
        # Refuse before urllib constructs a request with copied credentials.
        # This also stops same-origin redirects and every redirect chain.
        try:
            if fp is not None:
                fp.close()
        finally:
            raise UnsafeRedirectError("Redirect refused.")

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


class WebDavClient:

    def __init__(self):
        self.server = ""
        self.user = ""
        self.password = ""

    def connect(self, server, user, password):
        self.server = server.rstrip("/") + "/"
        self.user = user
        self.password = password

        try:
            request = urllib.request.Request(self._resolve_url("/"), method="PROPFIND")
            request.add_header("Depth", "0")
            request.add_header("Authorization", self._auth_header())
            with self._open(request, timeout=20) as response:
                return response.status in (200, 207)
        except Exception:
            return False

    def _resolve_url(self, path):
        # A leading slash is a server href, not an ambiguous base-relative path.
        # Only '/' (and the legacy empty root alias) denote the configured root.
        return self._delete_url("/" if path == "" else path, root_alias=True)[0]

    def _join_url(self, path):
        # Caller has already checked decoded segment boundaries. Preserve the
        # original href spelling instead of comparing encoded string prefixes.
        base = urllib.parse.urlsplit(self.server)
        target = urllib.parse.urlsplit(path)
        if target.scheme or (path.startswith("/") and path != "/"):
            url_path = target.path
        else:
            url_path = base.path.rstrip("/") + "/" + path.lstrip("/")
        return urllib.parse.urlunsplit((base.scheme, base.netloc,
            urllib.parse.quote(url_path, safe="/%:@!$&'()*+,;=-._~"), "", ""))

    def create_directory(self, parent_path, name):
        # Names are literal user input, never URL-decoded before validation.
        if (not isinstance(name, str) or not name.strip() or name in (".", "..")
                or any(char in name for char in ("/", "\\"))
                or any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise ValueError("Invalid directory name.")
        parent = urllib.parse.urlsplit(self._resolve_url(parent_path))
        if parent.query or parent.fragment:
            raise ValueError("Invalid parent directory.")
        url = urllib.parse.urlunsplit(parent._replace(
            path=parent.path.rstrip("/") + "/" + urllib.parse.quote(name, safe="") + "/"))
        url, _ = self._delete_target(parent_path, url)
        request = urllib.request.Request(url, data=b"", method="MKCOL")
        request.add_header("Authorization", self._auth_header())
        with self._open(request, timeout=30) as response:
            if response.status != 201:
                raise ValueError("Unexpected MKCOL response.")
        return True

    @staticmethod
    def _path_segments(path):
        # Decode each segment exactly once for comparison, never for transport.
        # Encoded literal '%' names (%252F etc.) must retain their identity.
        if re.search(r"%(?![0-9a-fA-F]{2})", path):
            raise DeleteSafetyError("Invalid encoding.")
        pieces = path.split("/")
        if pieces and pieces[0] == "":
            pieces = pieces[1:]
        if pieces and pieces[-1] == "":
            pieces = pieces[:-1]
        result = []
        for piece in pieces:
            value = urllib.parse.unquote(piece, encoding="utf-8", errors="strict")
            if (not value or value in (".", "..") or "/" in value or "\\" in value
                    or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise DeleteSafetyError("Unsafe path segment.")
            result.append(value)
        return tuple(result)

    def _delete_url(self, path, root_alias=False):
        if (not isinstance(path, str) or not path or path.startswith("//")
                or any(ord(c) < 32 or ord(c) == 127 for c in path)
                or "?" in path or "#" in path or "\\" in path):
            raise DeleteSafetyError("Unsafe path.")
        raw = urllib.parse.urlsplit(path)
        base = urllib.parse.urlsplit(self.server)
        if (any(ord(c) < 32 or ord(c) == 127 for c in self.server)
                or "\\" in self.server
                or base.scheme not in ("http", "https") or not base.netloc
                or base.username is not None or base.password is not None
                or base.query or base.fragment):
            raise DeleteSafetyError("Invalid server.")
        try:
            if not base.hostname:
                raise ValueError()
            base.port
            raw.port
        except ValueError:
            raise DeleteSafetyError("Invalid origin.") from None
        base_segments = self._path_segments(base.path)
        raw_segments = self._path_segments(raw.path)
        if raw.scheme and not raw.netloc:
            raise DeleteSafetyError("Invalid origin.")
        if raw.netloc and (raw.scheme, raw.netloc) != (base.scheme, base.netloc):
            raise DeleteSafetyError("Foreign origin.")
        if raw.username is not None or raw.password is not None:
            raise DeleteSafetyError("Credentials in path.")
        # An origin-relative server href must already be inside the DAV root;
        # do not reinterpret an outside href as a base-relative app path.
        if raw.path.startswith("/") and not (root_alias and path == "/"):
            if raw_segments[:len(base_segments)] != base_segments:
                raise DeleteSafetyError("Outside root.")
        url = self._join_url(path)
        parts = urllib.parse.urlsplit(url)
        segments = self._path_segments(parts.path)
        if ((parts.scheme, parts.netloc) != (base.scheme, base.netloc)
                or segments[:len(base_segments)] != base_segments):
            raise DeleteSafetyError("Outside root.")
        return url, segments

    def _delete_target(self, parent_path, path):
        _, parent = self._delete_url(parent_path, root_alias=True)
        url, target = self._delete_url(path)
        _, root = self._delete_url(self.server)
        if (target == root or target == parent or len(target) != len(parent) + 1
                or target[:-1] != parent):
            raise DeleteSafetyError("Not a direct child.")
        return url, target

    def _open(self, request, timeout=30):
        # Private, shared opener: no global monkeypatch and no redirects, even
        # within the root. Editor and DELETE retain their existing interface.
        return urllib.request.build_opener(NoDeleteRedirect()).open(request, timeout=timeout)

    def _delete_open(self, request):
        return self._open(request, timeout=30)

    @staticmethod
    def _delete_xml(response):
        data = response.read(1024 * 1024 + 1)
        if b"\x00" in data or len(data) > 1024 * 1024 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise DeleteSafetyError("Unsafe or oversized XML.")
        root = ET.fromstring(data)
        if root.tag != "{DAV:}multistatus":
            raise DeleteSafetyError("Invalid multistatus.")
        return root

    @staticmethod
    def _dav_status(text):
        match = re.fullmatch(r"HTTP/\d+(?:\.\d+)? ([1-5]\d\d)(?: .*)?", (text or "").strip())
        if not match:
            raise DeleteSafetyError("Invalid DAV status.")
        return int(match.group(1))

    def inspect_delete(self, parent_path, path, editor=False, parent=False):
        url, target = (self._delete_url(path, root_alias=True) if parent else
                       self._delete_target(parent_path, path))
        body = (b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
                b'<d:getetag/><d:creationdate/><d:getlastmodified/><d:getcontentlength/>'
                b'<d:resource-id/></d:prop></d:propfind>')
        request = urllib.request.Request(url, data=body, method="PROPFIND")
        request.add_header("Authorization", self._auth_header())
        request.add_header("Depth", "0")
        request.add_header("Content-Type", "application/xml; charset=utf-8")
        with self._delete_open(request) as response:
            if response.status != 207:
                raise DeleteSafetyError("Missing resource metadata.")
            root = self._delete_xml(response)
        entries = root.findall("{DAV:}response")
        if len(entries) != 1:
            raise DeleteSafetyError("Ambiguous resource metadata.")
        entry = entries[0]
        status = entry.findtext("{DAV:}status")
        if status is not None and not 200 <= self._dav_status(status) < 300:
            raise DeleteSafetyError("Resource metadata failed.")
        href = entry.findtext("{DAV:}href")
        _, actual = (self._delete_url(href) if parent else self._delete_target(parent_path, href))
        if actual != target:
            raise DeleteSafetyError("Resource mismatch.")
        props = {}
        for propstat in entry.findall("{DAV:}propstat"):
            if self._dav_status(propstat.findtext("{DAV:}status")) == 200:
                prop = propstat.find("{DAV:}prop")
                if prop is not None:
                    for value in prop:
                        if value.tag in props:
                            raise DeleteSafetyError("Duplicate metadata.")
                        props[value.tag] = value
        resource_type = props.get("{DAV:}resourcetype")
        if resource_type is None or (resource_type.text or "").strip():
            raise DeleteSafetyError("Unknown resource type.")
        children = list(resource_type)
        if any(child.tag != "{DAV:}collection" for child in children) or len(children) > 1:
            raise DeleteSafetyError("Unsupported resource type.")
        metadata = {}
        for key in ("getetag", "creationdate", "getlastmodified", "getcontentlength", "resource-id"):
            value = props.get("{DAV:}" + key)
            metadata[key] = "" if value is None else "".join(value.itertext()).strip()
        if not editor and not any(metadata[key] for key in ("getetag", "creationdate", "resource-id")):
            raise DeleteSafetyError("No resource identity metadata.")
        return {"url": url, "segments": target, "isDirectory": bool(children),
                "name": target[-1], "metadata": metadata}

    def delete_resource(self, parent_path, path, expected):
        current = self.inspect_delete(parent_path, path)
        if current != expected:
            raise DeleteSafetyError("Resource changed. Select it again.")
        request = urllib.request.Request(current["url"], method="DELETE")
        request.add_header("Authorization", self._auth_header())
        etag = current["metadata"]["getetag"]
        # A strong file ETag guards the selected representation. Collection
        # validators do not snapshot their descendants; do not apply If-Match
        # to collection DELETE (headers may apply to every member, RFC4918).
        if not current["isDirectory"] and re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"', etag):
            request.add_header("If-Match", etag)
        with self._delete_open(request) as response:
            if response.status in (200, 204):
                return {"success": True}
            if response.status == 207:
                try:
                    root = self._delete_xml(response)
                    entries = root.findall("{DAV:}response")
                    codes = []
                    if not entries:
                        raise DeleteSafetyError("Empty multistatus.")
                    for entry in entries:
                        _, resource = self._delete_url(entry.findtext("{DAV:}href"))
                        if resource[:len(current["segments"])] != current["segments"]:
                            raise DeleteSafetyError("Foreign multistatus entry.")
                        codes.append(self._dav_status(entry.findtext("{DAV:}status")))
                    failures = sorted(set(code for code in codes if code >= 300))
                    message = (tr("Deletion was not completed for all resources. Refresh and select again.")
                               if failures else tr("The server returned an unclear deletion result. Refresh and select again."))
                    if failures:
                        message += tr(" HTTP: ") + ", ".join(str(code) for code in failures) + "."
                    if 423 in failures:
                        message += tr(" One or more resources are locked.")
                    return {"success": False, "status": 207, "refresh": True,
                            "message": message, "failureStatuses": failures}
                except (ValueError, ET.ParseError):
                    return {"success": False, "status": 207, "refresh": True,
                            "message": tr("The server returned an invalid or unclear deletion result. Refresh and select again.")}
            return {"success": False, "refresh": True,
                    "message": tr("Deletion has not been confirmed. Refresh and select again.")}

    def list_directory(self, path="/"):
        url = self._resolve_url(path)

        request = urllib.request.Request(url, method="PROPFIND")
        request.add_header("Depth", "1")
        request.add_header("Authorization", self._auth_header())

        with self._open(request, timeout=20) as response:
            data = response.read()

        root = ET.fromstring(data)
        namespace = {"d": "DAV:"}
        items = []

        for entry in root.findall("d:response", namespace):
            href_element = entry.find("d:href", namespace)
            if href_element is None:
                continue

            href = href_element.text
            try:
                _, listed_segments = self._delete_target(url, href)
                name = listed_segments[-1]
            except (ValueError, UnicodeError):
                # Never expose unverified/outside hrefs as navigable entries.
                continue

            prop = ET.Element("{DAV:}prop")
            for propstat in entry.findall("d:propstat", namespace):
                if propstat.findtext("d:status", "", namespace).split()[1:2] == ["200"]:
                    found = propstat.find("d:prop", namespace)
                    if found is not None:
                        prop.extend(list(found))
            resource_type = prop.find("d:resourcetype", namespace)
            is_directory = (resource_type.find("d:collection", namespace) is not None
                            if resource_type is not None else href.endswith("/"))

            size = ""
            last_modified = ""
            content_type = ""

            if prop is not None:
                size_element = prop.find("d:getcontentlength", namespace)
                modified_element = prop.find("d:getlastmodified", namespace)
                type_element = prop.find("d:getcontenttype", namespace)

                if size_element is not None and size_element.text:
                    size = size_element.text

                if modified_element is not None and modified_element.text:
                    last_modified = modified_element.text

                if type_element is not None and type_element.text:
                    content_type = type_element.text

            items.append({
                "name": name,
                "path": href,
                "isDirectory": is_directory,
                "resourceTypeKnown": resource_type is not None and not (resource_type.text or "").strip()
                    and all(child.tag == "{DAV:}collection" for child in resource_type),
                "resourceId": prop.findtext("d:resource-id/d:href", "", namespace),
                "size": size,
                "lastModified": last_modified,
                "contentType": content_type
            })

        return items

    def _auth_header(self):
        token = base64.b64encode(
            f"{self.user}:{self.password}".encode()
        ).decode()
        return f"Basic {token}"

    def download_file(self, path, destination, progress=None, control=None, max_bytes=None):
        """Stream to a sibling .part file; publish only a complete response."""
        request = urllib.request.Request(self._resolve_url(path), method="GET")
        request.add_header("Authorization", self._auth_header())
        request.add_header("Accept-Encoding", "identity")
        partial = destination + ".part"
        try:
            if control:
                control.check()
            with self._open(request, timeout=30) as response:
                if control:
                    control.check()
                if response.status != 200:
                    raise ValueError("Unexpected download response: HTTP {}".format(response.status))
                try:
                    total = int(response.headers.get("Content-Length", ""))
                    if total < 0:
                        total = None
                except (ValueError, TypeError):
                    total = None
                if max_bytes is not None and total is not None and total > max_bytes:
                    raise DownloadSizeLimit("Text preview size limit.")
                try:
                    free = shutil.disk_usage(os.path.dirname(destination)).free
                except OSError:
                    free = None  # Actual write errors remain authoritative.
                if free is not None and free < (total or 0) + 1024 * 1024:
                    raise OSError(errno.ENOSPC, "Insufficient local storage")
                received = 0
                last_update = 0
                if progress:
                    progress(0, total)
                with open(partial, "xb") as target:
                    while True:
                        if control:
                            control.check()
                        chunk = response.read(64 * 1024)
                        if control:
                            control.check()
                        if not chunk:
                            break
                        if max_bytes is not None and received + len(chunk) > max_bytes:
                            raise DownloadSizeLimit("Text preview size limit.")
                        if target.write(chunk) != len(chunk):
                            raise OSError(errno.EIO, "Incomplete local write")
                        received += len(chunk)
                        if total is not None and received > total:
                            raise ValueError("Download exceeds the announced size.")
                        now = time.monotonic()
                        if progress and now - last_update >= 0.1:
                            progress(received, total)
                            last_update = now
                    if total is not None and received != total:
                        raise ValueError("The download ended before the file was complete.")
                    target.flush()
                    os.fsync(target.fileno())
            if control:
                control.publish(partial, destination)
            else:
                os.replace(partial, destination)
            if progress:
                progress(received, total)
            return received
        except BaseException:
            try:
                os.unlink(partial)
            except FileNotFoundError:
                pass
            raise

    def upload_file(self, local_file, remote_path, progress=None):
        url = self._resolve_url(remote_path)
        with open(local_file, "rb") as source:
            total = os.fstat(source.fileno()).st_size

            def chunks():
                sent = 0
                last_update = 0
                if progress:
                    progress(0, total)
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
                    sent += len(chunk)
                    now = time.monotonic()
                    if progress and (now - last_update >= 0.1 or sent == total):
                        progress(sent, total)
                        last_update = now

            request = urllib.request.Request(url, data=chunks(), method="PUT")
            request.add_header("Authorization", self._auth_header())
            request.add_header("Content-Length", str(total))
            with self._open(request, timeout=60) as response:
                if response.status not in (200, 201, 204):
                    raise ValueError("Unexpected upload response: HTTP {}".format(response.status))
                return True
