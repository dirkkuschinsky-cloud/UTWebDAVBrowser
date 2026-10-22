import QtQuick 2.7
import "EditorRules.js" as EditorRules
import Lomiri.Components 1.3
import Lomiri.Content 1.3
import Lomiri.Components.Popups 1.3
import "FileIcons.js" as FileIcons
import "DownloadSelection.js" as Selection

Page {
    id: browserPage

    property var backend
    property var pathHistory: []
    property string currentPath: "/"
    property string displayPath: "/"

    property bool editorBusy: false
    property var textNameDialog: null
    signal editText(var session)
    signal openTextFile(string fileName, string fileContent, var downloadInfo)
    signal openImageFile(string fileName, string imageSource, var downloadInfo)
    signal openPdfFile(string fileName, string filePath, var downloadInfo)

    property var batchController: null
    property bool selectionMode: false
    property var selectedKeys: []
    property int listGeneration: 0

    function modelEntries() {
        var entries = []
        for (var i = 0; i < fileModel.count; i++) entries.push(fileModel.get(i))
        return entries
    }
    function selectAllFiles() { selectedKeys = Selection.allKeys(modelEntries()) }
    function startSelectedDownloads() {
        if (transferBusy || !batchController) return
        var paths = Selection.selectedPaths(modelEntries(), selectedKeys)
        if (!paths.length) return
        selectionMode = false
        selectedKeys = []
        batchController.begin(currentPath, paths)
    }

    property var activeTransfer


    property bool uploadBusy: false
    property bool selectingFiles: false
    property var uploadQueue: []
    property int uploadIndex: 0
    property int uploadSucceeded: 0
    property string uploadDestination: "/"
    property string uploadName: ""
    property real uploadFraction: 0
    property bool awaitingConfirmation: false
    property string uploadMessage: ""
    property string uploadErrors: ""
    property bool transferHandled: false

    property bool downloadBusy: false
    property var exportController
    property real downloadedBytes: 0
    property real downloadTotal: -1
    property string downloadName: ""
    property string downloadMessage: ""
    property bool exportToFileManager: true
    property bool folderBusy: false
    property var folderDialog: null
    property bool deleteBusy: false
    property var deleteDialog: null
    property bool transferBusy: editorBusy || !!textNameDialog || !!(batchController && batchController.present) || deleteBusy || !!deleteDialog || folderBusy || uploadBusy || selectingFiles || downloadBusy
                                || (exportController && exportController.exportBusy)

    function requestDelete(path) {
        if (transferBusy || folderDialog || !path) return
        var parentPath = currentPath
        deleteBusy = true
        downloadMessage = i18n.tr("Checking resource before deletion…")
        backend.call("main.prepare_delete", [parentPath, path], function(result) {
            deleteBusy = false
            if (!result || !result.success) {
                downloadMessage = result && result.message ? result.message : i18n.tr("The resource could not be checked.")
                return
            }
            downloadMessage = ""
            deleteDialog = PopupUtils.open(deleteDialogComponent, browserPage,
                {selection: result, parentPath: parentPath})
        })
    }

    Component {
        id: deleteDialogComponent
        Dialog {
            id: confirmation
            objectName: "deleteConfirmationDialog"
            title: i18n.tr("Confirm deletion")
            property var selection
            property string parentPath
            property bool submitted: false
            function cancelSelection() {
                if (browserPage.deleteBusy) return
                backend.call("main.cancel_delete", [selection.token], function(result) {})
                browserPage.deleteDialog = null
                PopupUtils.close(confirmation)
            }
            onVisibleChanged: {
                if (!visible && browserPage.deleteDialog === confirmation) {
                    if (browserPage.deleteBusy) confirmation.show()
                    else cancelSelection()
                }
            }
            Component.onCompleted: cancelDeleteButton.forceActiveFocus()
            Component.onDestruction: {
                if (!submitted && selection)
                    backend.call("main.cancel_delete", [selection.token], function(result) {})
            }
            Label {
                objectName: "deleteQuestion"
                text: selection ? (selection.isDirectory ? i18n.tr("Really delete folder %1?")
                                                         : i18n.tr("Really delete file %1?")).arg(selection.name) : ""
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            Label {
                objectName: "deleteFolderWarning"
                visible: selection ? selection.isDirectory : false
                text: i18n.tr("Warning: The folder and all contained files and subfolders may be permanently deleted.")
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            ActivityIndicator {
                running: browserPage.deleteBusy
                visible: running
            }
            Button {
                id: cancelDeleteButton
                objectName: "cancelDeleteButton"
                text: i18n.tr("Cancel")
                enabled: !browserPage.deleteBusy
                onClicked: confirmation.cancelSelection()
            }
            Button {
                objectName: "confirmDeleteButton"
                text: i18n.tr("Delete permanently")
                color: theme.palette.normal.negative
                enabled: !browserPage.deleteBusy && !confirmation.submitted
                // A keyboard Return/Enter must never confirm a destructive action.
                Keys.priority: Keys.BeforeItem
                Keys.onPressed: {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        event.accepted = true
                }
                Keys.onReleased: {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        event.accepted = true
                }
                onClicked: {
                    if (browserPage.deleteBusy || confirmation.submitted) return
                    confirmation.submitted = true
                    browserPage.deleteBusy = true
                    backend.call("main.delete_resource", [confirmation.selection.token], function(result) {
                        browserPage.deleteBusy = false
                        var parent = confirmation.parentPath
                        browserPage.deleteDialog = null
                        PopupUtils.close(confirmation)
                        if (result && result.success) {
                            downloadMessage = i18n.tr("Resource deleted.")
                            browserPage.loadDirectory(parent)
                        } else {
                            downloadMessage = result && result.message ? result.message : i18n.tr("Deletion was not confirmed. Refresh and select again.")
                            if (result && result.refresh) browserPage.loadDirectory(parent)
                        }
                    })
                }
            }
        }
    }

    function openEditor(path, name) {
        if (transferBusy || selectionMode) return
        editorBusy = true
        backend.call("main.open_editor", [currentPath, path || "", name || ""], function(result) {
            editorBusy = false
            if (result && result.success) editText(result)
            else downloadMessage = result && result.message ? result.message : i18n.tr("The editor could not be opened.")
        })
    }
    function newTextFile() {
        if (!transferBusy && !selectionMode) textNameDialog = PopupUtils.open(textNameComponent, browserPage)
    }
    Component {
        id: textNameComponent
        Dialog {
            id: names
            title: i18n.tr("New text file")
            onVisibleChanged: if (!visible) browserPage.textNameDialog = null
            TextField { id: textName; objectName: "newTextName"; placeholderText: i18n.tr("File name (.txt or .md)") }
            Button {
                text: i18n.tr("Create")
                enabled: EditorRules.validName(textName.text)
                onClicked: {
                    var name = textName.text
                    browserPage.textNameDialog = null
                    PopupUtils.close(names)
                    browserPage.openEditor("", name)
                }
            }
            Button {
                text: i18n.tr("Cancel")
                onClicked: { browserPage.textNameDialog = null; PopupUtils.close(names) }
            }
        }
    }

    function validFolderName(name) {
        return name.trim().length > 0 && name !== "." && name !== ".."
            && !/[\/\\\x00-\x1f\x7f]/.test(name)
    }

    function openFolderDialog() {
        if (transferBusy || folderDialog) return
        folderDialog = PopupUtils.open(folderDialogComponent, browserPage)
    }

    Component {
        id: folderDialogComponent
        Dialog {
            id: dialog
            objectName: "newFolderDialog"
            title: i18n.tr("New folder")
            property string destination: browserPage.currentPath
            property string errorMessage: ""
            // Escape can hide a Lomiri Dialog independently of its buttons.
            // Keep the pending request visible; otherwise release the dialog slot.
            onVisibleChanged: {
                if (!visible && browserPage.folderDialog === dialog) {
                    if (browserPage.folderBusy) dialog.show()
                    else browserPage.folderDialog = null
                }
            }
            function createFolder() {
                if (browserPage.transferBusy || !browserPage.validFolderName(folderName.text)) return
                browserPage.folderBusy = true
                errorMessage = ""
                backend.call("main.create_directory", [destination, folderName.text], function(result) {
                    browserPage.folderBusy = false
                    if (result && result.success) {
                        var path = dialog.destination
                        browserPage.folderDialog = null
                        PopupUtils.close(dialog)
                        browserPage.loadDirectory(path)
                    } else {
                        dialog.errorMessage = result && result.message ? result.message : i18n.tr("The folder could not be created.")
                    }
                })
            }
            TextField {
                id: folderName
                objectName: "newFolderName"
                placeholderText: i18n.tr("Folder name")
                enabled: !browserPage.folderBusy
                inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                onAccepted: dialog.createFolder()
            }
            Label {
                objectName: "newFolderError"
                text: dialog.errorMessage
                visible: text !== ""
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
            }
            ActivityIndicator {
                running: browserPage.folderBusy
                visible: running
            }
            Button {
                objectName: "createFolderButton"
                text: i18n.tr("Create")
                color: theme.palette.normal.positive
                enabled: !browserPage.transferBusy && !browserPage.selectionMode && browserPage.validFolderName(folderName.text)
                onClicked: dialog.createFolder()
            }
            Button {
                objectName: "cancelFolderButton"
                text: i18n.tr("Cancel")
                enabled: !browserPage.folderBusy
                onClicked: {
                    browserPage.folderDialog = null
                    PopupUtils.close(dialog)
                }
            }
        }
    }

    Component.onCompleted: {
        backend.setHandler("uploadProgress", function(sent, total) {
            if (!uploadBusy) return
            uploadFraction = total > 0 ? sent / total : 0
            awaitingConfirmation = sent === total
        })
    }
    Connections {
        target: exportController ? exportController : null
        onProgress: {
            if (!downloadBusy) return
            downloadedBytes = received
            downloadTotal = total === null ? -1 : total
        }
    }

    function downloadFile(remotePath, fileName, purpose) {
        if (transferBusy) return
        if (purpose === "export") {
            exportController.save({remotePath: remotePath, fileName: fileName}, exportToFileManager)
            return
        }
        downloadBusy = true
        downloadedBytes = 0
        downloadTotal = -1
        downloadName = fileName
        downloadMessage = ""
        var method = purpose === "text" ? "main.read_text_file" : "main.download_file"
        backend.call(method, purpose === "text" ? [remotePath, true] : [remotePath], function(result) {
            downloadBusy = false
            if (!result || !result.success) {
                downloadMessage = result && result.message ? result.message : i18n.tr("Download failed.")
                if (result && result.status) downloadMessage += " (HTTP " + result.status + ")"
                return
            }
            var info = {localFile: result.localFile, localUrl: result.localUrl,
                fileName: result.fileName, remotePath: remotePath, cacheRef: result.cacheRef}
            if (purpose === "image") {
                openImageFile(fileName, result.localUrl, info)
            } else if (purpose === "pdf") {
                backend.call("main.pin_download", [info.cacheRef], function(pinResult) {})
                openPdfFile(fileName, result.localFile, info)
            } else {
                openTextFile(fileName, result.text, info)
            }
        })
    }

    function uploadNext() {
        if (uploadIndex >= uploadQueue.length) {
            uploadBusy = false
            uploadMessage = i18n.tr("Uploaded %1 of %2 files.").arg(uploadSucceeded).arg(uploadQueue.length)
            loadDirectory(currentPath)
            return
        }
        var entry = uploadQueue[uploadIndex]
        uploadName = entry.name
        uploadFraction = 0
        awaitingConfirmation = false
        backend.call("main.upload_file", [entry.localPath,
            uploadDestination.replace(/\/+$/, "") + "/" + encodeURIComponent(entry.name)],
            function(result) {
                if (result && result.success) {
                    uploadSucceeded++
                } else {
                    uploadErrors += (uploadErrors ? "\n" : "") + entry.name + ": "
                        + (result && result.message ? result.message : i18n.tr("Upload failed."))
                    if (result && result.status) uploadErrors += " (HTTP " + result.status + ")"
                }
                uploadIndex++
                uploadNext()
            })
    }

    function receiveFiles() {
        if (transferHandled) return
        transferHandled = true
        selectingFiles = false
        var queue = []
        uploadErrors = ""
        for (var i = 0; i < activeTransfer.items.length; i++) {
            var item = activeTransfer.items[i]
            try {
                var localUrl = item.url.toString()
                if (localUrl.indexOf("file:///") !== 0)
                    throw new Error(i18n.tr("The selected item is not a local file."))
                var localPath = decodeURIComponent(localUrl.substring(7))
                var fileName = item.name || localPath.substring(localPath.lastIndexOf("/") + 1)
                if (!fileName || fileName === "." || fileName === ".." || fileName.indexOf("/") !== -1)
                    throw new Error(i18n.tr("Invalid file name."))
                queue.push({localPath: localPath, name: fileName})
            } catch (error) {
                uploadErrors += (uploadErrors ? "\n" : "")
                    + i18n.tr("The selected file could not be prepared. Choose it again.")
            }
        }
        uploadQueue = queue
        uploadIndex = 0
        uploadSucceeded = 0
        uploadBusy = queue.length > 0
        uploadMessage = queue.length ? "" : i18n.tr("No files selected for upload.")
        if (uploadBusy) uploadNext()
    }

    function loadDirectory(path) {
    if (editorBusy || textNameDialog || folderBusy || deleteBusy || deleteDialog || (batchController && batchController.present)) return
    selectionMode = false
    selectedKeys = []
    var request = ++listGeneration
    currentPath = path
    if (path === "/") {
        displayPath = "/"
    } else {
        displayPath = path.replace("/remote.php/webdav", "").replace(/\/$/, "")
    }
    fileModel.clear()

    backend.call(
        "main.list_directory",
        [path],
        function(result) {
                if (request !== listGeneration) return
                if (!result.success) {
                    fileModel.append({
                        "name": i18n.tr("Error: %1").arg(result.message),
                        "isDirectory": false
                    })
                    return
            }

            for (var i = 0; i < result.items.length; i++) {
                var item = result.items[i]

                if (item.name === "webdav") {
                    continue
                }

                fileModel.append({
                    "name": item.name,
                    "path": item.path,
                    "isDirectory": item.isDirectory,
                    "size": item.size,
                    "displaySize": item.displaySize,
                    "lastModified": item.lastModified,
                    "contentType": item.contentType,
                    "selectKey": item.selectKey || ""
                })
            }
        }
    )
}


    Rectangle {
        id: peerPickerBackground
        anchors.fill: parent
        color: "black"
        visible: peerPicker.visible
        z: 100

        ContentPeerPicker {
            id: peerPicker
            anchors.fill: parent

            handler: ContentHandler.Source
            contentType: ContentType.All

            onPeerSelected: {

                peer.selectionType = ContentTransfer.Multiple
                transferHandled = false
                activeTransfer = peer.request()


                peerPickerBackground.visible = false
            }

            onCancelPressed: {
                peerPickerBackground.visible = false
                selectingFiles = false
            }
        }

        Connections {
            target: activeTransfer ? activeTransfer : null

            onStateChanged: {
                if (!activeTransfer)
                    return


                if (activeTransfer.state === ContentTransfer.Charged) {
                    receiveFiles()
                } else if (activeTransfer.state === ContentTransfer.Aborted) {
                    selectingFiles = false
                    uploadMessage = i18n.tr("File selection was cancelled.")
                }

            }
        }

    }

    header: PageHeader {
        id: header
        title: displayPath === "/" ? i18n.tr("Files") : displayPath
          leadingActionBar.actions: [
          Action {
              iconName: "back"
              text: i18n.tr("Back")
              visible: currentPath !== "/"
              enabled: !transferBusy && !selectionMode

                onTriggered: {
                  if (pathHistory.length > 0) {
                      var previousPath = pathHistory.pop()
                      loadDirectory(previousPath)
                  }
              }
          }
      ]

           trailingActionBar.actions: [
               Action {
                   objectName: "newTextAction"
                   iconName: "add"
                   text: i18n.tr("New text file")
                   enabled: !transferBusy && !selectionMode
                   onTriggered: newTextFile()
               },
               Action {
                   objectName: "selectFilesAction"
                   iconName: "select"
                   text: i18n.tr("Select files")
                   enabled: !transferBusy && !folderDialog
                   onTriggered: { selectionMode = !selectionMode; selectedKeys = [] }
               },
               Action {
                   objectName: "newFolderAction"
                   iconName: "folder-symbolic"
                   text: i18n.tr("New folder")
                   enabled: !transferBusy && !selectionMode
                   onTriggered: openFolderDialog()
               },
               Action {
                   objectName: "refreshAction"
                   iconName: "reload"
                   text: i18n.tr("Refresh")
                   enabled: !transferBusy && !selectionMode
                   onTriggered: loadDirectory(currentPath)
               },
               Action {
                   iconName: "add"
                   text: i18n.tr("Upload")
                   enabled: !transferBusy && !selectionMode

                   onTriggered: {
                       uploadDestination = currentPath
                       selectingFiles = true
                       uploadMessage = ""
                       uploadErrors = ""
                       peerPickerBackground.visible = true
                   }

               }
           ]

    }

    ListModel {
        id: fileModel


    }

    Column {
        id: selectionPanel
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: units.gu(1)
        spacing: units.gu(1)
        visible: selectionMode || (batchController && batchController.present)
        Label {
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: selectionMode ? i18n.tr("%1 files selected").arg(selectedKeys.length)
                 : batchController && batchController.cancelRequested && batchController.busy ? i18n.tr("Cancelling…")
                 : batchController && batchController.current ? i18n.tr("File %1 of %2: %3").arg(batchController.position).arg(batchController.files.length).arg(batchController.current.name)
                 : batchController && batchController.busy ? i18n.tr("Preparing downloads…") : i18n.tr("Download job finished")
        }
        Flow {
            width: parent.width
            spacing: units.gu(1)
            visible: selectionMode
            Button { objectName: "selectAllFiles"; text: i18n.tr("Select all"); onClicked: selectAllFiles() }
            Button { text: i18n.tr("Clear selection"); onClicked: selectedKeys = [] }
        }
        Flow {
            width: parent.width
            spacing: units.gu(1)
            visible: selectionMode
            Button { objectName: "startSelectedDownloads"; text: i18n.tr("Download"); enabled: selectedKeys.length > 0; onClicked: startSelectedDownloads() }
            Button { text: i18n.tr("Leave selection"); onClicked: { selectionMode = false; selectedKeys = [] } }
        }
        ProgressBar {
            width: parent.width
            visible: !!(batchController && batchController.busy && batchController.current)
            minimumValue: 0
            maximumValue: 1
            indeterminate: !!(batchController && batchController.current && batchController.current.total === null)
            value: batchController && batchController.current && batchController.current.total > 0
                ? Math.min(0.99, batchController.current.received / batchController.current.total) : 0
        }
        Label {
            textFormat: Text.PlainText
            visible: !!(batchController && batchController.busy && batchController.current)
            text: batchController && batchController.current ? (batchController.current.total > 0
                ? Math.min(99, Math.floor(batchController.current.received * 100 / batchController.current.total)) + " %"
                : Math.floor(batchController.current.received / 1024) + " KiB") : ""
        }
        ProgressBar {
            width: parent.width
            visible: !!(batchController && batchController.present && batchController.files.length)
            minimumValue: 0
            maximumValue: 1
            value: batchController ? batchController.fraction : 0
        }
        Label {
            width: parent.width
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            visible: !!(batchController && batchController.present)
            text: batchController ? i18n.tr("Processed: %1 of %2. Progress weighted by files: %3 %.").arg(batchController.counts.processed).arg(batchController.files.length).arg(Math.floor(batchController.fraction * 100)) : ""
        }
        Label {
            width: parent.width
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            visible: !!(batchController && batchController.present && !batchController.busy)
            text: batchController ? i18n.tr("Downloaded: %1 · Failed: %2 · Cancelled: %3").arg(batchController.counts.succeeded).arg(batchController.counts.failed).arg(batchController.counts.cancelled) : ""
        }
        Flickable {
            width: parent.width
            height: Math.min(batchErrors.height, units.gu(12))
            contentHeight: batchErrors.height
            clip: true
            visible: !!(batchController && batchController.present)
            Label {
                id: batchErrors
                width: parent.width
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                text: {
                    if (!batchController) return ""
                    var messages = batchController.message ? [batchController.message] : []
                    for (var i = 0; i < batchController.files.length; i++) {
                        var entry = batchController.files[i]
                        if (entry.message) messages.push(entry.name + ": " + entry.message)
                    }
                    return messages.join("\n")
                }
            }
        }
        Button {
            objectName: "cancelDownloadJob"
            text: i18n.tr("Cancel downloads")
            visible: !!(batchController && batchController.busy)
            enabled: !!(batchController && !batchController.cancelRequested)
            onClicked: batchController.cancel()
        }
        Button {
            objectName: "saveDownloadedFiles"
            text: i18n.tr("Save downloaded files…")
            visible: !!(batchController && batchController.present && !batchController.busy && batchController.counts.succeeded)
            enabled: !(exportController && exportController.exportBusy)
            onClicked: batchController.save()
        }
        Button {
            objectName: "discardDownloadJob"
            text: i18n.tr("Discard results and temporary files")
            visible: !!(batchController && batchController.present && !batchController.busy)
            enabled: !(exportController && exportController.exportBusy)
            onClicked: batchController.clear()
        }
    }

    Column {
        id: uploadPanel
        anchors.top: selectionPanel.visible ? selectionPanel.bottom : header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: units.gu(1)
        spacing: units.gu(1)
        visible: uploadBusy || selectingFiles || uploadMessage !== "" || uploadErrors !== ""

        Label {
            width: parent.width
            wrapMode: Text.Wrap
            text: uploadBusy ? i18n.tr("Uploading %1 of %2: %3").arg(uploadIndex + 1).arg(uploadQueue.length).arg(uploadName)
                             : selectingFiles ? i18n.tr("Waiting for file selection…") : uploadMessage
        }
        ProgressBar {
            width: parent.width
            visible: uploadBusy
            minimumValue: 0
            maximumValue: 1
            value: uploadFraction
        }
        Label {
            width: parent.width
            visible: uploadBusy
            text: awaitingConfirmation ? i18n.tr("Waiting for server confirmation…")
                                       : Math.floor(uploadFraction * 100) + " %"
        }
        Flickable {
            width: parent.width
            height: Math.min(errorLabel.height, units.gu(12))
            contentHeight: errorLabel.height
            clip: true
            visible: uploadErrors !== ""
            Label {
                id: errorLabel
                width: parent.width
                wrapMode: Text.Wrap
                text: uploadErrors
            }
        }
        Button {
            visible: !uploadBusy && !selectingFiles
            text: i18n.tr("Dismiss")
            onClicked: { uploadMessage = ""; uploadErrors = "" }
        }
    }

    Column {
        id: downloadPanel
        anchors.top: uploadPanel.visible ? uploadPanel.bottom : (selectionPanel.visible ? selectionPanel.bottom : header.bottom)
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: units.gu(1)
        spacing: units.gu(1)
        visible: editorBusy || downloadBusy || downloadMessage !== ""
        Label {
            width: parent.width
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            text: editorBusy ? i18n.tr("Loading editor…") : downloadBusy ? i18n.tr("Downloading: %1").arg(downloadName) : downloadMessage
        }
        ActivityIndicator {
            visible: browserPage.editorBusy || (browserPage.deleteBusy && !browserPage.deleteDialog)
            running: visible
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
            text: downloadTotal > 0
                ? Math.min(99, Math.floor(downloadedBytes * 100 / downloadTotal)) + " %"
                : Math.floor(downloadedBytes / 1024) + " KiB"
        }
        Button {
            visible: !downloadBusy
            text: i18n.tr("Dismiss")
            onClicked: downloadMessage = ""
        }
    }

    ListView {
        objectName: "webdavFileList"
        anchors {
            top: downloadPanel.visible ? downloadPanel.bottom : (uploadPanel.visible ? uploadPanel.bottom : (selectionPanel.visible ? selectionPanel.bottom : header.bottom))
            topMargin: units.gu(1)
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        model: fileModel

delegate: ListItem {
    id: fileDelegate
    property string remoteName: model.name || ""
    property string remotePath: model.path || ""
    property bool remoteDirectory: !!model.isDirectory
    objectName: "webdavFileRow"
    height: Math.max(units.gu(7), fileText.implicitHeight + units.gu(2))
    swipeEnabled: !browserPage.selectionMode
    property string selectionKey: model.selectKey || ""

    trailingActions: ListItemActions {
        actions: [
            Action {
                iconName: "save"
                text: i18n.tr("Download…")
                visible: !fileDelegate.remoteDirectory
                enabled: !browserPage.transferBusy && !browserPage.selectionMode && !fileDelegate.remoteDirectory
                onTriggered: {
                    exportToFileManager = true
                    downloadFile(fileDelegate.remotePath, fileDelegate.remoteName, "export")
                }
            },
            Action {
                iconName: "external-link"
                text: i18n.tr("Open in another app…")
                visible: !fileDelegate.remoteDirectory
                enabled: !browserPage.transferBusy && !browserPage.selectionMode && !fileDelegate.remoteDirectory
                onTriggered: {
                    exportToFileManager = false
                    downloadFile(fileDelegate.remotePath, fileDelegate.remoteName, "export")
                }
            },
            Action {
                objectName: "deleteResourceAction"
                iconName: "delete"
                text: i18n.tr("Delete…")
                enabled: !browserPage.transferBusy && !browserPage.selectionMode && fileDelegate.remotePath !== ""
                onTriggered: browserPage.requestDelete(fileDelegate.remotePath)
            },
            Action {
                objectName: "editTextAction"
                iconName: "edit"
                text: i18n.tr("Edit…")
                visible: !fileDelegate.remoteDirectory && EditorRules.editable(fileDelegate.remoteName)
                enabled: visible && !browserPage.transferBusy && !browserPage.selectionMode && fileDelegate.selectionKey !== ""
                onTriggered: browserPage.openEditor(fileDelegate.remotePath, "")
            }
        ]
    }

    onClicked: {
        if (transferBusy) return
        if (selectionMode) {
            if (!fileDelegate.remoteDirectory && fileDelegate.selectionKey)
                selectedKeys = Selection.toggle(selectedKeys, fileDelegate.selectionKey)
            return
        }
        if (isDirectory) {
            pathHistory.push(currentPath)
            loadDirectory(path)
        } else {
            var lowerName = name.toLowerCase()
            if (EditorRules.editable(lowerName)) {
                downloadFile(path, name, "text")
            } else if (/\.(jpe?g|png)$/.test(lowerName)) {
                downloadFile(path, name, "image")
            } else if (lowerName.endsWith(".pdf")) {
                downloadFile(path, name, "pdf")
            } else {
                exportToFileManager = true
                downloadFile(fileDelegate.remotePath, fileDelegate.remoteName, "export")
            }
        }
    }

    CheckBox {
        id: selectionBox
        objectName: "fileSelectionBox"
        anchors.left: parent.left
        anchors.leftMargin: units.gu(1)
        anchors.verticalCenter: parent.verticalCenter
        visible: browserPage.selectionMode && !fileDelegate.remoteDirectory && fileDelegate.selectionKey !== ""
        checked: browserPage.selectedKeys.indexOf(fileDelegate.selectionKey) >= 0
        onClicked: browserPage.selectedKeys = Selection.toggle(browserPage.selectedKeys, fileDelegate.selectionKey)
    }

    Icon {
        id: fileIcon
        objectName: "fileTypeIcon"
        anchors.left: parent.left
        anchors.leftMargin: selectionBox.visible ? units.gu(6) : units.gu(2)
        anchors.verticalCenter: parent.verticalCenter
        width: units.gu(3)
        height: width
        name: FileIcons.iconName(fileDelegate.remoteName, fileDelegate.remoteDirectory, model.contentType)
        color: theme.palette.normal.baseText
    }

    Column {
        id: fileText
        anchors.left: fileIcon.right
        anchors.leftMargin: units.gu(2)
        anchors.right: parent.right
        anchors.rightMargin: units.gu(2)
        anchors.verticalCenter: parent.verticalCenter
        spacing: units.gu(0.5)

        Label {
            objectName: "fileNameLabel"
            width: parent.width
            text: fileDelegate.remoteName
            textFormat: Text.PlainText
            color: theme.palette.normal.baseText
            wrapMode: Text.Wrap
        }
        Label {
            objectName: "fileSizeLabel"
            width: parent.width
            visible: text !== ""
            text: model.displaySize || ""
            textFormat: Text.PlainText
            color: theme.palette.normal.baseText
            wrapMode: Text.Wrap
        }
    }
}
    }
}
