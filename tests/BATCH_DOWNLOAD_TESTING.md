# v1.0.17: Mehrfachauswahl und Downloadauftrag

## Implementierung und Grenzen

- BrowserPage zeigt Checkboxen nur für vom Backend geprüfte Dateien des aktuellen
  Verzeichnisses. DAV:resourcetype muss bekannt sein; Ordner und unsichere Pfade
  werden ausgeschlossen. Vor Auftragsbeginn wird die Liste erneut geprüft.
- Pfade werden über die zentrale URL-Auflösung und die segmentweise Grenzprüfung
  aus DELETE validiert. Identische Ressourcen (resource-id oder geprüfte Segmente)
  werden dedupliziert. Kodierte Pfadtrenner werden nicht zu neuen Pfaden dekodiert.
- Genau ein Python-Worker arbeitet einen Auftrag sequenziell ab. Der bestehende
  64-KiB-Streaming-Downloader bleibt die einzige Netzwerkimplementierung.
- Die kurzen PyOtherSide-Aufrufe für Status und Abbruch blockieren nicht hinter
  dem GET. Statusantworten enthalten Auftrags-ID, Datei-IDs und eine Sequenznummer.
  Alte Antworten ändern keinen späteren Auftrag.
- Abbruch erscheint sofort in QML. Ein blockierender DNS-/Netzwerkaufruf kann bis
  zum bisherigen 30-Sekunden-Timeout warten. Zwischen Blöcken und direkt vor
  os.replace() wird geprüft. Abbruch und Veröffentlichung sind geordnet:
  bereits veröffentlichte Dateien bleiben erfolgreich, weitere GETs starten nicht.
- Gesamtfortschritt ist nach Dateien gewichtet, kein behaupteter Gesamt-Bytewert.
  Fehlgeschlagene Dateien zählen als bearbeitet, nicht als heruntergeladen.
  Bei unbekannter Größe erscheinen für die aktuelle Datei KiB statt Prozenten.
- Der Auftrag ist auf 1000 Dateien begrenzt. Erfolgreiche Dateien bleiben im Cache
  bis zur bewussten Verwerfung der Ergebnisse; kein Wiederaufnehmen nach App-Neustart.
- Jede Batch-Datei erhält ein privates Verzeichnis mit Prozess-Lease (flock).
  Beim nächsten Start werden markierte, nicht mehr verwendete Batch-Verzeichnisse
  bereinigt. Legacy-Vorschau-/PDF-Caches bleiben unangetastet.
- Vorab wird für bekannte Größen Platz geprüft, vor jeder Datei erneut anhand
  ihrer tatsächlichen Content-Length. Unbekannte Größen können dennoch später
  zu ENOSPC führen; Schreibfehler werden aufgeräumt und als Fehler gemeldet.
- Identische Exportnamen sowie konservativ auch Groß-/Kleinschreibungs- und
  Unicode-Normalisierungs-Konflikte werden vor Beginn abgelehnt. Keine automatische
  Umbenennung und keine stille Überschreibung. Ungültige Namen werden nicht als
  lokale Zielpfade verwendet.

## Content Hub: tatsächliche Unterstützung

Die ContentTransfer-API unterstützt mehrere ContentItems. Der offizielle
Lomiri-Dateimanager verarbeitet in importFiles() jedes Element aus
activeTransfer.items und zeigt erfolgreiche/fehlgeschlagene Imports an.
Eine alternative Einzelübergabe wurde deshalb nicht implementiert.

Der gemeinsame ExportController wird für Einzel- und Mehrfachübergaben verwendet.
Für den Batch-Export werden vorhandene Cache-Dateien blockweise lokal kopiert,
niemals erneut heruntergeladen. Die Kopien besitzen eigene Cache-Referenzen:
Ein Verschieben oder Ändern durch einen Empfänger beschädigt die Originale nicht.
Dafür wird zeitweise zusätzlicher Speicherplatz in Größe der Exportdateien benötigt.
Fehlt dieser Platz, bleiben die Originaldownloads erhalten.

