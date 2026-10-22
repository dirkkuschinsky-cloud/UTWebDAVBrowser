# Release security checks — v1.0.19 preparation (package version 1.0.18)

These changes deliberately retain package version 1.0.18. No permissions or dependencies are added. Automated tests use synthetic credentials and simulated HTTP responses only.

## Transport and paths

All authenticated operations use a private urllib opener which refuses 301, 302, 303, 307 and 308 before another request is constructed. This includes same-origin redirects. Redirect chains, port changes, URL user information and HTTPS downgrades therefore cannot forward Authorization to a redirected destination. Configure the final WebDAV endpoint instead of relying on redirects. A rejected redirect is never retried automatically; for a write operation, refresh before deciding whether to try again.

Legacy list, GET, PUT and MKCOL now share the existing segment-based root checks used by DELETE/editor operations. Segments are decoded once for identity checks, while their encoded spelling is retained for transport. Dot segments, encoded separators, malformed escapes, foreign origins and outside-root hrefs are rejected. `/` and the legacy empty path mean the configured root. Other leading-slash paths are server-origin hrefs and must contain the configured root; base-relative paths have no leading slash. Literal `%2F` in a user-supplied new name becomes `%252F` on the wire. Listings expose only checked direct children.

The server remains responsible for its own URL interpretation and resource aliases. Client-side validation cannot constrain a malicious server's internal filesystem or a server that repeatedly decodes URLs contrary to the checked resource identity. Explicit HTTP endpoints remain supported; they do not provide HTTPS transport confidentiality. No HTTP fallback is introduced.

## Safe output and preview

Network errors are mapped to fixed messages. Raw backend tracebacks are not printed by Main.qml; dynamic debug output from BrowserPage and the unused example helper is removed. Existing batch validation messages are fixed application-defined messages, not HTTP-library exceptions.

TXT/Markdown preview uses the existing 64-KiB streaming downloader with a 1-MiB byte ceiling, enforced against both Content-Length and actual received bytes. A second bounded read guards local preview consumption. The limit applies only to preview: ordinary downloads remain streaming and can exceed it. Preview retains tolerant UTF-8 decoding and newline display behavior, while export retains original bytes. Its Label explicitly uses PlainText, including HTML-like and Markdown input. The protected 256-KiB editor and Content-Hub/cache ownership logic are unchanged.

The tests cover 35 redirect combinations through urllib's real response processor, path rejection across legacy operations, Unicode/literal percent names, filtered listings, preview boundaries/unknown or dishonest lengths, cleanup, unchanged cache bytes and sanitized errors. QML checks literal rendering and the existing preview save action. Existing suites cover editor ETags, cancellation, upload/download, DELETE/MKCOL and single/multiple Content-Hub exports.

## POCO X3 NFC and tablet checklist

Use synthetic test files and an expendable test directory. Never enter credentials in a redirect URL.

1. Sign in to the final HTTPS WebDAV endpoint; browse root and nested directories. Verify saved URL/username restoration.
2. Upload, download and create directories with spaces, umlauts, `%`, literal `%2F` and literal `%2e%2e`. Downloaded bytes and resource names must match. Check the list stays inside the configured root.
3. On a controlled test server, return a same-origin redirect followed by a foreign-host redirect, a changed-port redirect and an HTTPS-to-HTTP redirect. Each operation must fail without a second request. Confirm with test-server request counters, not by logging Authorization.
4. Preview TXT and MD containing `<b>literal</b>`, an HTML image/link and Unicode: display the literal characters, with no embedded image or link. Save/export and compare original bytes.
5. Preview files at 1 MiB, above 1 MiB, and streamed without Content-Length. Over-limit preview must show the fixed message; the normal Download action must still save the large file. Retry a small preview afterward.
6. Trigger offline, denied-access, missing-file and server-error responses. Messages/logs must contain no private URL, credentials, Authorization or raw traceback. The app must remain usable afterward.
7. Recheck single and batch downloads, cancellation, export destination cancellation, repeated preview saving, external PDF reader lifetime, MKCOL and confirmed DELETE using disposable data.
8. Recheck TXT/MD editor conflict protection and “Save under a new name”; editor text and original ETag rules must remain intact.

Desktop tests cannot fully validate confined device networking, real Content-Hub receivers, or device memory/rendering behavior. Final verification on both devices remains required. This phase is a targeted hardening change, not a complete audit of malicious-server responses in every parser.
