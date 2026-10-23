# UT WebDAV Browser — quick user guide

For the 1.0.19 release candidate.

## Connect

1. Enter the full WebDAV endpoint provided by your server administrator. Use
   HTTPS, and enter the final endpoint rather than a redirecting web login page.
2. Enter your username and password in their separate fields. Credentials must
   not be embedded in the URL.
3. Choose **Connect**. After success, the app remembers the URL and username.
   You must enter your password again after restarting.

The first launch starts with empty fields. **Delete saved connection settings**
on the login page clears the saved URL and username. It does not delete server
files or local document copies. Enter different settings and connect
successfully to replace the saved values.

## Browse and manage files

Tap a folder to open it. Use **Back** to return and **Refresh** to reload the
listing. Header actions can be in the overflow menu on a small screen. Swipe a
file row to reveal available actions; folder and file actions differ.

- **New folder** creates a directory in the currently open folder. Enter a name
  without `/` or `\`; empty names, `.` and `..` are not accepted. Spaces,
  umlauts and literal percent signs are supported.
- **Upload** opens a Content Hub source picker. Choose File Manager or another
  available source, then select local files. Uploads go to the currently open
  WebDAV folder and run sequentially. **An existing remote file with the same
  name can be overwritten.** Upload has no editor-style ETag protection.
- **Delete…** first checks the selected resource, then asks for confirmation.
  Deleting a folder may permanently remove all its files and subfolders. Use
  **Cancel** if unsure. There is no undo in this app.

If a connection breaks during a write or deletion, its outcome may be unknown.
Refresh and check the server before trying again. Do not assume the operation
failed just because its confirmation did not arrive.

## Download one or several files

For one file, reveal **Download…**, then select a receiving app. To save it in a
folder, choose File Manager and complete its destination selection. Wait for
its import result. Downloading into the app's temporary cache alone is not the
same as saving a permanent copy in your chosen folder.

For several files:

1. Choose **Select files** in the header.
2. Tick files, or use **Select all**. Folders cannot be selected. **Clear
   selection** removes the selection; **Leave selection** exits without a job.
3. Choose **Download**. The app downloads one file at a time and displays its
   name, position and progress. Overall progress is weighted by file, not bytes.
4. Check the successful, failed and cancelled counts. An individual failure
   does not automatically stop the remaining files.
5. Choose **Save downloaded files…** to hand successful results to File Manager
   through the Content Hub. Check the receiver's import results.
6. Once your saved copies are verified, use **Discard results and temporary
   files** to release the job's cached results.

**Cancel downloads** requests cancellation immediately. A blocked network read
may take until its timeout to stop. No further files start after cancellation;
already successful files remain available. Leaving a folder clears its
selection. Conflicting file names within a job are rejected rather than silently
renamed.

File Manager may report that Content Hub does not overwrite existing files.
Choose a different destination folder, or manage the existing copy in File
Manager before exporting again. The app does not force an overwrite or invent
a new name automatically.

## Preview and open documents

Tap a TXT or Markdown file for plain-text preview, or JPEG/PNG for image preview.
Markdown is shown as source text, not a formatted page. The PDF page offers
**Open PDF**, which needs an installed external reader. Other file types are
handed to a Content Hub destination picker; their viewing support depends on
installed apps.

Use **Save…** in a preview header to export the downloaded original file. Use
the file-row action **Open in another app…** for an explicit external handover.
Editing such a copy in another app does **not** save it back to WebDAV.

If an external app leaves the handover waiting, use **Return to app**. Source
files remain available for the receiver until the transfer finishes. **Cancel
transfer and return** is offered while cancellation is possible. Cancelling a
picker does not delete your remote file. Check the receiving app for its actual
save result; handover alone cannot confirm a particular destination file.

## Create or edit TXT/Markdown

Choose **New text file**, enter a name ending in `.txt` or `.md`, and create the
editor page. Type your text, then choose **Save on server** to create the remote file.
Opening the editor alone does not create a remote file. If the chosen name
already exists, choose another name; new editor files never replace it.

To edit an existing file, reveal its **Edit…** row action. Tapping the file
normally opens preview instead. The editor supports valid UTF-8 and consistent
LF or CRLF line endings and preserves an existing UTF-8 BOM.

- **Save on server** (disk icon) saves only when the app can verify the original version
  safely with a strong ETag.
- **Save under a new name…** (plus icon) creates a separate file in the same
  WebDAV folder. An existing name is refused.
- Leaving with unsaved changes opens a warning. Choose **Continue editing** to
  keep working, or explicitly discard the changes to leave.

If the file changed on the server, the editor reports a conflict and keeps your
text. Do not repeatedly press Save on server. Save under a new name to keep your version,
then compare it with the server's current file. To reload, leave the editor
and open the file again; first preserve any unsaved text you need. Missing or
weak ETags also require **Save under a new name…**. A successful save whose new
version cannot be verified may require reloading before another overwrite.

After a timeout or an uncertain result, inspect the server before retrying.
There is no automatic retry and no persistent draft recovery. Do not close the
app while relying on unsaved text.

## Large files and storage

- Text preview accepts at most **1 MiB**. Use **Download…** for larger files.
- Editing accepts at most **256 KiB of UTF-8 bytes**, not 256 thousand visible
  characters. Unicode characters can require several bytes each.
- Ordinary downloads stream to disk and do not load the whole file into RAM.
  Keep enough free storage for downloads and export copies. Image display and
  external viewers have their own memory and format limits.
- Unknown download sizes show bytes received instead of a percentage.
- Do not clear app caches while transfers or external readers are active. Cache
  cleanup does not remove copies already saved by File Manager or other apps.

See [PRIVACY.md](PRIVACY.md) for retention and security details, and
[README.md](README.md) for build instructions and compatibility notes.

## Support

For support, contact [utwebdavbrowser@dk-service.de](mailto:utwebdavbrowser@dk-service.de).
Include the app version, device model, Ubuntu Touch version and steps to reproduce
the issue. Never send passwords, Authorization headers or private document contents.