Bei Collected werden keine Exportdateien freigegeben. Erst beim terminalen
Transferzustand werden die Exportkopien freigegeben. Der Dateimanager setzt
nach Schließen seines Ergebnisdialogs Aborted, auch nach erfolgreichem Import.
Daraus lässt sich kein zuverlässiges Ergebnis pro Datei ableiten. Die App fordert
zur Prüfung des Importergebnisses auf und bietet erneutes Speichern oder bewusstes
Verwerfen der Originaldownloads an. Ein vorhandener Zielname wird vom Dateimanager
nicht überschrieben. Die installierte Geräteversion muss im Praxistest bestätigt werden.

Quellen (geprüft am 19.10.2026):
- https://ubports.gitlab.io/docs/api-docs/lomiri-content-qml-api/qml-lomiri-content-contenttransfer.html
- https://gitlab.com/ubports/development/apps/lomiri-filemanager-app/-/blob/main/src/app/qml/filemanager.qml
- https://gitlab.com/ubports/development/core/lomiri-content-hub/-/blob/main/import/Lomiri/Content/contentitem.cpp

## POCO-Praxistest

Nur eigens angelegte Testdateien verwenden.

1. In einem Testordner „Dateien auswählen“ öffnen. Einzelne Checkboxen, „Alle
   auswählen“, „Auswahl aufheben“ und „Auswahl verlassen“ prüfen. Ordner dürfen
   weder ausgewählt noch versehentlich geöffnet werden. Außerhalb des Modus
   müssen Navigation, Wischaktionen und Vorschau wie bisher funktionieren.
2. Drei Dateien auswählen, darunter eine mit Umlaut, Leerzeichen und wörtlichem
   Prozentzeichen. Download starten. Dateiposition, Prozent/KiB und nach Dateien
   gewichteten Auftragsfortschritt prüfen. Am Ende muss die Zusammenfassung stimmen.
3. Die drei Dateien gemeinsam über „Speichern“ an die Dateiverwaltung übergeben.
   Importergebnis dort prüfen, Dateien öffnen oder SHA256 mit den Quellen vergleichen.
4. Erneut speichern und die Zielauswahl abbrechen. Nochmals speichern: kein neuer
   WebDAV-Download, Originaldateien bleiben verfügbar. Bereits vorhandene Zieldateien
   dürfen nicht überschrieben werden; Konflikte erscheinen im Dateimanager.
5. Einen Auftrag mit einer großen Testdatei zuerst und zwei weiteren Dateien starten.
   Während des Downloads abbrechen. „Abbruch läuft“ muss sofort erscheinen; nach
   Abschluss der aktuellen Netzwerkoperation dürfen keine weiteren GETs starten.
   Keine unvollständige Datei darf zum Speichern angeboten werden.
6. Eine kleine Datei vor der großen Testdatei abschließen lassen, dann abbrechen.
   Die kleine Datei muss weiterhin speicherbar sein. Fehlgeschlagene und abgebrochene
   Dateien müssen getrennt von erfolgreichen Downloads gezählt werden.
7. Navigation, Upload, DELETE, MKCOL und weiteren Download während des Auftrags
   versuchen. Danach die Ergebnisse bewusst verwerfen und einen neuen Auftrag starten.
8. Einzel-Download, TXT-/Bild-/PDF-Vorschau, Viewer-Speichern, Upload, DELETE, MKCOL,
   Dateiicons und gespeicherte Verbindungsdaten als Regression prüfen.

Automatisierte Tests verwenden ausschließlich simulierte HTTP-Antworten.
BatchBridgeSmoke.qml prüft zusätzlich den laufenden Abbruch über das echte
PyOtherSide-Plugin mit simuliertem GET und regelmäßig weiterlaufender QML-Timeranzeige.
