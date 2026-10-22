# v1.0.18: Texteditor

Der Editor unterstützt ausschließlich UTF-8, optional mit BOM, und einheitliche
LF-/CRLF-Zeilenenden. Die Grenze ist 256 KiB einschließlich BOM und tatsächlicher
UTF-8-/Zeilenende-Bytes. Gemischte Zeilenenden, alleinstehendes CR, binäre
Steuerzeichen und Unicode-Absatztrenner werden abgelehnt statt normalisiert.
Markdown wird als Klartext bearbeitet. Die bisherigen Viewer bleiben unverändert.

Erstellen verwendet ausschließlich If-None-Match: *, Bearbeiten ausschließlich
einen starken ETag aus dem GET. Die DAV-Ressource wird vor jedem PUT erneut geprüft.
Ein starker ETag aus der PUT-Antwort muss anschließend zur DAV-Metadatenantwort
passen, bevor weitere Überschreibungen erlaubt werden. Ohne diese Bestätigung ist
Schließen und erneutes Laden erforderlich; alternativ ist geschütztes Speichern
unter einem neuen Namen möglich. Schwache/fehlende ETags erlauben nur diese Alternative.

Kein automatischer Wiederholungsversuch nach PUT-Fehlern. Der Text bleibt sichtbar;
ein unklarer PUT-Ausgang sperrt die alte Speicherbedingung. Kein unbedingtes PUT.
Die Sicherheit bedingt einen Server, der HTTP-Vorbedingungen korrekt durchsetzt.
DAV-Prüfung und PUT sind keine serverseitige Transaktion; starke Validatoren schützen
die Repräsentation, ersetzen aber keine unveränderliche serverseitige Ressourcen-ID.

Keine Entwürfe auf Disk, keine Textinhalte in Logs oder Einstellungen. Bei einem
unerwarteten App-Ende geht ungespeicherter Text verloren. Es gibt derzeit keinen
im Click-Profil nutzbaren sicheren Schlüsselspeicher für verschlüsselte Entwürfe.

## Gerätetest POCO und Tablet

Nur eigens angelegte Testdateien verwenden.

1. Neue TXT und MD mit Umlaut, Leerzeichen, Prozent und wörtlichem %2F erstellen.
   Ohne Speichern zurückgehen: keine Serverdatei. Gespeicherte Datei neu öffnen.
2. Vorhandene Datei über die zusätzliche Wischaktion „Edit…“ bearbeiten. Zweimal
   speichern, neu laden und Inhalt prüfen. Normaler TXT-Viewer bleibt unverändert.
3. Einen vorhandenen Namen beim Erstellen/„Save under a new name“ angeben:
   Konflikt, kein Überschreiben, Text bleibt erhalten.
4. Datei während der Bearbeitung mit einem anderen Client ändern. Speichern muss
   abgewiesen werden; anschließend unter neuem Namen speichern.
5. LF/CRLF und BOM per Download byteweise prüfen. Ungültiges UTF-8, gemischte
   Zeilenenden und Dateien über 256 KiB dürfen nicht zum Bearbeiten geladen werden.
6. Änderungen eingeben, Header-Zurück und Hardware-Zurück prüfen: Warnung,
   „Continue editing“ behält Text. „Discard changes“ verwirft ausdrücklich.
7. Während PUT mehrfach Speichern/Zurück versuchen. Bei Verbindungsunterbrechung
   Text behalten, keine automatische Wiederholung. Anschließend Serverzustand prüfen.
8. Tastatur, lange Texte, Hoch-/Querformat auf Telefon und Tablet prüfen.
9. Upload, Einzel-/Mehrfachdownload, Export, Vorschau, DELETE, MKCOL, Icons und
   gespeicherte Verbindung als Regression prüfen.

Automatisierte Tests verändern keine echten Serverdateien; HTTP-Antworten sind simuliert.

## Automatische Prüfung am 20.10.2026

