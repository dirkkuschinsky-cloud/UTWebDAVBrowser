import QtQuick 2.7
import Lomiri.Components 1.3

Page {
    id: imageViewer

    property var downloadInfo: null
    property bool saveBusy: false
    signal saveRequested()

    property string fileName: ""
    property string imageSource: ""

    header: PageHeader {
        title: fileName
        trailingActionBar.actions: [
            Action {
                iconName: "save"
                text: i18n.tr("Save…")
                enabled: !imageViewer.saveBusy && imageViewer.downloadInfo !== null
                onTriggered: imageViewer.saveRequested()
            }
        ]
    }

    Flickable {
        anchors.fill: parent

        Image {
            id: image

            anchors.centerIn: parent
            fillMode: Image.PreserveAspectFit

            width: parent.width
            height: parent.height

            source: imageSource
        }
    }
}
