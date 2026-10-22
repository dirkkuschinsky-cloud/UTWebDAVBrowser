import QtQuick 2.7
import Lomiri.Components 1.3

Page {
    id: pdfViewer

    property var downloadInfo: null
    property bool saveBusy: false
    signal saveRequested()

    property string fileName: ""
    property string filePath: ""

    header: PageHeader {
        title: fileName
        trailingActionBar.actions: [
            Action {
                iconName: "save"
                text: i18n.tr("Save…")
                enabled: !pdfViewer.saveBusy && pdfViewer.downloadInfo !== null
                onTriggered: pdfViewer.saveRequested()
            }
        ]
    }

    Button {
    anchors.centerIn: parent
    text: i18n.tr("Open PDF")

    onClicked: {
        Qt.openUrlExternally("file://" + filePath.split("/").map(encodeURIComponent).join("/"))
    }
}

}