- 95 Python-Tests erfolgreich, auch im Clickable-Container mit Python 3.8.
- 62 QML-Testresultate erfolgreich (einschließlich initTestCase/cleanupTestCase).
- Vier JavaScript-Testsuiten erfolgreich.
- DownloadSmoke, BatchBridgeSmoke und EditorBridgeSmoke erfolgreich.
- `clickable desktop`: Backend erfolgreich importiert; App gestartet.
- `clickable build`: Version 1.0.18 gebaut, Click-Review `pass`.
- Paketquellen mit Arbeitsstand verglichen; Icon und AppArmor-Berechtigungen
  unverändert. Keine Tests, Diagnoseunterlagen, .pyc- oder .part-Dateien im Paket.

Der Desktop bietet keinen vollständigen Content Hub. Der Abschluss auf POCO und
Tablet steht aus; insbesondere Tastatur, Bildschirmorientierung und Server-ETags
müssen dort mit Testdateien geprüft werden.

## Korrekturen nach erstem POCO-Test (weiterhin 1.0.18)

Ursache: Beim normalen Antippen war nur `.txt` intern mit dem TextViewer verbunden.
`.md` fiel in den generischen Exportpfad (ContentHandler.Destination). Der Picker
konnte deshalb einen externen Editor auswählen. Die gesonderte Aktion „Edit…“
unterstützte bereits TXT und MD über denselben geschützten Editor.

Nun nutzen TXT und MD die bestehende interne Textvorschau. „Edit…“ bleibt die
interne Bearbeitung; „Open in another app…“ bleibt die explizite externe Übergabe.
Externe Änderungen werden nicht automatisch auf den WebDAV-Server hochgeladen.

Der ExportController kannte Collected bereits, wartete dort aber ohne Rückkehrweg.
Collected bestätigt nur die Abholung, nicht das Ende des Kopierens/Bearbeitens.
`finalize()` kann temporäre Hub-Dateien entfernen und darf diesen Zustand nicht
künstlich beenden. „Return to app“ löst jetzt die Oberflächensperre und übergibt
Transfer, ContentItems und Cache-Referenzen an einen eigenen Hintergrundbeobachter
innerhalb desselben ExportControllers. Erst Aborted/Finalized lösen die vorhandene
Freigabe genau einmal aus. Alte Ereignisse verändern keinen neuen Export.

Vor Collected ist zusätzlich „Cancel transfer and return“ verfügbar. Das Senden
von Aborted allein löst keine Freigabe aus: erst der bestätigte terminale Zustand.
Auch fehlgeschlagener oder verzögerter Abbruch lässt die App benutzbar und behält
Dateien. Charged wird gemäß der tatsächlichen API erst aus InProgress gesetzt.

Technische Grenze: Ohne Rückmeldung des Empfängers gibt es keine zuverlässige
Bestätigung, dass er mit den Dateien fertig ist. Kein automatischer Timeout mit
Löschen, kein erzwungenes finalize() nach Collected. Die Referenzen bleiben dann
für die laufende App-Sitzung erhalten; es gibt keine neue Bereinigungsregel.
Das ist die sichere Alternative zum erzwungenen Abschluss. Receiver und echter
Content Hub müssen abschließend erneut auf dem Gerät getestet werden.

Icons: Direkt per SSH auf dem POCO geprüft: Suru `add.svg` ist vorhanden,
`document-save.svg` ist ein Symlink auf `save.svg` (Download-Pfeil). Die explizite
Diskette kommt deshalb als kleines eigenes SVG `assets/editor-save.svg` mit;
„Save under a new name…“ verwendet das vorhandene Plus `add`. Die Header-Icons
verwenden Theme-Farben, getrennte Action.text-/description-Beschriftungen,
explizite Accessible-Namen sowie Hinweise bei Hover und langem Drücken.
Ein langes Drücken zeigt nur die Beschriftung und speichert nicht.

Quellen:
- https://ubports.gitlab.io/docs/api-docs/lomiri-content-qml-api/qml-lomiri-content-contenttransfer.html
- https://gitlab.com/ubports/development/core/lomiri-content-hub/-/blob/main/import/Lomiri/Content/contenttransfer.cpp
- https://ubports.gitlab.io/docs/api-docs/lomiriuserinterfacetoolkit/qml-lomiri-components-action.html

Zusätzliche Gerätetests:

