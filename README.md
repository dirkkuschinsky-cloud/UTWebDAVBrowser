# UT WebDAV Browser

A native Ubuntu Touch app for browsing and managing files on a WebDAV server.
The interface uses QML and Lomiri components, with a Python backend connected
through PyOtherSide. The application ID is `utwebdavbrowser.dkuschinsky`.

The current package version is **1.0.18**. OpenStore release preparation is in
progress; this document does not imply that an OpenStore release is available.

## Features

- Browse folders with file-type icons, readable file names and file sizes.
- Remember the WebDAV URL and username after a successful login.
- Upload local files through the Lomiri Content Hub, with progress reporting.
- Download individual files or select multiple files for sequential downloads,
  with progress, cancellation and a result summary for batch jobs.
- Save downloaded files to a location chosen in File Manager, or hand documents
  to another compatible app through the Content Hub.
- Preview TXT/Markdown as plain text and JPEG/PNG images internally. The PDF page
  provides an action to open the downloaded document in an external PDF reader.
- Create folders and delete individual files or folders after confirmation.
- Create and edit UTF-8 `.txt` and `.md` files in a separate, protected editor.

This is a WebDAV client, not a background synchronisation service. It does not
provide a local mirror of the server or synchronise changes made in other apps.

## Devices, environment and compatibility

Device testing has succeeded on the **Xiaomi POCO X3 NFC** and an
**Ubuntu Touch tablet**. These tests do not establish compatibility with every
Ubuntu Touch device or release. The tablet model and exact tested OS build are
not specified here, so no wider device or OS support claim is made.

Development and desktop testing use Kubuntu 24.04, Docker and Clickable. The
project requires Clickable 8.8.0 or newer and uses the `pure-qml-cmake` builder.
The current build targets the `ubuntu-sdk-20.04.1` Click framework; this is a
package framework identifier, not a claim that only one Ubuntu Touch OS version
can run the app. Desktop tests cannot fully reproduce device Content Hub
behaviour.

MagentaCLOUD, a Nextcloud-based service, has been used for successful device
tests. The app accepts a configurable WebDAV endpoint and has no hard-coded
provider address. Other Nextcloud installations and standards-compatible WebDAV
servers may work, but are not all individually certified. Server permissions,
DAV metadata, conditional request support and installed receiving apps affect
which operations are available. Use the final WebDAV endpoint supplied by your
provider: authenticated HTTP redirects are refused, including same-host ones.

## Interface language

The interface is available in English and German. It follows the Ubuntu Touch
system language automatically; unsupported languages fall back to English.
Fully close and reopen the app after changing the system language. File names
and document contents are never translated. See
[translation testing](tests/TRANSLATION_TESTING.md) for device checks.

## Build and install

Set up Clickable with its Docker build environment, then run these commands
from the repository root:

```sh
clickable desktop
clickable build
```

The build runs the Click package review. The package is normally produced at:

```text
build/all/app/utwebdavbrowser.dkuschinsky_1.0.18_all.click
```

For device testing, transfer the package to the device and install it there.
For example, with SSH configured, replace `DEVICE_ADDRESS` with your own device
address:

```sh
scp build/all/app/utwebdavbrowser.dkuschinsky_1.0.18_all.click phablet@DEVICE_ADDRESS:Downloads/
ssh -t phablet@DEVICE_ADDRESS 'sudo click install --user=phablet --allow-unauthenticated /home/phablet/Downloads/utwebdavbrowser.dkuschinsky_1.0.18_all.click'
```

This command explicitly permits an unsigned development package. Install only a
package you built or obtained from a trusted source. Launch the installed app
from the device's app overview. Installing a development package with the same
version does not make it a new public release.

## Using the app

Enter your WebDAV endpoint, username and password, then choose **Connect**.
Only the URL and username are saved, after authentication succeeds. Enter the
password again after restarting the app. The login page offers **Delete saved
connection settings**.

Tap a folder to navigate. File-row swipe actions expose **Download…**,
**Open in another app…**, **Delete…** and, for TXT/Markdown, **Edit…**. Header
actions may be in the overflow menu on a narrow screen. Use **Upload** to choose
local files through another app, **New folder** to create a directory, and
**Refresh** to reload the current listing.

For multiple downloads, use **Select files**, choose files or **Select all**,
then **Download**. After the job finishes, use **Save downloaded files…** to
export successful downloads. Downloading to the app's cache is separate from
saving to a chosen user folder. Do not discard results until the copies you need
have been saved.

