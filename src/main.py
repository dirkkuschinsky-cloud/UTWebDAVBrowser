from translations import tr
import tempfile
import os
import socket
import urllib.error
import urllib.parse
import shutil
import errno
import http.client
import uuid
import threading
import functools
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from webdav import WebDavClient, DeleteSafetyError, DownloadCancelled, DownloadSizeLimit, UnsafeRedirectError
from download_jobs import DownloadJobs, safe_name, JobValidationError
from text_editor import Editor
from batch_cache import BatchCache
from config import Config, validate_server

TEXT_PREVIEW_LIMIT = 1024 * 1024
PREVIEW_SIZE_MESSAGE = tr("The file is too large for text preview (limit: 1 MiB). Use Download to save it.")
REDIRECT_MESSAGE = tr("The server redirected the request. Use its final WebDAV address.")

client = WebDavClient()
config = Config()
_delete_selections = {}
_cache_lock = threading.RLock()
_batch_cache = BatchCache()


def _job_busy():
    return (("_jobs" in globals() and _jobs.busy) or
            ("_editor" in globals() and _editor.lock.locked()))


def _busy_result():
    return {"success": False, "message": tr("Wait until the download job has stopped.")}


def _cache_locked(function):
    @functools.wraps(function)
    def locked(*args, **kwargs):
        with _cache_lock:
            return function(*args, **kwargs)
    return locked


def _cache_root():
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                        "utwebdavbrowser.dkuschinsky", "downloads")



def load_connection():
    try:
        return dict(success=True, **config.load())
    except (OSError, ValueError, UnicodeError):
        return {"success": False, "server": "", "username": "",
                "message": tr("Saved connection settings could not be loaded. Please enter them again or delete them.")}


def delete_connection():
    try:
        config.delete()
        return {"success": True}
    except (OSError, ValueError):
        return {"success": False, "message": tr("Saved connection settings could not be deleted.")}


def connect(server, username, password):
    if _job_busy():
        return _busy_result()
    _delete_selections.clear()
    if "_editor" in globals():
        _editor.sessions.clear()
    try:
        server = validate_server(server)
    except (ValueError, TypeError):
        return {"success": False, "message": tr("Enter a valid HTTP(S) WebDAV URL without embedded credentials, query or fragment.")}
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        return {"success": False, "message": tr("Server, username and password are required.")}
    try:
        ok = client.connect(server, username, password)
    except Exception:
        # Neither exception messages nor request arguments may expose secrets.
        ok = False
    if not ok:
        return {"success": False, "message": tr("Connection failed. Please check the server and login details.")}
    try:
        config.save(server, username)
    except (OSError, ValueError, UnicodeError):
        return {"success": True, "saved": False, "message": tr("Connection successful."),
                "warning": tr("Connected, but the connection settings could not be saved.")}
    return {"success": True, "saved": True, "message": tr("Connection successful.")}

def create_directory(parent_path, name):
    if _job_busy():
        return _busy_result()
    try:
        return {"success": client.create_directory(parent_path, name)}
    except UnsafeRedirectError:
        return {"success": False, "message": REDIRECT_MESSAGE}
    except urllib.error.HTTPError as error:
        messages = {
            401: tr("Authentication failed. Please check your login details."),
            403: tr("The server denied permission to create a folder here."),
            404: tr("The parent folder was not found."),
            405: tr("The name may already be in use, or the server does not allow creating folders here."),
            409: tr("The parent folder is missing or conflicts with another item."),
            507: tr("The server has insufficient storage space.")
        }
        return {"success": False, "status": error.code,
                "message": messages.get(error.code, tr("The server rejected folder creation."))}
    except (socket.timeout, TimeoutError, urllib.error.URLError, OSError, http.client.HTTPException):
        return {"success": False,
                "message": tr("The connection failed. The folder may already have been created. Cancel and refresh the file list before trying again.")}
    except (ValueError, TypeError):
        return {"success": False, "message": tr("Invalid folder name, parent path or server response.")}
    except Exception:
        return {"success": False, "message": tr("The folder could not be created.")}



