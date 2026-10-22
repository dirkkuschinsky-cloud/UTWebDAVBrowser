# v1.0.16: Löschen sicher prüfen

Automatisierte Tests verwenden ausschließlich simulierte HTTP-Antworten und QML-Backends.
Es werden keine echten Cloud-Ressourcen gelöscht.

## Gerätepraxistest (POCO und Ubuntu-Touch-Tablet)

Nur eigens angelegte, entbehrliche Testdateien und Testordner verwenden.

1. Testdatei mit Umlaut und Leerzeichen anlegen. Wischaktion „Löschen…“ öffnen:
   Dateiname prüfen, zunächst abbrechen. Datei muss erhalten bleiben.
2. Dieselbe Datei erneut auswählen und ausdrücklich per Löschbutton bestätigen.
   Liste muss im bisherigen Verzeichnis aktualisiert werden.
3. Leeren Testordner und Testordner mit Unterordner/Testdatei löschen.
   Vor beiden Vorgängen muss die Warnung vor dem dauerhaften Löschen aller Inhalte erscheinen.
4. Testnamen mit `%`, dem wörtlichen `%2F`, `#` und `&` prüfen.
   Es darf ausschließlich die ausgewählte Ressource betroffen sein.
5. Während der Prüfung/Anfrage mehrfach antippen und Navigation versuchen:
   keine zweite Löschanfrage, kein Verzeichniswechsel.
6. Bei vorhandener Tastatur: Return und Enter auf dem Löschbutton dürfen nichts löschen;
   Escape vor dem Absenden muss abbrechen.
7. Soweit mit Testdaten möglich: Schreibschutz oder gesperrte Ressource prüfen.
   Keine falsche Erfolgsmeldung; nach Fehler ist eine neue Auswahl erforderlich.
8. Upload, Download, Vorschau, Content-Hub-Export, MKCOL und gespeicherte Verbindung prüfen.

## Technische Grenzen und Bedingungen

- Pfade werden über die zentrale URL-Auflösung verarbeitet und zusätzlich anhand
  einzeln verglichener Pfadsegmente begrenzt. Stamm, aktuelles Verzeichnis,
  fremde Ziele und kodierte Pfadtrenner sind für DELETE gesperrt.
- Vor dem Dialog und unmittelbar vor DELETE wird Depth-0-PROPFIND ausgeführt.
  Ressourcentyp sowie verfügbare ETag-, resource-id-, Erstellungs- und Änderungsdaten
  werden verglichen. Ohne ETag, resource-id oder Erstellungsdatum wird abgebrochen.
- Starke Datei-ETags werden als If-Match verwendet. HTTP 412 führt zum Abbruch,
  niemals zu einem erneuten Versuch ohne Bedingung. Schwache ETags sind dafür ungeeignet.
- Ordner-ETags werden verglichen, aber nicht als If-Match gesendet: Sie garantieren
  keinen unveränderten Unterbaum; DELETE-Bedingungen können alle Mitglieder betreffen.
- Ohne serverseitige Sperren gibt es für Ordner und Dateien ohne starke ETags ein
  verbleibendes Zeitfenster zwischen zweiter Prüfung und DELETE. Identische oder
  fehlende Servermetadaten können eine unbemerkte Ersetzung nicht ausschließen.
  Es wird keine vollständige Identitäts- oder Unterbaumgarantie behauptet.
- 207 wird nie pauschal als vollständiger Erfolg angezeigt. Fehlerstatus werden
  ausgewertet, unklare/ungültige Antworten führen ebenfalls zur Warnung und Aktualisierung.
- Bei Verbindungsabbruch kann die Löschung bereits erfolgt sein. Keine automatische
  Wiederholung; Ergebnis durch Aktualisieren prüfen und bei Bedarf neu auswählen.

Quellen:
- https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1
- https://www.rfc-editor.org/rfc/rfc4918.html#section-9.6.1
- https://www.rfc-editor.org/rfc/rfc4918.html#section-8.8