1. TXT und MD antippen: interne Textvorschau. Beide über „Edit…“ bearbeiten.
2. MD ausdrücklich extern öffnen und den Empfänger ohne Änderungen verlassen.
   „Return to app“ muss ohne App-Neustart zurückführen. Danach erneut exportieren.
3. Einzel- und Mehrfachexport inklusive Zielauswahl-Abbruch, verzögertem Abschluss
   und Dateimanager-Import prüfen. Keine vorzeitige Entfernung der übergebenen Dateien.
4. Diskette/Plus bei hellem und dunklem Theme prüfen. Langes Drücken zeigt den
   richtigen Hinweis. Diskette speichert bedingt; Plus öffnet nur die Namenseingabe.
5. ETag-Konflikt und Verlassen mit ungespeicherten Änderungen erneut prüfen.

Prüfergebnis des korrigierten Stands:
95 Python-Tests, 74 QML-Testresultate (einschließlich Initialisierung/Abschluss),
vier JavaScript-Suiten und alle drei Smoke-Tests erfolgreich. Zusätzlich echtes
langes Drücken mit Maus-Press/Release geprüft: Beschriftung, kein PUT.
Desktop-Start erfolgreich, Click-Build und Paket-Review `pass`. Paketinhalt samt
neuer Diskette, Original-Logo und unveränderten AppArmor-Gruppen kontrolliert.

## Letzter Feinschliff: Editor-Fehlermeldungen (21.10.2026)

Ausschließlich die Editor-Diagnose und angezeigten Meldungen wurden verfeinert.
Feste Fehlercodes unterscheiden Versionskonflikt, Namenskonflikt, nicht sicher
prüfbare Ressource/Pfad, 256-KiB-Limit, ungültiges UTF-8, nicht unterstütztes Format,
Netzwerkfehler und unklaren Speicherstatus. Ausnahme-Texte werden nicht angezeigt.
Auch beschädigte Prozentkodierung im Pfad wird nicht als Textkodierungsfehler
fehlinterpretiert. HTTP 412 gilt nur bei einer bedingten Anfrage als bestätigter
Namens-/Versionskonflikt; bei einer unerwarteten PROPFIND-Antwort bleibt die
Meldung eine fehlgeschlagene Sicherheitsprüfung.

Wird beim begrenzten Lesen tatsächlich mehr als 256 KiB empfangen, erscheint die
Größenmeldung auch bei einer größeren Content-Length. Der unveränderte begrenzte
Read wird deshalb nicht irreführend als fehlerhafte Serverantwort erklärt.

Diagnosemerker für GET/PUT dienen ausschließlich der Meldungszuordnung. Alle
Pfad-, Typ-, Identitäts-, ETag-, Größen- und Formatprüfungen, PUT-Vorbedingungen,
Sperren nach unklarem PUT und Regeln zum Erhalt des Editor-Texts bleiben erhalten.
Neue QML-Prüfungen kontrollieren Meldung, PlainText-Darstellung, erhaltenen Text,
weiter bestehende Änderungswarnung sowie die Meldung im Speichern-unter-Dialog.

Abschlussprüfung am 21.10.2026: 103 Python-Tests (auch unter Python 3.8 im
Clickable-Container), 75 QML-Testresultate einschließlich Initialisierung/Abschluss,
vier JavaScript-Suiten und drei Smoke-Tests erfolgreich. Desktop-Start erfolgreich;
Click-Build und Paket-Review `pass`. Paketinhalt, Version 1.0.18, aktuelle
Editorquellen und unveränderte Berechtigungsgruppen kontrolliert.

## Gerätefreigabe für den Commit

Der Benutzer hat die erfolgreichen Gerätetests auf POCO X3 NFC und
Ubuntu-Touch-Tablet bestätigt. Auf dem POCO wurden zusätzlich ETag-Konflikte für
TXT und Markdown einschließlich „Unter neuem Namen speichern“ erfolgreich geprüft.
Die Commit-Freigabe umfasst den Editor, Content-Hub-Rückkehrweg, Icons,
verständliche Fehlermeldungen sowie die zugehörigen Tests und Dokumentation.
