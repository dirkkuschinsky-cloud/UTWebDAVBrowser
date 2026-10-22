import QtQuick 2.7
import Lomiri.Components 1.3
import io.thp.pyotherside 1.4
import "../../qml"
MainView {
    id: appWindow
    width: 400; height: 700
    PageStack { id: stack }
    Component { id: editorComponent; TextEditorPage { backend: python } }
    Python {
        id: python
        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../../src'))
            addImportPath(Qt.resolvedUrl('..'))
            importModule('editor_smoke_backend', function() {
                call('editor_smoke_backend.setup', [], function() {
                    importModule('main', function() {
                        call('main.open_editor', ['/', '/dav/test.txt', ''], function(result) {
                            if (!result.success) { console.error('EDITOR_BRIDGE_SMOKE_FAIL: open'); Qt.quit(); return }
                            var page = stack.push(editorComponent, {session: result})
                            function find(item) {
                                if (item.objectName === 'editorText') return item
                                for (var i=0;i<item.children.length;i++) { var found=find(item.children[i]); if(found) return found }
                                return null
                            }
                            var text = find(page)
                            if (!text || text.text !== 'Grüße\n') { console.error('EDITOR_BRIDGE_SMOKE_FAIL: UTF8'); Qt.quit(); return }
                            page.saved.connect(function() {
                                if (page.dirty || !page.writable) { console.error('EDITOR_BRIDGE_SMOKE_FAIL: save'); Qt.quit(); return }
                                var token = page.session.token
                                stack.pop()
                                // FIFO barrier waits for Component.onDestruction cleanup.
                                Qt.callLater(function() {
                                    python.call('main.close_editor', [token], function() {
                                        python.call('editor_smoke_backend.verify', [], function(ok) {
                                            console.log(ok ? 'EDITOR_BRIDGE_SMOKE_PASS' : 'EDITOR_BRIDGE_SMOKE_FAIL: cleanup/bytes')
                                            Qt.quit()
                                        })
                                    })
                                })
                            })
                            text.text = 'Grüße\nNeu\n'
                            page.save('')
                            page.save('')
                        })
                    })
                })
            })
        }
        onError: { console.error('EDITOR_BRIDGE_SMOKE_FAIL: Python boundary'); Qt.quit() }
    }
    Timer { interval:10000; running:true; onTriggered: { console.error('EDITOR_BRIDGE_SMOKE_FAIL: timeout'); Qt.quit() } }
}