def _delete_error(error, deleting=False):
    if isinstance(error, urllib.error.HTTPError):
        messages = {
            401: tr("Authentication failed. Please check your login details."),
            403: tr("The server denied permission to delete this resource."),
            404: tr("The resource no longer exists. Refresh the file list."),
            405: tr("The server does not allow this deletion."),
            409: tr("The resource could not be deleted because of a conflict."),
            412: tr("The resource changed. Refresh and select it again."),
            423: tr("The resource or one of its children is locked."),
        }
        return {"success": False, "status": error.code, "refresh": deleting,
                "message": messages.get(error.code, tr("The server could not complete the operation. Refresh and select again."))}
    if isinstance(error, (DeleteSafetyError, ValueError, TypeError, ET.ParseError)):
        return {"success": False, "refresh": deleting,
                "message": tr("The path, resource type or identity could not be verified, or the resource changed. Refresh and select it again.")}
    return {"success": False, "refresh": deleting,
            "message": (tr("The connection or response failed. Deletion may already have occurred. Refresh before selecting again.")
                        if deleting else tr("The resource could not be checked. Please check the connection and refresh."))}


def prepare_delete(parent_path, path):
    if _job_busy():
        return _busy_result()
    _delete_selections.clear()
    try:
        snapshot = client.inspect_delete(parent_path, path)
        token = uuid.uuid4().hex
        _delete_selections[token] = (client.server, client.user, parent_path, path, snapshot)
        return {"success": True, "token": token, "name": snapshot["name"],
                "isDirectory": snapshot["isDirectory"]}
    except Exception as error:
        return _delete_error(error)


def cancel_delete(token):
    _delete_selections.pop(token, None)
    return {"success": True}


def delete_resource(token):
    if _job_busy():
        return _busy_result()
    # Consume before any network access: double invocation cannot send DELETE twice.
    selection = _delete_selections.pop(token, None)
    if selection is None:
        return {"success": False, "message": tr("Select the resource again before deleting it.")}
    server, user, parent, path, snapshot = selection
    if (server, user) != (client.server, client.user):
        return {"success": False, "message": tr("The connection changed. Select the resource again.")}
    try:
        return client.delete_resource(parent, path, snapshot)
    except Exception as error:
        return _delete_error(error, deleting=True)