Tap TXT/Markdown to preview it; use **Edit…** to change it. The editor's **Save on server**
action updates a verified existing version, or creates a new file. **Save under
a new name…** creates a separate file without replacing an existing one. See
[USER_GUIDE.md](USER_GUIDE.md) for conflicts, cancellation and export details.

## Limits and safety

- Text preview is limited to **1 MiB** of source bytes. It displays plain text,
  not rendered HTML or Markdown. Invalid UTF-8 may appear as replacement
  characters in preview; exporting that preview uses the original file bytes.
- The editor accepts at most **256 KiB of UTF-8 data**, including a UTF-8 BOM if
  present. It strictly validates UTF-8 and preserves BOM and consistent LF or
  CRLF line endings. Unsupported formats are refused rather than rewritten.
- Existing editor files are saved only with the original strong ETag and
  `If-Match`. Missing or weak ETags require saving under a new name. New editor
  files use `If-None-Match: *`. Conflicts and uncertain results are not retried
  automatically. A reload may be required before another overwrite.
- **ETag conflict protection is specific to the editor. Normal uploads can
  overwrite an existing remote file with the same name.** Check the destination
  and keep backups before uploading.
- Folder deletion can permanently remove all descendants. The app requires
  explicit confirmation; it does not provide an undo or restore function.
- Downloads stream in 64-KiB blocks to `.part` files. Complete transfers are
  published with `os.replace()`; failures and cancellation remove partials in
  normal execution. Disk space, device storage and receiving apps impose limits
  on large downloads. Large images may also require substantial rendering RAM.
- Batch downloads are sequential. Their overall progress is weighted by file,
  not total bytes. Unknown file sizes show received bytes rather than an
  invented percentage. Cancellation may wait for a blocking network timeout.
- Content Hub receivers control their own import results. The File Manager may
  refuse an existing destination name; the app does not silently rename it or
  force an overwrite. Check the receiver's result, not just the handover message.
- If an external app does not finish its transfer, **Return to app** provides a
  way back while retaining its source files. Changes made externally are not
  uploaded back to WebDAV. PDF readers require a suitable installed app.
- Unsaved editor text lives in memory only. There is no persistent draft recovery
  after a crash or app termination. Cache files may remain after interruption,
  external transfers or PDF viewing; do not assume immediate secure erasure.

## Privacy and security

Use **HTTPS**. Explicit HTTP endpoints are supported but send credentials and
file contents without transport encryption. Passwords are used in memory for
the session and are not saved in configuration files. Saved URL/username
settings use a private app configuration directory (`0700`) and file (`0600`),
with atomic replacement. These settings and downloaded caches are not encrypted
by the app.

The app validates WebDAV root boundaries, refuses redirects for authenticated
requests and uses fixed error messages instead of exposing raw backend errors.
It contains no telemetry, analytics or automatic update-check connections.
Files and credentials are sent to the server you configure; exported copies
are handled by the receiving apps. Read [PRIVACY.md](PRIVACY.md) for storage,
retention and logging details.

## Tests

Python tests use simulated WebDAV responses rather than modifying a live
account:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -p 'test_*.py'
```

QML tests are in `tests/qml_*`; run them with `qmltestrunner` in the Clickable
runtime, using an X server or Xvfb. JavaScript suites are `tests/test_*.js` and
can be run with Node.js. The three QML smoke harnesses are under `tests/qml/`.
Device checklists are provided in the testing documents under `tests/`, including
[release security checks](tests/RELEASE_SECURITY_TESTING.md). Test Content Hub
handover and UI behaviour on real devices as well as on the desktop.

## Support

For support, contact [utwebdavbrowser@dk-service.de](mailto:utwebdavbrowser@dk-service.de).
Include the app version, device model, Ubuntu Touch version and steps to reproduce
the issue. Never send passwords, Authorization headers or private document contents.

## License

Copyright (C) 2026  Dirk Kuschinsky

This project is licensed under **GPL-3.0-or-later**: the GNU General Public
License version 3 or, at your option, any later version. The complete GPL v3
text is included in [LICENSE](LICENSE) and in the Click package. This program
comes without warranty; see LICENSE for the full terms.

For the app icon's origin and intended licensing, see
[assets/README.md](assets/README.md).
