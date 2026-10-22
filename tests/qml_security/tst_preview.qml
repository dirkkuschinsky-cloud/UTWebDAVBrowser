import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"
MainView {
    width: 400; height: 800
    TextViewerPage { id: viewer; anchors.fill: parent }
    TestCase {
        name: "PlainTextPreviewSecurity"
        when: windowShown
        function test_markup_is_literal_data() {
            var label=findChild(viewer, "textPreviewContent")
            var contents=['<b>Grüße</b>', '<img src="https://invalid.example/image">',
                '<a href="file:///private">link</a>', '# Markdown\n**literal** &amp; %2F']
            for(var i=0;i<contents.length;i++) {
                viewer.fileContent=contents[i]
                compare(label.textFormat, Text.PlainText)
                compare(label.text, contents[i])
            }
        }
        function test_preview_export_action_keeps_original_cache_reference() {
            var reference={cacheRef:'original-bytes', localFile:'/cache/original.md'}
            viewer.downloadInfo=reference
            var calls=0
            function saved() { calls++; compare(viewer.downloadInfo.cacheRef,'original-bytes') }
            viewer.saveRequested.connect(saved)
            viewer.header.trailingActionBar.actions[0].trigger(null)
            compare(calls,1)
            viewer.saveRequested.disconnect(saved)
        }
    }
}
