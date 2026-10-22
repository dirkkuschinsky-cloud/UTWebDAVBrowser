import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"

MainView {
    id: window
    width: 400
    height: 800
    QtObject {
        id: fake
        property int creates: 0
        property int lists: 0
        property var pending: null
        property var received: []
        function setHandler(name, handler) {}
        function call(method, args, callback) {
            if (method === "main.create_directory") {
                creates++
                received = args
                pending = callback
            } else if (method === "main.list_directory") {
                lists++
                callback({success: true, items: []})
            }
        }
    }
    QtObject {
        id: fakeExport
        property bool exportBusy: false
        signal progress(var received, var total)
    }
    BrowserPage { id: page; anchors.fill: parent; backend: fake; exportController: fakeExport }
    TestCase {
        name: "CreateFolder"
        when: windowShown
        function field(name) { return findChild(page.folderDialog, name) }
        function init() {
            page.loadDirectory('/dav/B%C3%BCro/')
            fake.creates = 0
            fake.lists = 0
            page.openFolderDialog()
            verify(page.folderDialog !== null)
            wait(100)
        }
        function cleanup() {
            if (page.folderBusy) fake.pending({success: false, message: 'cleanup'})
            if (page.folderDialog) field('cancelFolderButton').clicked()
            wait(100)
        }
        function test_validation() {
            var names = ['', ' ', '.', '..', 'a/b', 'a\\b', '\n', '\x7f']
            for (var i = 0; i < names.length; i++) {
                field('newFolderName').text = names[i]
                verify(!field('createFolderButton').enabled)
                page.folderDialog.createFolder()
            }
            compare(fake.creates, 0)
            var valid = ['Grüße Ordner', '%', '%2F', '#?&', '<b>']
            for (i = 0; i < valid.length; i++) {
                field('newFolderName').text = valid[i]
                verify(field('createFolderButton').enabled)
            }
        }
        function test_double_activation_and_success() {
            field('newFolderName').text = 'Grüße %2F'
            page.folderDialog.createFolder()
            page.folderDialog.createFolder()
            compare(fake.creates, 1)
            compare(fake.received[0], '/dav/B%C3%BCro/')
            compare(fake.received[1], 'Grüße %2F')
            verify(page.transferBusy)
            verify(!field('createFolderButton').enabled)
            verify(!field('cancelFolderButton').enabled)
            page.loadDirectory('/different/')
            compare(page.currentPath, '/dav/B%C3%BCro/')
            compare(fake.lists, 0)
            fake.pending({success: true})
            verify(!page.folderBusy)
            compare(page.folderDialog, null)
            compare(fake.lists, 1)
            compare(page.currentPath, '/dav/B%C3%BCro/')
        }
        function test_error_preserves_name_and_manual_refresh() {
            field('newFolderName').text = 'Existing'
            page.folderDialog.createFolder()
            fake.pending({success: false, status: 405, message: 'May exist'})
            compare(field('newFolderName').text, 'Existing')
            compare(field('newFolderError').text, 'May exist')
            verify(field('createFolderButton').enabled)
            compare(fake.lists, 0)
            wait(100)
            compare(fake.creates, 1)
            field('newFolderName').text = 'Corrected'
            page.folderDialog.createFolder()
            compare(fake.creates, 2)
            fake.pending({success: false, message: 'Disconnected; refresh first'})
            field('cancelFolderButton').clicked()
            findChild(page, 'refreshAction').trigger(null)
            compare(fake.lists, 1)
        }
        function test_escape_lifecycle() {
            page.folderDialog.hide()
            wait(300)
            compare(page.folderDialog, null)
            page.openFolderDialog()
            field('newFolderName').text = 'Pending'
            page.folderDialog.createFolder()
            page.folderDialog.hide()
            wait(350)
            verify(page.folderDialog !== null)
            verify(page.folderDialog.visible)
            compare(fake.creates, 1)
            fake.pending({success: false, message: 'failed'})
        }
        function test_cancel_no_request() {
            field('newFolderName').text = 'Cancelled'
            field('cancelFolderButton').clicked()
            compare(fake.creates, 0)
            compare(page.folderDialog, null)
        }
        function test_tablet_layout() {
            window.width = 1000
            window.height = 700
            wait(100)
            verify(field('newFolderName').width > 0)
            field('newFolderName').text = 'Tablet'
            verify(field('createFolderButton').enabled)
            window.width = 400
            window.height = 800
        }
    }
}
