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
        property int prepares: 0
        property int deletes: 0
        property int cancels: 0
        property int lists: 0
        property var pendingPrepare: null
        property var pendingDelete: null
        property var selection: ({success: true, token: "once", name: "Grüße <b>& %2F", isDirectory: false})
        property bool deferred: false
        property var received: []
        function setHandler(name, handler) {}
        function call(method, args, callback) {
            if (method === 'main.prepare_delete') {
                prepares++
                received = args
                if (deferred) pendingPrepare = callback
                else callback(selection)
            } else if (method === 'main.delete_resource') {
                deletes++
                received = args
                pendingDelete = callback
            } else if (method === 'main.cancel_delete') {
                cancels++
                callback({success: true})
            } else if (method === 'main.list_directory') {
                lists++
                callback({success: true, items: [
                    {name: 'Grüße <b>& %2F', path: '/dav/parent/file', isDirectory: false,
                     size: '4', displaySize: '4 B', contentType: 'text/plain', lastModified: ''},
                    {name: 'folder', path: '/dav/parent/folder/', isDirectory: true,
                     size: '', displaySize: '', contentType: '', lastModified: ''}
                ]})
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
        name: 'SafeDeletion'
        when: windowShown
        function field(name) { return findChild(page.deleteDialog, name) }
        function hidePicker(item) {
            if (item.z === 100 && String(item).indexOf('Rectangle') !== -1) item.visible = false
            var children = item.children || []
            for (var i = 0; i < children.length; i++) hidePicker(children[i])
        }
        function init() {
            fake.prepares = 0; fake.deletes = 0; fake.cancels = 0; fake.lists = 0
            fake.deferred = false
            fake.selection = {success: true, token: 'once', name: 'Grüße <b>& %2F', isDirectory: false}
            page.loadDirectory('/dav/parent/')
            hidePicker(page)
            fake.lists = 0
            page.downloadMessage = ''
            wait(100)
        }
        function cleanup() {
            if (page.deleteBusy) {
                if (fake.deletes > 0) fake.pendingDelete({success: false, message: 'cleanup'})
                else fake.pendingPrepare({success: false, message: 'cleanup'})
            }
            if (page.deleteDialog) page.deleteDialog.cancelSelection()
            wait(300)
        }
        function openDialog(directory) {
            fake.selection.isDirectory = directory
            page.requestDelete('/dav/parent/file')
            verify(page.deleteDialog !== null)
            wait(200)
        }
        function row(directory) {
            var items = findChild(page, 'webdavFileList').contentItem.children
            for (var i = 0; i < items.length; i++)
                if (items[i].objectName === 'webdavFileRow' && items[i].remoteDirectory === directory) return items[i]
            fail('Row missing')
        }
        function test_swipe_action_only_opens_confirmation() {
            var item = row(false)
            var x = item.width - 20
            mousePress(item, x, item.height / 2, Qt.LeftButton)
            for (x -= 20; x >= 20; x -= 20) mouseMove(item, x, item.height / 2, 20, Qt.LeftButton)
            mouseRelease(item, 20, item.height / 2, Qt.LeftButton)
            compare(fake.deletes, 0)
            item.trailingActions.actions[2].trigger(null)
            compare(fake.prepares, 1)
            compare(fake.deletes, 0)
            verify(page.deleteDialog !== null)
        }
        function test_file_dialog_plain_text_cancel_default() {
            openDialog(false)
            compare(field('deleteQuestion').textFormat, Text.PlainText)
            verify(field('deleteQuestion').text.indexOf('Grüße <b>& %2F') !== -1)
            verify(!field('deleteFolderWarning').visible)
            verify(field('cancelDeleteButton').activeFocus)
            field('cancelDeleteButton').clicked()
            compare(fake.deletes, 0)
            compare(page.deleteDialog, null)
        }
        function test_folder_warning_and_success_refresh() {
            openDialog(true)
            verify(field('deleteFolderWarning').visible)
            verify(field('deleteFolderWarning').text.indexOf('permanently') !== -1)
            mouseClick(field('confirmDeleteButton'))
            compare(fake.deletes, 1)
            compare(fake.received[0], 'once')
            verify(page.deleteBusy)
            verify(!field('confirmDeleteButton').enabled)
            verify(!field('cancelDeleteButton').enabled)
            field('confirmDeleteButton').clicked()
            page.requestDelete('/dav/parent/folder/')
            page.loadDirectory('/dav/other/')
            compare(fake.deletes, 1)
            compare(fake.prepares, 1)
            compare(page.currentPath, '/dav/parent/')
            fake.pendingDelete({success: true})
            compare(page.deleteDialog, null)
            compare(fake.lists, 1)
            compare(page.currentPath, '/dav/parent/')
            compare(page.downloadMessage, 'Resource deleted.')
        }
        function test_enter_and_escape_never_delete() {
            openDialog(true)
            field('confirmDeleteButton').forceActiveFocus()
            keyClick(Qt.Key_Return)
            keyClick(Qt.Key_Enter)
            compare(fake.deletes, 0)
            keyClick(Qt.Key_Escape)
            wait(350)
            compare(fake.deletes, 0)
            compare(page.deleteDialog, null)
        }
        function test_prepare_wait_failure_and_no_delete() {
            fake.deferred = true
            page.requestDelete('/dav/parent/file')
            page.requestDelete('/dav/parent/file')
            compare(fake.prepares, 1)
            verify(page.deleteBusy)
            page.loadDirectory('/dav/other/')
            compare(page.currentPath, '/dav/parent/')
            fake.pendingPrepare({success: false, message: 'Unsafe path'})
            verify(!page.deleteBusy)
            compare(page.deleteDialog, null)
            compare(fake.deletes, 0)
            compare(page.downloadMessage, 'Unsafe path')
        }
        function test_partial_failure_closes_requires_reselection() {
            openDialog(true)
            field('confirmDeleteButton').clicked()
            fake.pendingDelete({success: false, status: 207, refresh: true, message: 'Partly deleted; locked child'})
            compare(page.downloadMessage, 'Partly deleted; locked child')
            compare(page.deleteDialog, null)
            compare(fake.lists, 1)
            wait(200)
            compare(fake.deletes, 1)
        }
        function test_disconnect_no_retry_manual_refresh() {
            openDialog(false)
            field('confirmDeleteButton').clicked()
            page.deleteDialog.hide()
            wait(350)
            verify(page.deleteDialog.visible)
            fake.pendingDelete({success: false, refresh: true, message: 'Result unknown'})
            compare(page.downloadMessage, 'Result unknown')
            wait(100)
            compare(fake.deletes, 1)
            findChild(page, 'refreshAction').trigger(null)
            compare(fake.lists, 2)
        }
        function test_tablet_layout_and_folder_action() {
            window.width = 1000; window.height = 700
            row(true).trailingActions.actions[2].trigger(null)
            wait(200)
            verify(field('deleteQuestion').width > 0)
            verify(field('confirmDeleteButton').width > 0)
            compare(fake.deletes, 0)
            window.width = 400; window.height = 800
        }
    }
}
