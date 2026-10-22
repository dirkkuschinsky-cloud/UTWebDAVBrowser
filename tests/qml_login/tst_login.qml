import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"

MainView {
    width: 400
    height: 800
    QtObject {
        id: fake
        property int loads: 0
        property bool deferLoad: false
        property var pending: null
        property var loaded: ({success: true, server: "https://example.org/Büro/", username: "Jörg"})
        property var connected: ({success: true, saved: true})
        property var deleted: ({success: true})
        property var receivedArguments: []
        function call(method, args, callback) {
            if (method === "main.load_connection") {
                loads++
                if (deferLoad) pending = callback
                else callback(loaded)
            } else if (method === "main.connect") {
                receivedArguments = args
                callback(connected)
            } else if (method === "main.delete_connection") callback(deleted)
        }
    }
    Component { id: factory; LoginPage { backend: fake } }
    SignalSpy { id: successSpy; signalName: "loginSuccessful" }
    TestCase {
        name: "ConnectionSettingsLogin"
        when: windowShown
        property var page: null
        function field(name) { return findChild(page, name) }
        function init() {
            fake.loads = 0
            fake.deferLoad = false
            fake.pending = null
            fake.loaded = {success: true, server: "https://example.org/Büro/", username: "Jörg"}
            fake.connected = {success: true, saved: true}
            fake.deleted = {success: true}
            fake.receivedArguments = []
            page = factory.createObject(parent, {width: 400, height: 800})
            verify(page !== null)
            successSpy.target = page
            successSpy.clear()
        }
        function cleanup() {
            successSpy.target = null
            page.destroy()
            page = null
            wait(0)
        }
        function test_wait_for_backend_and_load_once() {
            compare(fake.loads, 0)
            compare(field("loginServer").text, "")
            verify(!field("loginConnect").enabled)
            fake.deferLoad = true
            page.backendReady = true
            compare(fake.loads, 1)
            verify(page.busy)
            verify(!field("loginServer").enabled)
            fake.pending(fake.loaded)
            verify(!page.busy)
            compare(field("loginServer").text, "https://example.org/Büro/")
            compare(field("loginUsername").text, "Jörg")
            compare(field("loginPassword").text, "")
            page.backendReady = false
            page.backendReady = true
            compare(fake.loads, 1)
        }
        function test_first_start_empty() {
            fake.loaded = {success: true, server: "", username: ""}
            page.backendReady = true
            compare(field("loginServer").text, "")
            compare(field("loginUsername").text, "")
            compare(field("loginPassword").text, "")
        }
        function test_corrupt_settings_do_not_block_login() {
            fake.loaded = {success: false, message: "Invalid settings"}
            page.backendReady = true
            verify(field("loginConnect").enabled)
            compare(field("loginServer").text, "")
            compare(page.statusMessage, "Invalid settings")
        }
        function test_success_clears_password_and_emits_warning() {
            page.backendReady = true
            field("loginPassword").text = "SESSION_ONLY"
            fake.connected = {success: true, saved: false, warning: "Not saved"}
            page.connectToServer()
            compare(fake.receivedArguments[0], "https://example.org/Büro/")
            compare(fake.receivedArguments[1], "Jörg")
            compare(fake.receivedArguments[2], "SESSION_ONLY")
            compare(field("loginPassword").text, "")
            compare(successSpy.count, 1)
            compare(successSpy.signalArguments[0][0], "Not saved")
        }
        function test_failed_login_stays_on_page() {
            page.backendReady = true
            fake.connected = {success: false, message: "Connection failed"}
            page.connectToServer()
            compare(successSpy.count, 0)
            verify(!page.busy)
            compare(page.statusMessage, "Connection failed")
        }
        function test_delete_clears_fields() {
            page.backendReady = true
            field("loginPassword").text = "SESSION_ONLY"
            page.deleteSavedConnection()
            compare(field("loginServer").text, "")
            compare(field("loginUsername").text, "")
            compare(field("loginPassword").text, "")
        }
        function test_delete_error_preserves_fields() {
            page.backendReady = true
            fake.deleted = {success: false, message: "Cannot delete"}
            page.deleteSavedConnection()
            compare(page.statusMessage, "Cannot delete")
            compare(field("loginUsername").text, "Jörg")
            verify(!page.busy)
        }
    }
}
