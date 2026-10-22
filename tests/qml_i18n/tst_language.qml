import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"
import "../../build/all/app/install/qml" as Built
Built.Main {
    id: app
    width: 360; height: 720
    QtObject {
        id: fake
        function setHandler(name, handler) {}
        function call(method, args, callback) {
            if (method === 'main.list_directory') callback({success:true,items:[]})
        }
    }
    QtObject { id: exporter; property bool exportBusy:false }
    Component { id: browserFactory; BrowserPage { backend:fake; exportController:exporter } }
    Component { id: editorFactory; TextEditorPage { backend:fake; session:({name:'Grüße.md',token:'',text:''}) } }
    TestCase {
        name: 'SystemLanguage'
        when: windowShown && app.backendReady
        property bool german: Qt.locale().name.indexOf('de') === 0
        function test_login_uses_system_language() {
            compare(findChild(app,'loginUsername').placeholderText, german ? 'Benutzername' : 'Username')
            compare(findChild(app,'loginPassword').placeholderText, german ? 'Passwort' : 'Password')
            compare(findChild(app,'loginConnect').text, german ? 'Verbinden' : 'Connect')
            compare(findChild(app,'loginDelete').text, german ? 'Gespeicherte Verbindung löschen' : 'Delete saved connection settings')
        }
        function test_dialog_actions_and_placeholder_substitution() {
            var page=browserFactory.createObject(app,{width:360,height:720})
            page.openFolderDialog()
            var dialog=page.folderDialog
            verify(dialog !== null)
            compare(dialog.title, german ? 'Neuer Ordner' : 'New folder')
            dialog.hide(); wait(200)
            page.selectionMode=true
            page.selectedKeys=['one','two']
            compare(i18n.tr('%1 files selected').arg(2),german ? 'Ausgewählte Dateien: 2' : '2 files selected')
            page.destroy()
        }
        function test_editor_actions_and_document_name_not_translated() {
            var page=editorFactory.createObject(app,{width:360,height:720})
            compare(page.header.title,'Grüße.md')
            var actions=page.header.trailingActionBar.actions
            compare(actions[0].text,german ? 'Auf dem Server speichern' : 'Save on server')
            compare(actions[1].text,german ? 'Unter neuem Namen speichern…' : 'Save under a new name…')
            page.destroy()
        }
        function test_narrow_login_and_screenshot() {
            app.width=360
            var button=findChild(app,'loginDelete')
            verify(button.width <= app.width - units.gu(4), 'Login button exceeds available width')
            wait(150)
            grabImage(app).save(decodeURIComponent(Qt.resolvedUrl('../../build/i18n-' + Qt.locale().name + '-login.png').toString().replace(/^file:\/\//, '')))
        }
        function test_python_errors_match_ui_language() {
            var finished=false
            var backend=findChild(app,'pythonBackend')
            backend.call('main.create_directory',['/','..'],function(result) {
                verify(!result.success)
                compare(result.message,german ? 'Der Ordnername, der übergeordnete Pfad oder die Serverantwort ist ungültig.' : 'Invalid folder name, parent path or server response.')
                finished=true
            })
            tryVerify(function(){return finished},5000)
        }
        function test_selection_buttons_fit_phone_and_tablet() {
            var widths=[320,900]
            for(var i=0;i<widths.length;i++) {
                var page=browserFactory.createObject(app,{width:widths[i],height:720,selectionMode:true})
                wait(50)
                var flows=[findChild(page,'selectAllFiles').parent,findChild(page,'startSelectedDownloads').parent]
                for(var f=0;f<flows.length;f++) {
                    for(var c=0;c<flows[f].children.length;c++) {
                        var button=flows[f].children[c]
                        if(button.visible && button.text !== undefined)
                            verify(button.x+button.width <= flows[f].width+1, 'Selection button exceeds width')
                    }
                }
                page.destroy()
            }
        }
        function test_unknown_message_falls_back_to_english() {
            compare(i18n.tr('Future untranslated message'),'Future untranslated message')
        }
    }
}