def list_directory(path):
    if _job_busy():
        return _busy_result()
    try:
        items = client.list_directory(path)

        for item in items:
            item["displaySize"] = format_size(item.get("size", ""))
            item["selectKey"] = ""
            try:
                if item.get("resourceTypeKnown") and not item["isDirectory"]:
                    _, segments = client._delete_target(path, item["path"])
                    safe_name(segments[-1])
                    identity = item.get("resourceId") or json.dumps(segments)
                    item["selectKey"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            except (ValueError, TypeError):
                pass

        return {
            "success": True,
            "items": items
        }
    except Exception:
        return {
            "success": False,
            "message": tr("The directory could not be loaded. Please check the connection and permissions."),
            "items": []
        }


def list_root():
    return list_directory("/")

# Each consumer owns a unique lease; releasing it twice cannot affect another.
_downloads = {}
_download_leases = {}


@_cache_locked
def _download_info(filename, reference):
    entry = _downloads[filename]
    return {"success": True, "localFile": filename, "localUrl": Path(filename).as_uri(),
            "fileName": os.path.basename(filename), "remotePath": entry["remotePath"],
            "cacheRef": reference}


@_cache_locked
def _new_download_reference(filename):
    reference = uuid.uuid4().hex
    _download_leases[reference] = filename
    _downloads[filename]["references"].add(reference)
    return reference


@_cache_locked
def acquire_download(info):
    """Acquire an independent export lease, or use the existing streaming download."""
    if _job_busy():
        return _busy_result()
    filename = info.get("localFile", "")
    entry = _downloads.get(filename)
    if entry and entry["remotePath"] == info.get("remotePath") and os.path.isfile(filename):
        return _download_info(filename, _new_download_reference(filename))
    path = info.get("remotePath")
    if not path:
        return {"success": False, "message": tr("The cached file is no longer available.")}
    return download_file(path)


@_cache_locked
def pin_download(reference):
    """Keep PDFs available to external readers after the preview is closed."""
    filename = _download_leases.get(reference)
    if filename not in _downloads:
        return {"success": False, "message": tr("Unknown temporary download.")}
    _downloads[filename]["pinned"] = True
    return {"success": True}


@_cache_locked
def release_download(reference):
    # Compatibility for existing callers passing a local filename/URL: release
    # only the original lease, never an independently acquired export lease.
    if reference.startswith("file://"):
        reference = urllib.parse.unquote(urllib.parse.urlsplit(reference).path)
    if reference in _downloads:
        reference = _downloads[reference]["originalReference"]
    filename = _download_leases.pop(reference, None)
    if filename is None or filename not in _downloads:
        return {"success": False, "message": tr("Unknown or already released download reference.")}
    entry = _downloads[filename]
    entry["references"].discard(reference)
    if entry["references"] or entry["pinned"]:
        return {"success": True}
    try:
        shutil.rmtree(entry["directory"])
        _batch_cache.forget(entry["directory"])
        del _downloads[filename]
        return {"success": True}
    except OSError:
        # The reference is consumed even when filesystem cleanup fails.
        return {"success": False, "message": tr("The temporary download could not be removed.")}


def read_text_file(path, keep_file=False):
    result = download_file(path, _max_bytes=TEXT_PREVIEW_LIMIT)
    if not result["success"]:
        result["text"] = ""
        return result
    retained = False
    try:
        with open(result["localFile"], "rb") as source:
            data = source.read(TEXT_PREVIEW_LIMIT + 1)
        if len(data) > TEXT_PREVIEW_LIMIT:
            return {"success": False, "message": PREVIEW_SIZE_MESSAGE, "text": ""}
        # Keep the preview's tolerant decoding/newline behavior. Export still
        # owns the original bytes; the protected editor is entirely separate.
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        if keep_file:
            retained = True
            result["text"] = text
            return result
        return {"success": True, "text": text}
    except OSError:
        return {"success": False, "message": tr("The downloaded text could not be read."), "text": ""}
    finally:
        if not retained:
            release_download(result["cacheRef"])


def download_file(path, _job_id=None, _control=None, _progress=None, _client=None, _name=None, _max_bytes=None):
    if _job_busy() and (_job_id is None or not _jobs.owns(_job_id)
                        or threading.current_thread() is not _jobs.thread):
        return _busy_result()
    directory = None
    try:
        import pyotherside
        cache = _cache_root()
        os.makedirs(cache, exist_ok=True)
        directory = (_batch_cache.create(cache) if _job_id else
                     tempfile.mkdtemp(prefix="download-", dir=cache))
        name = urllib.parse.unquote(urllib.parse.urlsplit(path).path.rsplit("/", 1)[-1])
        name = os.path.basename(name)
        if not name or name in (".", "..") or "\x00" in name:
            name = "download"
        if _name is not None:
            name = safe_name(_name)
        filename = os.path.join(directory, name)
        progress = _progress or (lambda received, total: pyotherside.send("downloadProgress", received, total))
        if _control is None:
            if _max_bytes is None:
                client.download_file(path, filename, progress)
            else:
                client.download_file(path, filename, progress, max_bytes=_max_bytes)
        else:
            _client.download_file(path, filename, progress, control=_control)
        with _cache_lock:
            _downloads[filename] = {"directory": directory, "remotePath": path,
                                    "references": set(), "pinned": False}
            reference = _new_download_reference(filename)
            _downloads[filename]["originalReference"] = reference
            return _download_info(filename, reference)
    except DownloadSizeLimit:
        return {"success": False, "message": PREVIEW_SIZE_MESSAGE}
    except DownloadCancelled:
        return {"success": False, "cancelled": True, "message": tr("Download cancelled.")}
    except UnsafeRedirectError:
        return {"success": False, "message": REDIRECT_MESSAGE}
    except urllib.error.HTTPError as error:
        messages = {401: tr("Authentication failed. Please check your login details."),
                    403: tr("The server denied permission to download this file."),
                    404: tr("The file was not found on the server.")}
        return {"success": False, "status": error.code,
                "message": messages.get(error.code, tr("The server rejected the download."))}
    except (socket.timeout, TimeoutError):
        return {"success": False, "message": tr("The download timed out. Please check the connection.")}
    except urllib.error.URLError:
        return {"success": False, "message": tr("The server could not be reached. Please check the connection.")}
    except OSError as error:
        message = (tr("There is not enough free space for this download.")
                   if error.errno in (errno.ENOSPC, errno.EDQUOT)
                   else tr("The download could not be written or the connection was interrupted."))
        return {"success": False, "message": message}
    except (ValueError, http.client.HTTPException):
        return {"success": False, "message": tr("The download was incomplete or the server response was invalid.")}
    except Exception:
        return {"success": False, "message": tr("The file could not be downloaded.")}
    finally:
        with _cache_lock:
            retained = any(value["directory"] == directory for value in _downloads.values())
        if directory is not None and not retained:
            # Do not hide a failed download with a secondary cleanup exception.
            try:
                shutil.rmtree(directory)
            except OSError:
                pass
            finally:
                _batch_cache.forget(directory)


def format_size(size):
    if size is None or size == "":
        return ""

    size = int(size)

    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"

def upload_file(local_file, remote_path):
    if _job_busy():
        return _busy_result()
    try:
        import pyotherside
        success = client.upload_file(
            local_file, remote_path,
            lambda sent, total: pyotherside.send("uploadProgress", sent, total)
        )

        return {
            "success": success
        }

    except UnsafeRedirectError:
        return {"success": False, "message": REDIRECT_MESSAGE}
    except urllib.error.HTTPError as error:
        messages = {
            401: tr("Authentication failed. Please check your login details."),
            403: tr("The server denied permission to upload here."),
            404: tr("The destination folder was not found."),
            409: tr("The destination folder does not exist or conflicts with another item."),
            413: tr("The file exceeds the server's upload size limit."),
            507: tr("The server has insufficient storage space.")
        }
        return {"success": False, "message": messages.get(
            error.code, tr("The server rejected the upload.")
        ), "status": error.code}
    except (socket.timeout, TimeoutError):
        return {"success": False, "message": tr("The upload timed out. Please check the connection.")}
    except urllib.error.URLError:
        return {"success": False, "message": tr("The server could not be reached. Please check the connection.")}
    except OSError:
        return {"success": False, "message": tr("The local file could not be read or the connection was interrupted.")}
    except Exception:
        return {"success": False, "message": tr("The upload could not be completed. Check the connection and destination.")}



def _prepare_job_files(parent, paths):
    if not isinstance(paths, list) or not paths or len(paths) > 1000:
        raise JobValidationError(tr("Select between 1 and 1000 files."))
    selected = []
    for path in paths:
        _, segments = client._delete_target(parent, path)
        selected.append(segments)
    available = {}
    for item in client.list_directory(parent):
        try:
            if not item.get("resourceTypeKnown") or item["isDirectory"]:
                continue
            url, segments = client._delete_target(parent, item["path"])
            name = safe_name(segments[-1])
            try:
                size = int(item.get("size", ""))
                if size < 0:
                    size = None
            except (ValueError, TypeError):
                size = None
            if segments in available and available[segments]["identity"] != segments:
                continue  # Preserve a known resource-id across encoded href aliases.
            available[segments] = {"path": url, "name": name, "sizeHint": size,
                                   "identity": item.get("resourceId") or segments}
        except (ValueError, TypeError):
            continue
    entries, seen = [], set()
    for segments in selected:
        if segments not in available:
            raise JobValidationError(tr("The selection contains missing, unknown or non-file resources. Refresh and select again."))
        item = available[segments]
        if item["identity"] not in seen:
            seen.add(item["identity"])
            entries.append({key: value for key, value in item.items() if key != "identity"})
    worker = WebDavClient()
    worker.server, worker.user, worker.password = client.server, client.user, client.password
    return entries, worker


_jobs = DownloadJobs(_prepare_job_files,
    lambda path, job_id, control, progress, worker, name: download_file(
        path, job_id, control, progress, worker, name), release_download, _cache_root)


def prepare_download_job(parent, paths):
    if _job_busy():
        return _busy_result()
    return _jobs.prepare(parent, paths)


def start_download_job(job_id):
    if "_editor" in globals() and _editor.lock.locked():
        return _busy_result()
    return _jobs.start(job_id)


def download_job_status(job_id):
    return _jobs.status(job_id)


def cancel_download_job(job_id):
    return _jobs.cancel(job_id)


def discard_download_job(job_id):
    return _jobs.discard(job_id)


@_cache_locked
def acquire_batch_exports(infos):
    """Export copies protect originals even if a receiver moves or edits them.

    Cache references are trusted instead of arbitrary local paths. No network
    fallback and no writes outside the application's cache are permitted.
    """
    if _job_busy():
        return _busy_result()
    results = []
    directory = None
    try:
        if not isinstance(infos, list) or not infos:
            raise ValueError()
        sources, names = [], set()
        for info in infos:
            filename = _download_leases.get(info.get("cacheRef"))
            entry = _downloads.get(filename)
            if not entry or not os.path.isfile(filename):
                raise ValueError()
            name = safe_name(os.path.basename(filename))
            if name in names:
                raise ValueError()
            names.add(name)
            sources.append((filename, entry, name))
        required = sum(os.path.getsize(source) for source, _, _ in sources)
        try:
            free = shutil.disk_usage(_cache_root()).free
        except OSError:
            free = None
        if free is not None and free < required + 1024 * 1024:
            raise OSError(errno.ENOSPC, "Insufficient export space")
        for source, entry, name in sources:
            directory = _batch_cache.create(_cache_root())
            filename = os.path.join(directory, name)
            partial = filename + ".part"
            with open(source, "rb") as incoming, open(partial, "xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=64 * 1024)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if os.path.getsize(partial) != os.path.getsize(source):
                raise OSError(errno.EIO, "Incomplete export copy")
            os.replace(partial, filename)
            _downloads[filename] = {"directory": directory, "remotePath": entry["remotePath"],
                                    "references": set(), "pinned": False}
            reference = _new_download_reference(filename)
            _downloads[filename]["originalReference"] = reference
            results.append(_download_info(filename, reference))
            directory = None
        return {"success": True, "files": results}
    except Exception:
        for info in results:
            release_download(info["cacheRef"])
        if directory is not None:
            try:
                shutil.rmtree(directory)
            except OSError:
                pass
            _batch_cache.forget(directory)
        return {"success": False, "message": tr("The export copies could not be prepared. Check available storage. Original downloads remain available.")}


# Only abandoned, marked batch directories are recovered. Live leases are
# protected by flock; legacy PDF pins and unrelated cache files are untouched.
_batch_cache.cleanup(_cache_root())


_editor = Editor(lambda: client, lambda: "_jobs" in globals() and _jobs.busy)

def open_editor(parent, path="", name=""):
    return _editor.call("open", parent, path, name)

def save_editor(token, text, new_name=""):
    return _editor.call("save", token, text, new_name)

def close_editor(token):
    return _editor.close(token)
