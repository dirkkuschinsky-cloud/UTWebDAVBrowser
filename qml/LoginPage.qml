import QtQuick 2.7
import Lomiri.Components 1.3
import QtQuick.Layouts 1.3

Page {
    id: loginPage

    property var backend
    property bool backendReady: false
    property bool busy: false
    property bool settingsLoaded: false
    property string statusMessage: ""
    signal loginSuccessful(string warning)

    function restoreConnection() {
        if (!backendReady || settingsLoaded) return
        settingsLoaded = true
        busy = true
        backend.call("main.load_connection", [], function(result) {
            serverField.text = result && result.success ? result.server : ""
            userField.text = result && result.success ? result.username : ""
            passwordField.text = ""
            statusMessage = result && !result.success ? result.message : ""
            busy = false
        })
    }

    function connectToServer() {
        if (!backendReady || busy) return
        busy = true
        statusMessage = ""
        backend.call("main.connect", [serverField.text, userField.text, passwordField.text], function(result) {
            busy = false
            if (result && result.success) {
                passwordField.text = ""
                loginSuccessful(result.warning || "")
            } else {
                statusMessage = result && result.message ? result.message : i18n.tr("Connection failed.")
            }
        })
    }

    function deleteSavedConnection() {
        if (!backendReady || busy) return
        busy = true
        backend.call("main.delete_connection", [], function(result) {
            if (result && result.success) {
                serverField.text = ""
                userField.text = ""
                passwordField.text = ""
                statusMessage = i18n.tr("Saved connection settings deleted.")
            } else {
                statusMessage = result && result.message ? result.message : i18n.tr("Could not delete saved settings.")
            }
            busy = false
        })
    }

    Component.onCompleted: restoreConnection()
    onBackendReadyChanged: restoreConnection()

    header: PageHeader {
        id: header
        title: i18n.tr("UT WebDAV Browser")
    }

    Flickable {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        contentHeight: fields.height + units.gu(4)
        clip: true

        Column {
            id: fields
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: units.gu(2)
            spacing: units.gu(2)

            TextField {
                id: serverField
                objectName: "loginServer"
                width: parent.width
                placeholderText: i18n.tr("WebDAV URL")
                enabled: loginPage.backendReady && !loginPage.busy
                inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoPredictiveText
            }
            TextField {
                id: userField
                objectName: "loginUsername"
                width: parent.width
                placeholderText: i18n.tr("Username")
                enabled: loginPage.backendReady && !loginPage.busy
                inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            }
            TextField {
                id: passwordField
                objectName: "loginPassword"
                width: parent.width
                placeholderText: i18n.tr("Password")
                echoMode: TextInput.Password
                enabled: loginPage.backendReady && !loginPage.busy
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            }
            Label {
                width: parent.width
                text: i18n.tr("Only the URL and username are saved. The password is used for this session only.")
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
            Button {
                objectName: "loginConnect"
                text: loginPage.busy ? i18n.tr("Please wait…") : i18n.tr("Connect")
                enabled: loginPage.backendReady && !loginPage.busy
                onClicked: loginPage.connectToServer()
            }
            Button {
                objectName: "loginDelete"
                text: i18n.tr("Delete saved connection settings")
                enabled: loginPage.backendReady && !loginPage.busy
                onClicked: loginPage.deleteSavedConnection()
            }
            Label {
                width: parent.width
                visible: text !== ""
                text: loginPage.statusMessage
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
        }
    }
}
