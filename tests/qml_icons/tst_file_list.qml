import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"

MainView {
    id: window
    width: 360
    height: 900
    property string longName: "SehrLangerDateinameOhneLeerzeichen".repeat(5) + "_Grüße_<b>&.PDF"
    QtObject {
        id: fakeBackend
        property string listed: ""
        property string downloaded: ""
        function setHandler(name, handler) {}
        function call(method, args, callback) {
            if (method === "main.list_directory") {
                listed = args[0]
                callback({success: true, items: [
                    {name: window.longName, path: "/dav/long.pdf", isDirectory: false, displaySize: "123 KB", size: "123456", contentType: "application/octet-stream", lastModified: ""},
                    {name: "Ordner.PDF", path: "/dav/dir/", isDirectory: true, displaySize: "", size: "", contentType: "application/pdf", lastModified: ""},
                    {name: "Grüße_<b>&.PNG", path: "/dav/image.png", isDirectory: false, displaySize: "4 KB", size: "4096", contentType: "image/png", lastModified: ""}
                ]})
            } else if (method === "main.download_file") {
                downloaded = args[0]
                callback({success: true, localUrl: "file:///cache/image.png", localFile: "/cache/image.png", fileName: "image.png", cacheRef: "preview"})
            }
        }
    }
    QtObject {
        id: fakeExport
        property bool exportBusy: false
        property string saved: ""
        signal progress(var received, var total)
        function save(info, toFileManager) { saved = info.remotePath }
    }
    BrowserPage { id: page; anchors.fill: parent; backend: fakeBackend; exportController: fakeExport }
    SignalSpy { id: imageSpy; target: page; signalName: "openImageFile" }
    TestCase {
        name: "FileListIcons"
        when: windowShown
        function hideUnavailablePicker(item) {
            // The desktop has no Content Hub service. Hide its initial picker
            // overlay in this fixture so real mouse events reach the file list.
            if (item.z === 100 && String(item).indexOf("Rectangle") !== -1) item.visible = false
            var children = item.children || []
            for (var i = 0; i < children.length; i++) hideUnavailablePicker(children[i])
        }
        function init() {
            fakeExport.saved = ""
            fakeBackend.downloaded = ""
            imageSpy.clear()
            page.loadDirectory("/")
            hideUnavailablePicker(page)
            wait(150)
        }
        function rowFor(name) {
            var list = findChild(page, "webdavFileList")
            var children = list.contentItem.children
            for (var i = 0; i < children.length; i++)
                if (children[i].objectName === "webdavFileRow" && children[i].remoteName === name)
                    return children[i]
            fail("Missing row: " + name)
        }
        function test_long_plain_filename_and_size() {
            var row = rowFor(window.longName)
            var label = findChild(row, "fileNameLabel")
            var size = findChild(row, "fileSizeLabel")
            var icon = findChild(row, "fileTypeIcon")
            compare(label.text, window.longName)
            compare(label.textFormat, Text.PlainText)
            verify(label.lineCount > 1)
            verify(label.width > 0)
            verify(label.paintedWidth <= label.width + 1)
            verify(row.height > units.gu(7))
            verify(row.height >= label.height + size.height + units.gu(2))
            compare(size.text, "123 KB")
            compare(icon.name, "application-pdf-symbolic")
            compare(icon.color, label.color)
            verify(icon.width > 0)
        }
        function test_directory_priority_and_click() {
            var row = rowFor("Ordner.PDF")
            compare(findChild(row, "fileTypeIcon").name, "folder-symbolic")
            mouseClick(row, row.width / 2, row.height / 2)
            compare(fakeBackend.listed, "/dav/dir/")
        }
        function test_image_preview_click() {
            var row = rowFor("Grüße_<b>&.PNG")
            compare(findChild(row, "fileNameLabel").text, "Grüße_<b>&.PNG")
            compare(findChild(row, "fileTypeIcon").name, "image-x-generic-symbolic")
            mouseClick(row, row.width / 2, row.height / 2)
            compare(fakeBackend.downloaded, "/dav/image.png")
            compare(imageSpy.count, 1)
        }
        function test_long_row_download_action() {
            var row = rowFor(window.longName)
            verify(row.trailingActions.actions[0].enabled)
            row.trailingActions.actions[0].trigger(null)
            compare(fakeExport.saved, "/dav/long.pdf")
        }
        function test_long_row_swipe() {
            var row = rowFor(window.longName)
            verify(row.swipeEnabled)
            var center = row.height / 2
            mousePress(row, row.width - 20, center, Qt.LeftButton)
            for (var x = row.width - 40; x >= 20; x -= 20)
                mouseMove(row, x, center, 30, Qt.LeftButton)
            wait(150)
            verify(row.contentItem.x !== 0, "Swipe moves the row content")
            mouseRelease(row, 20, center, Qt.LeftButton)
            wait(250)
            row.trailingActions.actions[0].trigger(null)
            compare(fakeExport.saved, "/dav/long.pdf")
        }
        function test_dark_theme() {
            window.theme.name = "Lomiri.Components.Themes.SuruDark"
            wait(150)
            var row = rowFor(window.longName)
            compare(findChild(row, "fileTypeIcon").color, findChild(row, "fileNameLabel").color)
            window.theme.name = "Lomiri.Components.Themes.Ambiance"
        }
    }
}
