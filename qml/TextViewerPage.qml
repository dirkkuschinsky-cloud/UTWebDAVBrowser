import QtQuick 2.7
import Lomiri.Components 1.3

Page {
    id: textViewer

    property var downloadInfo: null
    property bool saveBusy: false
    signal saveRequested()

    property string fileName: ""
    property string fileContent: ""

    header: PageHeader {
        title: fileName
        trailingActionBar.actions: [
            Action {
                iconName: "save"
                text: i18n.tr("Save…")
                enabled: !textViewer.saveBusy && textViewer.downloadInfo !== null
                onTriggered: textViewer.saveRequested()
            }
        ]
    }

    Flickable {
        anchors.fill: parent
        anchors.margins: units.gu(2)

        contentWidth: parent.width
        contentHeight: textLabel.paintedHeight

        Label {
            id: textLabel
            objectName: "textPreviewContent"
            textFormat: Text.PlainText

            width: parent.width
            wrapMode: Text.Wrap
            text: fileContent
        }
    }
}
