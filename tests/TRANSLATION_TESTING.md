# Translation testing — release preparation, package version 1.0.18

The application uses one Gettext domain, `utwebdavbrowser.dkuschinsky`, for QML
and Python. `po/de.po` contains 199 fully populated messages. Brand names and
protocol notation such as HTTP remain unchanged. English message IDs are the
fallback. File names, paths, editor contents, protocol headers, error codes and
state values are not translated.

CMake extracts QML/JavaScript and Python `tr()` literals into the POT. It compiles
the German PO with the existing Gettext tooling and installs the catalog at:

```text
share/locale/de/LC_MESSAGES/utwebdavbrowser.dkuschinsky.mo
```

QML binds this package-local directory before opening the login page. Python
uses the same directory relative to its installed source files. Language choice
uses the session's locale/language environment, with normal Gettext regional
fallback (for example, de_CH to de). No in-app language preference is stored.
Restart the app after changing the system language so both components use the
same new language. Missing messages/catalogs fall back to English; unreadable
Python catalogs also fall back without blocking startup.

## Automated checks

1. Build with `clickable build` so QML integration tests can load the installed
   app and its real compiled catalog.
2. Run `python3 -B -m unittest discover -s tests -p 'test_*.py'`. The translation
   tests check complete POT coverage, UTF-8, `%1`/`%2`/`%3` preservation, spacing,
   regional locale selection, language precedence, missing/damaged catalogs,
   Python editor/security messages and unchanged user data. Tests use synthetic
   responses only.
3. Validate the catalog with
   `msgfmt --check --check-format --statistics -o /tmp/utwebdav-de.mo po/de.po`
   inside the existing Clickable environment. There must be no fuzzy or missing
   translations.
4. Run the existing QML suites, JavaScript suites and three smoke harnesses.
5. Run `qmltestrunner -input tests/qml_i18n` in the Clickable runtime under
   `de_DE.UTF-8`, `en_GB.UTF-8` and `fr_FR.UTF-8`, setting LANG and LC_ALL to the
   tested locale and clearing LANGUAGE. Use Xvfb when no display is available.
   These tests load the installed Main.qml, verify real UI text and Python
   responses, verify English fallback, and check a narrow login layout. Login
   screenshots are written to the ignored build directory.
6. Inspect the Click archive: its German MO must be byte-identical to the
   installed MO, and loading it with GNUTranslations must translate `Password`
   to `Passwort` and retain unknown English messages unchanged.

Desktop starts can be checked separately with:

```sh
clickable desktop --lang de_DE.UTF-8
clickable desktop --lang en_GB.UTF-8
```

Close the first instance before starting the second. A desktop Content Hub
service is not guaranteed to be available; test receiver apps on real devices.

## POCO and tablet checks

Install the rebuilt 1.0.18 Click package on both test devices. Use disposable
files and folders for operations that write or delete data.

1. Set the Ubuntu Touch system language to German. Follow any system request
   to restart the session, fully close the app and reopen it. Check the login
   fields, connection-settings deletion and fixed login errors are German.
2. Check both portrait and landscape layouts. Verify action menus, dialogs,
   long warnings and selection buttons remain readable and reachable on the
   phone and tablet. File names containing umlauts or markup characters must
   remain unchanged.
3. Browse, upload and download a small test file. Check progress and completion
   messages. Select several files, clear/select all, cancel a batch and export
   successful results. Check File Manager's import result separately.
4. Create a test folder. Open the DELETE confirmation and check its German
   permanent-deletion warning. Cancel it, then confirm only on disposable data.
5. Preview TXT, Markdown, an image and a PDF. Check Save/Open labels and export
   cancellation/return. Receiving apps use their own translations.
6. Edit a disposable TXT/Markdown file. Check Save on server, Save under a new
   name, unsaved-changes navigation and ETag conflicts. Check that unsaved text
   remains after an error. Test the 256-KiB editor and 1-MiB preview limits and a
   network error; no exception detail, private URL or credential may appear.
7. Switch the system language to English, restart the app and repeat the key
   login, editor and export flows. English is expected throughout the app.
8. Optionally select a different unsupported system language and restart. The
   app's own messages must fall back to English. Platform controls and receiving
   apps may be translated independently.

This phase does not change WebDAV, editor-save or Content Hub transfer logic,
permissions, dependencies or the package version. Some screen content is
necessarily outside the app's translation catalog: server file names, edited
text, installed-app names and messages inside receiving applications.
