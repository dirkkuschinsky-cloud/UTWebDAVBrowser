import QtQuick 2.7
import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import "EditorRules.js" as Rules

Page {
    id: editor
    property var backend
    property var session: ({})
    property string savedText: session.text || ""
    property bool dirty: input.text !== savedText
    property bool busy: false
    property bool writable: !!session.canOverwrite
    property string message: ""
    property string actionHint: ""
    property var closeDialog: null
    property var nameDialog: null
    signal closeRequested()
    signal saved()
    // No draft is persisted. Closing the page releases its backend session.
    Component.onDestruction: {
        if (session.token) backend.call("main.close_editor", [session.token], function(r) {})
    }
    function requestClose() {
        if (busy || closeDialog || nameDialog) return
        if (!dirty) { closeRequested(); return }
        closeDialog = PopupUtils.open(discardComponent, editor)
    }
    function save(name) {
        if (busy || (!name && !writable) || (name && !Rules.validName(name))) return
        busy = true
        message = ""
        backend.call("main.save_editor", [session.token, input.text, name || ""], function(result) {
            busy = false
            if (result && result.success) {
                savedText = input.text
                session = {token: session.token, name: result.name, canOverwrite: result.canOverwrite}
                writable = result.canOverwrite
                message = result.message || i18n.tr("Saved on server.")
                saved()
                if (nameDialog) { PopupUtils.close(nameDialog); nameDialog = null }
            } else {
                // Backend may have blocked a condition after an ambiguous PUT.
                writable = false
                message = result && result.message ? result.message : i18n.tr("Saving could not be confirmed. Check the server before trying again.")
            }
        })
    }
    function saveAs() {
        if (!busy && !nameDialog) nameDialog = PopupUtils.open(nameComponent, editor)
    }
    Keys.priority: Keys.BeforeItem
    Keys.onEscapePressed: { event.accepted = true; requestClose() }
    Keys.onBackPressed: { event.accepted = true; requestClose() }
    header: PageHeader {
        id: editorHeader
        title: session.name + (dirty ? " *" : "")
        leadingActionBar.actions: Action {
            iconName: "back"
            text: i18n.tr("Cancel")
            enabled: !editor.busy
            onTriggered: editor.requestClose()
        }
        trailingActionBar.delegate: AbstractButton {
            id: headerButton
            action: modelData
            objectName: action.objectName + "_button"
            width: units.gu(5)
            height: parent ? parent.height : units.gu(5)
            activeFocusOnTab: true
            Accessible.name: action.text
            Accessible.description: action.description || action.text
            Accessible.role: Accessible.Button
            onPressAndHold: { editor.actionHint = action.text; hintLifetime.restart() }
            onHoveredChanged: {
                if (hovered) hoverHint.restart()
                else { hoverHint.stop(); editor.actionHint = "" }
            }
            Rectangle {
                anchors.fill: parent
                color: headerButton.pressed ? theme.palette.highlighted.background : "transparent"
            }
            Icon {
                anchors.centerIn: parent
                width: units.gu(2.5); height: width
                source: headerButton.iconSource
                color: headerButton.enabled ? theme.palette.normal.backgroundText : theme.palette.disabled.backgroundText
            }
            Timer {
                id: hoverHint
                interval: 700
                onTriggered: { editor.actionHint = headerButton.action.text; hintLifetime.restart() }
            }
        }
        trailingActionBar.actions: [
            Action {
                objectName: "saveEditorAction"
                iconSource: Qt.resolvedUrl("../assets/editor-save.svg")
                text: i18n.tr("Save on server")
                description: i18n.tr("Save this version on the WebDAV server")
                enabled: !editor.busy && editor.writable
                onTriggered: editor.save("")
            },
            Action {
                objectName: "saveEditorAsAction"
                iconName: "add"
                text: i18n.tr("Save under a new name…")
                description: i18n.tr("Create a new file without overwriting an existing file")
                enabled: !editor.busy
                onTriggered: editor.saveAs()
            }
        ]
    }
    Timer { id: hintLifetime; interval: 3000; onTriggered: editor.actionHint = "" }
    Column {
        id: status
        anchors.top: editorHeader.bottom
        width: parent.width
        Label {
            objectName: "editorActionHint"
            width: parent.width
            visible: editor.actionHint !== ""
            height: visible ? implicitHeight : 0
            text: editor.actionHint
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
        }
        Label {
            objectName: "editorMessage"
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: editor.message || (!editor.writable ? i18n.tr("Reload the file or save under a new name.") : "")
        }
        ActivityIndicator { running: editor.busy; visible: running }
    }
    TextArea {
        id: input
        objectName: "editorText"
        anchors { top: status.bottom; bottom: parent.bottom; left: parent.left; right: parent.right; margins: units.gu(1) }
        text: editor.savedText
        textFormat: TextEdit.PlainText
        readOnly: editor.busy
        inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
        Keys.priority: Keys.BeforeItem
        Keys.onEscapePressed: { event.accepted = true; editor.requestClose() }
        Keys.onBackPressed: { event.accepted = true; editor.requestClose() }
    }
    Component {
        id: discardComponent
        Dialog {
            id: discard
            title: i18n.tr("Unsaved changes")
            text: i18n.tr("Discard the changes? Unsaved text will be lost.")
            onVisibleChanged: if (!visible) editor.closeDialog = null
            Button {
                objectName: "continueEditing"
                text: i18n.tr("Continue editing")
                onClicked: { editor.closeDialog = null; PopupUtils.close(discard) }
            }
            Button {
                objectName: "discardEditor"
                text: i18n.tr("Discard changes")
                color: theme.palette.normal.negative
                onClicked: { editor.closeDialog = null; PopupUtils.close(discard); editor.closeRequested() }
            }
        }
    }
    Component {
        id: nameComponent
        Dialog {
            id: names
            title: i18n.tr("Save under a new name")
            onVisibleChanged: {
                if (!visible) {
                    if (editor.busy) show()
                    else editor.nameDialog = null
                }
            }
            TextField {
                id: newName
                objectName: "editorNewName"
                placeholderText: i18n.tr("File name (.txt or .md)")
                enabled: !editor.busy
            }
            Label { objectName: "editorSaveAsError"; text: editor.message; textFormat: Text.PlainText; wrapMode: Text.Wrap }
            Button {
                text: i18n.tr("Save")
                enabled: !editor.busy && Rules.validName(newName.text)
                onClicked: editor.save(newName.text)
            }
            Button {
                text: i18n.tr("Cancel")
                enabled: !editor.busy
                onClicked: { editor.nameDialog = null; PopupUtils.close(names) }
            }
        }
    }
}
