# Privacy and security

This document describes UT WebDAV Browser package version 1.0.18 with the
release-preparation security corrections. It covers the app's own code, not
the privacy policies of a WebDAV provider, Ubuntu Touch or receiving apps.

## Network connections and telemetry

The app connects to the WebDAV endpoint you enter to authenticate, list files,
read and write data, create folders and delete confirmed resources. Your server
receives your account credentials, requested paths and the contents involved in
those operations. Its administrator may keep access logs or other records.

The current code contains no telemetry, analytics, advertising, crash-report
submission or automatic update-check connections. It does not send usage data
to the app developer. External apps and operating-system services may have
their own network activity and privacy policies.

WebDAV uses HTTP Basic authentication. **Use HTTPS** to protect credentials and
file contents in transit. If you deliberately enter an HTTP endpoint, those
transmissions are not encrypted. The app does not fall back from HTTPS to HTTP
and refuses HTTP redirects for authenticated requests, including redirects to
the same host. Enter the final WebDAV endpoint. Normal TLS certificate
verification is not disabled by the app.

## Saved connection settings

After a successful login, the app saves only the WebDAV URL and username. These
values are restored in the login form after restarting. A failed login does not
replace previously saved settings. If saving fails after a successful login,
the app reports a warning.

The configuration is `connection.json` inside the
`utwebdavbrowser.dkuschinsky` directory under `XDG_CONFIG_HOME`, or `~/.config`
when that variable is unset. The directory has permissions `0700`; the file
has permissions `0600`. Updates use a temporary file and atomic replacement.
These are access restrictions, not encryption: the URL and username remain
readable to processes that can access the file. A URL may itself reveal an
account name or private server path. URLs containing embedded credentials,
queries or fragments are rejected; do not put secrets in a URL path either.

WebDAV passwords are **not persisted** in files or QML settings. They remain in
process memory for the session, including in active operation state. No
keyring-based password storage is implemented. Process termination releases
that memory, but the app makes no guarantee of cryptographic memory erasure.

Use **Delete saved connection settings** on the login page to remove the
stored URL and username. This does not revoke your server credentials, remove
remote data or erase exported files and cached documents. Connect successfully
with different values to replace the saved connection.

## Local documents, cache and retention

Downloaded documents are written to the app's cache, under
`utwebdavbrowser.dkuschinsky/downloads` in `XDG_CACHE_HOME` or `~/.cache`.
Files are streamed in 64-KiB blocks to a sibling `.part` file and are published
only after the download completes. Normal failures and cancellation clean up
partials; an abrupt process or device failure can leave files behind.

Preview and export consumers hold separate cache references. Ordinary cached
files are removed when their last reference is released, unless deliberately
retained. Successful batch results remain available until discarded, and
ongoing exports keep their own references. Inactive batch cache directories
are checked for cleanup at startup. This is not a blanket removal of all old
cache files.

PDF downloads are deliberately retained for external readers, including after
the preview closes. External transfers that do not report completion can also
retain their source files. Legacy preview/download files and interrupted
operations may therefore leave cached documents on storage. Files imported
for upload can also exist in the Content Hub's app-specific `HubIncoming`
cache. The app does not promise immediate deletion of all such copies.

Cache contents are **not encrypted by the app**, and filesystem deletion is
not a secure-erasure guarantee. Do not clear the app's cache while a preview,
download or external transfer still needs it. Protect the device and consider
its storage and backup policies when handling sensitive documents.

## Content Hub and other apps

Choosing an upload source lets another app supply a local file to UT WebDAV
Browser. Choosing an export destination gives that app access to a downloaded
copy. File Manager can save it in a folder selected by you; other apps may
make their own copies or backups. Those copies are outside this app's cache
lifecycle and must be managed in the receiving app.

A handover confirmation is not proof that the receiver saved the file in the
intended folder. Check its import result. The receiver may refuse duplicate
names. UT WebDAV Browser does not directly write into another app's directory
or force an overwrite there. If a receiver never finishes, **Return to app**
keeps the source file available instead of deleting it prematurely. Changes
made in another app are not automatically uploaded to WebDAV.

## Text preview and editor

TXT/Markdown preview is limited to **1 MiB of source bytes**, including when the
server does not provide a trustworthy size. Text is displayed as plain text;
HTML and Markdown are not rendered as markup. Preview decoding may replace
invalid UTF-8 characters, but exporting the cached file preserves its original
bytes.

The separate editor has a **256-KiB UTF-8 byte limit** for both loading and
saving, including any UTF-8 BOM. It rejects invalid UTF-8 and unsupported
formats such as mixed line endings, rather than silently converting them.
Text and unsaved changes stay in memory; there is no automatic unencrypted
draft file. Unsaved text can be lost if the app is terminated.

**ETag conflict protection applies to editor saves, not ordinary uploads.**
Existing files require the original strong GET ETag and `If-Match`. Missing or
weak ETags require saving under a new name. New editor files use
`If-None-Match: *` to avoid overwriting an existing resource. Conflicts, timeouts
and uncertain save results are not retried automatically; the text remains in
the open editor after an error. Further overwrites may require reloading.

**Normal uploads can overwrite existing remote files with the same name.**
They do not use the editor's conditional-save protection. Keep backups and
check the destination before uploading. Confirmed folder deletion may remove
all descendants permanently; the app provides no recovery mechanism.

## Paths, permissions and error logs

Client-side checks restrict operations to the configured WebDAV root and
validate path segments and resource identities where required. Server-side
permissions, URL interpretation and storage behaviour remain the server's
responsibility. No client can protect data from a malicious server that already
controls it.

The app requests only the existing networking and Content Hub permission
groups: `networking`, `content_exchange` and `content_exchange_source`.

Application errors use fixed messages instead of exposing raw exceptions,
tracebacks, Authorization headers, passwords or private WebDAV addresses.
There is no automatic log upload. Ubuntu Touch, networking components, Content
Hub and receiving apps can produce their own diagnostic messages, potentially
including local paths or document names. Review and redact logs and screenshots
before sharing them; never include passwords, tokens, Authorization headers,
private URLs or document contents.
