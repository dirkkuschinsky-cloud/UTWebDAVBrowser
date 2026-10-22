import QtQuick 2.7
import Lomiri.Components 1.3
import Lomiri.Content 1.3

Item {
    id: exportController
    property var backend
    property bool exportBusy: false
    property bool downloadBusy: false
    property bool destinationPickerVisible: false
    property real downloadedBytes: 0
    property real downloadTotal: -1
    property string downloadName: ""
    property string downloadMessage: ""
    property var pendingExport: null
    property var exportTransfer: null
    property var exportItem: null
    property var pendingExports: []
    property var exportItems: []
    property int retainedExportCount: 0
    property bool multiExport: false
    property bool exportCharged: false
    property bool exportFinishing: false
    property bool exportCollected: false
    property bool exportToFileManager: true
    property int exportContentType: ContentType.All
    signal progress(var received, var total)

    Component.onCompleted: backend.setHandler("downloadProgress", function(received, total) {
        if (downloadBusy) {
            downloadedBytes = received
            downloadTotal = total === null ? -1 : total
        }
        progress(received, total)
    })

    function save(info, toFileManager) {
        if (exportBusy) return
        exportBusy = true
        pendingExports = []
        exportItems = []
        multiExport = false
        downloadBusy = true
        exportCollected = false
        exportFinishing = false
        exportToFileManager = toFileManager
        downloadName = info.fileName
        downloadMessage = ""
        downloadedBytes = 0
        downloadTotal = -1
        backend.call("main.acquire_download", [info], function(result) {
            downloadBusy = false
            if (!result || !result.success) {
                finishExport(result && result.message ? result.message : i18n.tr("Download failed."))
                return
            }
            pendingExport = result
            pendingExports = [result]
            exportContentType = chooseExportCategory()
            destinationPickerVisible = true
            downloadMessage = i18n.tr("Choose an app for the file.")
        })
    }

    function saveMany(infos) {
        if (exportBusy || !infos || !infos.length) return
        exportBusy = true
        multiExport = true
        pendingExports = []
        exportItems = []
        pendingExport = null
        downloadBusy = true
        exportCollected = false
        exportFinishing = false
        exportToFileManager = true
        downloadName = i18n.tr("%1 downloaded files").arg(infos.length)
        downloadMessage = ""
        downloadedBytes = 0
        downloadTotal = -1
        backend.call("main.acquire_batch_exports", [infos], function(result) {
            downloadBusy = false
            if (!result || !result.success) {
                finishExport(result && result.message ? result.message : i18n.tr("The export could not be prepared."))
                return
            }
            pendingExports = result.files
            pendingExport = pendingExports[0]
            exportContentType = ContentType.All
            destinationPickerVisible = true
            downloadMessage = i18n.tr("Choose an app for the downloaded files.")
        })
    }

    function chooseExportCategory() {
        if (exportToFileManager) return ContentType.All
        var name = downloadName.toLowerCase()
        if (/\.(png|jpe?g|gif|webp)$/.test(name)) return ContentType.Pictures
        if (/\.(mp3|ogg|wav|flac)$/.test(name)) return ContentType.Music
        if (/\.(mp4|mkv|webm)$/.test(name)) return ContentType.Videos
        if (/\.(epub)$/.test(name)) return ContentType.EBooks
        return ContentType.Documents
    }

    function updateExportState() {
        if (!exportTransfer || exportFinishing) return
        var state = exportTransfer.state
        if (state === ContentTransfer.InProgress && !exportCharged) {
            exportCharged = true
            exportTransfer.items = exportItems
            exportTransfer.state = ContentTransfer.Charged
            downloadMessage = i18n.tr("Handing the file to the selected app…")
        } else if (state === ContentTransfer.Collected) {
            exportCollected = true
            // The receiver may still copy the files after marking them Collected.
            // Only the receiver can finalize a successfully collected transfer.
            downloadMessage = i18n.tr("The selected app received the file. Waiting for it to finish…")
        } else if (state === ContentTransfer.Aborted) {
            finishExport(multiExport ? i18n.tr("The selected app ended the transfer. Check its import results. Original downloads are still available.")
                                     : i18n.tr("Export was cancelled or failed."))
        } else if (state === ContentTransfer.Finalized) {
            finishExport(exportCollected ? i18n.tr("The file was handed to the selected app.")
                                        : i18n.tr("Export ended without confirmation."))
        }
    }

    function startExport(peer) {
        if (!pendingExport || exportTransfer) return
        destinationPickerVisible = false
        exportCharged = false
        exportFinishing = false
        try {
            var items = []
            for (var i = 0; i < pendingExports.length; i++) {
                var item = exportItemComponent.createObject(exportController, {
                    "url": pendingExports[i].localUrl, "name": pendingExports[i].fileName
                })
                if (!item) throw new Error("ContentItem creation failed")
                items.push(item)
                exportItems = items.slice()
            }
            exportItem = items[0]
            peer.selectionType = items.length > 1 ? ContentTransfer.Multiple : ContentTransfer.Single
            exportTransfer = peer.request()
            if (!exportTransfer) throw new Error("Content Hub transfer creation failed")
            updateExportState()
        } catch (error) {
            finishExport(i18n.tr("The export could not be started."))
        }
    }

    function returnToApp(allowUncharged) {
        if (!exportBusy || exportFinishing || !exportTransfer || downloadBusy
                || (!allowUncharged && !exportCharged && !exportCollected)) return false
        // Move ownership, never release it. A Collected receiver may still be
        // reading. Its late signals must not touch a subsequent export.
        var retained = retainedExportComponent.createObject(exportController, {
            transfer: exportTransfer, files: pendingExports.slice(), items: exportItems.slice()
        })
        if (!retained) return false
        retainedExportCount++
        exportTransfer = null
        pendingExport = null
        pendingExports = []
        exportItem = null
        exportItems = []
        exportBusy = false
        exportCharged = false
        exportCollected = false
        destinationPickerVisible = false
        downloadMessage = ""
        retained.armed = true
        retained.check()
        return true
    }

    function cancelActiveExport() {
        if (!exportTransfer || exportCollected || exportFinishing) return
        var transfer = exportTransfer
        if (!returnToApp(true)) return
        // Abort is a request, not proof that the receiver has stopped.
        // Ownership stays with the retained observer until a terminal state.
        try { transfer.state = ContentTransfer.Aborted } catch (error) {}
    }

    Component {
        id: retainedExportComponent
        Item {
            id: retained
            property var transfer: null
            property var files: []
            property var items: []
            property bool armed: false
            property bool completed: false
            function check() {
                if (!armed || completed || !transfer) return
                if (transfer.state !== ContentTransfer.Aborted && transfer.state !== ContentTransfer.Finalized) return
                completed = true
                var finished = transfer
                transfer = null
                if (finished.state === ContentTransfer.Aborted) {
                    try { finished.finalize() } catch (error) {}
                }
                for (var i = 0; i < items.length; i++) items[i].destroy()
                items = []
                releaseNext(0)
            }
            function releaseNext(index) {
                if (index >= files.length) {
                    files = []
                    exportController.retainedExportCount--
                    retained.destroy()
                    return
                }
                exportController.backend.call("main.release_download", [files[index].cacheRef], function(result) {
                    retained.releaseNext(index + 1)
                })
            }
            Connections {
                target: retained.transfer ? retained.transfer : null
                onStateChanged: retained.check()
            }
        }
    }

    function finishExport(message) {
        if (exportFinishing || !exportBusy) return
        exportFinishing = true
        destinationPickerVisible = false
        downloadMessage = message
        var transfer = exportTransfer
        if (transfer && transfer.state !== ContentTransfer.Finalized && transfer.state !== ContentTransfer.Aborted) {
            try {
                if (!exportCollected) transfer.state = ContentTransfer.Aborted
            } catch (error) {}
            if (transfer.state !== ContentTransfer.Aborted && transfer.state !== ContentTransfer.Finalized) {
                // finalize() may clean up hub files. Never use it to force an
                // active receiver to finish, including an unconfirmed abort.
                exportFinishing = false
                downloadMessage += "\n" + i18n.tr("The transfer is still active. You can return to the app; its files will be retained.")
                return
            }
        }
        exportTransfer = null
        if (transfer && transfer.state === ContentTransfer.Aborted) {
            try { transfer.finalize() } catch (error) {
                downloadMessage += "\n" + i18n.tr("The transfer could not be finalized.")
            }
        }
        var items = exportItems
        exportItem = null
        exportItems = []
        for (var i = 0; i < items.length; i++) items[i].destroy()
        var files = pendingExports
        pendingExport = null
        pendingExports = []
        function releaseNext(index) {
            if (index >= files.length) {
                exportBusy = false
                exportFinishing = false
                return
            }
            backend.call("main.release_download", [files[index].cacheRef], function(result) {
                if (!result.success) downloadMessage += "\n" + result.message
                releaseNext(index + 1)
            })
        }
        releaseNext(0)
    }

    Component {
        id: exportItemComponent
        ContentItem {}
    }

    Connections {
        target: exportTransfer ? exportTransfer : null
        onStateChanged: updateExportState()
    }

    Rectangle {
        anchors.fill: parent
        color: theme.palette.normal.background
        visible: destinationPickerVisible
        z: 110
        ContentPeerPicker {
            anchors.fill: parent
            handler: ContentHandler.Destination
            contentType: exportContentType
            onPeerSelected: startExport(peer)
            onCancelPressed: finishExport(i18n.tr("Export was cancelled."))
        }
    }

    // Root overlay: errors and the picker remain visible above every preview.
    Rectangle {
        anchors.fill: parent
        visible: exportBusy || downloadMessage !== ""
        color: theme.palette.normal.background
        z: 100
        MouseArea { anchors.fill: parent }
        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: units.gu(2)
            spacing: units.gu(2)
            Label {
                width: parent.width
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                text: downloadBusy ? i18n.tr("Preparing: %1").arg(downloadName) : downloadMessage
            }
            ProgressBar {
                width: parent.width
                visible: downloadBusy
                indeterminate: downloadTotal < 0
                minimumValue: 0
                maximumValue: 1
                value: downloadTotal > 0 ? Math.min(downloadedBytes / downloadTotal, 0.99) : 0
            }
            Label {
                visible: downloadBusy
                text: downloadTotal > 0 ? Math.min(99, Math.floor(downloadedBytes * 100 / downloadTotal)) + " %"
                                        : Math.floor(downloadedBytes / 1024) + " KiB"
            }
            Label {
                width: parent.width
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                visible: !!exportTransfer && !downloadBusy
                text: i18n.tr("You can return to the app without ending the external app. Files remain available until the transfer ends. External changes are not saved back to WebDAV.")
            }
            Button {
                objectName: "returnFromExport"
                text: i18n.tr("Return to app")
                visible: !!exportTransfer && !downloadBusy && (exportCharged || exportCollected)
                enabled: !exportFinishing
                onClicked: returnToApp()
            }
            Button {
                objectName: "cancelActiveExport"
                text: i18n.tr("Cancel transfer and return")
                visible: !!exportTransfer && !downloadBusy && !exportCollected
                enabled: !exportFinishing
                onClicked: cancelActiveExport()
            }
            Button {
                text: i18n.tr("Dismiss")
                visible: !exportBusy
                onClicked: downloadMessage = ""
            }
        }
    }
}
