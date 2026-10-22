import QtQuick 2.7
import Lomiri.Components 1.3
import Lomiri.Content 1.3
import "../../qml"

MainView {
    Component.onCompleted: page.loadDirectory("/")
    width: 600
    height: 800
    QtObject {
        id: fakeBackend
        property var handlers: ({})
        property var released: []
        property int acquired: 0
        property bool failAcquire: false
        function setHandler(name, handler) { handlers[name] = handler }
        function call(method, args, callback) {
            if (method === "main.release_download") {
                released.push(args[0])
                callback({success: true})
            } else if (method === "main.acquire_download") {
                acquired++
                if (failAcquire) { callback({success: false, message: "Network error"}); return }
                callback({success: true, localFile: "/cache/Grüße %.txt",
                    localUrl: "file:///cache/Gr%C3%BC%C3%9Fe%20%25.txt", fileName: "Grüße %.txt",
                    remotePath: "/dav/file.txt", cacheRef: "export-" + acquired})
            } else if (method === "main.list_directory") {
                callback({success: true, items: [{name: "test.txt", path: "/dav/test.txt",
                    isDirectory: false, size: "4", displaySize: "4 B", lastModified: "", contentType: "text/plain"}]})
            } else if (method === "main.download_file") {
                callback({success: true, localFile: "/cache/Grüße %.txt",
                    localUrl: "file:///cache/Gr%C3%BC%C3%9Fe%20%25.txt", fileName: "Grüße %.txt"})
            }
        }
    }
    QtObject {
        id: fakeTransfer
        property int state: ContentTransfer.Created
        property var items: []
        property int finalized: 0
        function finalize() { finalized++; state = ContentTransfer.Finalized }
    }
    ExportController { id: controller; anchors.fill: parent; backend: fakeBackend; z: 200 }
    BrowserPage { id: page; anchors.fill: parent; backend: fakeBackend; exportController: controller }
    Component { id: textFactory; TextViewerPage {} }
    Component { id: imageFactory; ImageViewerPage {} }
    Component { id: pdfFactory; PdfViewerPage {} }
    Timer {
        interval: 100
        running: true
        onTriggered: {
            try {
                var tests = ["test_progress", "test_export_lifetime_and_collection", "test_cancel_picker",
                    "test_aborted_transfer", "test_return_retains_collected_file", "test_failed_request", "test_terminal_initial_state", "test_upload_navigation_guard", "test_repeated_save", "test_acquire_error", "test_cancel_then_save", "test_viewer_save_actions"]
                for (var i = 0; i < tests.length; i++) {
                    smoke.init()
                    smoke[tests[i]]()
                    console.log("PASS: " + tests[i])
                }
                console.log("DOWNLOAD_SMOKE_PASS")
            } catch (error) {
                console.error("DOWNLOAD_SMOKE_FAIL: " + error)
            }
            Qt.quit()
        }
    }
    QtObject {
        id: smoke
        function verify(value) { if (!value) throw new Error("Verification failed") }
        function compare(actual, expected) {
            if (actual !== expected) throw new Error("Expected " + expected + ", got " + actual)
        }
        function init() {
            controller.exportTransfer = null
            fakeTransfer.state = ContentTransfer.Created
            fakeTransfer.items = []
            fakeTransfer.finalized = 0
            fakeBackend.released = []
            controller.pendingExport = null
            controller.exportBusy = false
            controller.exportFinishing = false
            controller.exportCollected = false
            controller.exportCharged = false
            controller.destinationPickerVisible = false
            page.downloadBusy = false
            page.downloadMessage = ""
            controller.downloadMessage = ""
            fakeBackend.failAcquire = false
        }
        function prepare() {
            page.downloadFile("/dav/Gr%C3%BC%C3%9Fe.txt", "Grüße %.txt", "export")
            verify(controller.exportBusy)
            verify(controller.destinationPickerVisible)
        }
        function test_return_retains_collected_file() {
            prepare()
            controller.startExport({selectionType:0,request:function(){return fakeTransfer}})
            fakeTransfer.state=ContentTransfer.InProgress
            fakeTransfer.state=ContentTransfer.Collected
            verify(controller.returnToApp())
            verify(!controller.exportBusy)
            compare(controller.downloadMessage, "")
            compare(fakeBackend.released.length, 0)
            compare(fakeTransfer.finalized, 0)
            fakeTransfer.state=ContentTransfer.Finalized
            compare(fakeBackend.released.length, 1)
            compare(controller.retainedExportCount, 0)
        }
        function test_progress() {
            page.downloadBusy = true
            fakeBackend.handlers.downloadProgress(200, null)
            compare(page.downloadTotal, -1)
            fakeBackend.handlers.downloadProgress(500, 1000)
            compare(page.downloadTotal, 1000)
            compare(page.downloadedBytes, 500)
        }
        function test_export_lifetime_and_collection() {
            prepare()
            controller.startExport({selectionType: 0, request: function() { return fakeTransfer }})
            compare(fakeBackend.released.length, 0)
            fakeTransfer.state = ContentTransfer.InProgress
            compare(fakeTransfer.state, ContentTransfer.Charged)
            compare(fakeTransfer.items.length, 1)
            compare(fakeTransfer.items[0].name, "Grüße %.txt")
            compare(decodeURIComponent(fakeTransfer.items[0].url.toString()), "file:///cache/Grüße %.txt")
            compare(fakeBackend.released.length, 0)
            fakeTransfer.state = ContentTransfer.Collected
            compare(fakeBackend.released.length, 0)
            compare(fakeTransfer.finalized, 0)
            verify(controller.exportBusy)
            verify(controller.exportItem !== null)
            verify(controller.pendingExport !== null)
            // The destination copies the file, then finalizes the transfer.
            fakeTransfer.state = ContentTransfer.Finalized
            compare(fakeBackend.released.length, 1)
            compare(fakeTransfer.finalized, 0)
            verify(!controller.exportBusy)
        }
        function test_cancel_picker() {
            prepare()
            controller.finishExport("Cancelled")
            compare(fakeBackend.released.length, 1)
            verify(!controller.exportBusy)
            verify(!controller.destinationPickerVisible)
        }
        function test_aborted_transfer() {
            prepare()
            controller.startExport({selectionType: 0, request: function() { return fakeTransfer }})
            fakeTransfer.state = ContentTransfer.Aborted
            compare(fakeBackend.released.length, 1)
            compare(fakeTransfer.finalized, 1)
            verify(!controller.exportBusy)
        }
        function test_failed_request() {
            prepare()
            controller.startExport({selectionType: 0, request: function() { return null }})
            compare(fakeBackend.released.length, 1)
            verify(!controller.exportBusy)
        }
        function test_terminal_initial_state() {
            prepare()
            fakeTransfer.state = ContentTransfer.Aborted
            controller.startExport({selectionType: 0, request: function() { return fakeTransfer }})
            compare(fakeBackend.released.length, 1)
            verify(!controller.exportBusy)
        }
        function test_repeated_save() {
            for (var i = 0; i < 3; i++) {
                controller.save({localFile: "/cache/file.txt", fileName: "file.txt"}, true)
                controller.startExport({selectionType: 0, request: function() { return fakeTransfer }})
                fakeTransfer.state = ContentTransfer.InProgress
                fakeTransfer.state = ContentTransfer.Collected
                compare(fakeBackend.released.length, i)
                fakeTransfer.state = ContentTransfer.Finalized
                compare(fakeBackend.released.length, i + 1)
                controller.finishExport("Duplicate terminal event")
                compare(fakeBackend.released.length, i + 1)
                fakeTransfer.state = ContentTransfer.Created
            }
        }
        function test_acquire_error() {
            fakeBackend.failAcquire = true
            controller.save({fileName: "file.txt"}, true)
            compare(fakeBackend.released.length, 0)
            verify(!controller.exportBusy)
            verify(controller.downloadMessage.indexOf("Network error") !== -1)
        }
        function test_cancel_then_save() {
            prepare()
            controller.finishExport("Cancelled")
            compare(fakeBackend.released.length, 1)
            prepare()
            controller.startExport({selectionType: 0, request: function() { return null }})
            compare(fakeBackend.released.length, 2)
            verify(fakeBackend.released[0] !== fakeBackend.released[1])
        }
        function test_viewer_save_actions() {
            var factories = [textFactory, imageFactory, pdfFactory]
            for (var i = 0; i < factories.length; i++) {
                var viewer = factories[i].createObject(page, {downloadInfo: {
                    localFile: "/cache/file", fileName: "file", cacheRef: "preview", remotePath: "/dav/file"}})
                verify(viewer !== null)
                viewer.saveRequested.connect(function() { controller.save(viewer.downloadInfo, true) })
                var action = viewer.header.trailingActionBar.actions[0]
                verify(action.enabled)
                action.triggered(null)
                verify(controller.exportBusy)
                verify(controller.destinationPickerVisible)
                controller.finishExport("Cancelled")
                viewer.destroy()
            }
            compare(fakeBackend.released.length, 3)
        }
        function test_upload_navigation_guard() {
            page.uploadBusy = true
            page.downloadFile("/dav/file", "file", "export")
            compare(controller.pendingExport, null)
            page.uploadBusy = false
        }
    }
}
