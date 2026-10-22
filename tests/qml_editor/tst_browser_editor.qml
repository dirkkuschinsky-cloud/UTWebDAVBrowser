import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"
MainView {
    width: 400; height: 800
    QtObject {
        id: fake
        property int opens: 0
        property int lists: 0
        property string previewed: ''
        property var received: []
        property var pending: null
        function setHandler(name, handler) {}
        function call(method, args, callback) {
            if (method === 'main.open_editor') { opens++; received=args; pending=callback }
            else if (method === 'main.list_directory') {
                lists++; callback({success:true, items:[
                    {name:'test.txt',path:'/dav/Test/test.txt',isDirectory:false,size:'4',displaySize:'4 B',lastModified:'',contentType:'text/plain',selectKey:'txt'},
                    {name:'test.MD',path:'/dav/Test/test.MD',isDirectory:false,size:'4',displaySize:'4 B',lastModified:'',contentType:'text/markdown',selectKey:'md'}
                ]})
            } else if (method === 'main.read_text_file') {
                previewed=args[0]; callback({success:true,text:'text',fileName:'test',localFile:'/cache/test',localUrl:'file:///cache/test',cacheRef:'preview'})
            }
        }
    }
    QtObject {
        id: exporter
        property bool exportBusy:false
        property string path:''
        property bool toFiles:true
        signal progress(var received, var total)
        function save(info, toFileManager) { path=info.remotePath;toFiles=toFileManager }
    }
    BrowserPage { id: browser; anchors.fill:parent; backend:fake; exportController:exporter }
    TestCase {
        name: 'BrowserEditorIntegration'
        when: windowShown
        property int opened: 0
        function initTestCase() { browser.editText.connect(function(session) { opened++ }) }
        function init() {
            fake.opens=0; fake.lists=0; opened=0; fake.previewed='';exporter.path=''
            browser.currentPath='/dav/Test/'
        }
        function cleanup() {
            if (browser.editorBusy) fake.pending({success:false, message:'failed'})
            if (browser.textNameDialog) { browser.textNameDialog.hide(); wait(200) }
        }
        function row(name) {
            var children=findChild(browser,'webdavFileList').contentItem.children
            for(var i=0;i<children.length;i++) if(children[i].remoteName===name) return children[i]
            fail('Missing row')
        }
        function test_txt_md_preview_and_internal_edit() {
            browser.loadDirectory('/dav/Test/'); wait(100)
            for(var i=0;i<2;i++) {
                var name=i===0?'test.txt':'test.MD'
                var entry=row(name)
                entry.clicked()
                compare(fake.previewed,'/dav/Test/'+name)
                compare(exporter.path,'')
                var edit=entry.trailingActions.actions[3]
                verify(edit.enabled)
                edit.trigger(null)
                compare(fake.received[1],'/dav/Test/'+name)
                fake.pending({success:true,token:'editor',text:'text',canOverwrite:true})
            }
            compare(fake.opens,2)
            compare(opened,2)
        }
        function test_explicit_external_markdown_and_download_retained() {
            browser.loadDirectory('/dav/Test/'); wait(100)
            var entry=row('test.MD')
            entry.trailingActions.actions[1].trigger(null)
            compare(exporter.path,'/dav/Test/test.MD')
            verify(!exporter.toFiles)
            compare(fake.opens,0)
            entry.trailingActions.actions[0].trigger(null)
            verify(exporter.toFiles)
        }
        function test_load_blocks_navigation_and_duplicate_open() {
            browser.openEditor('/dav/Test/test.md', '')
            browser.openEditor('/dav/Test/second.txt', '')
            compare(fake.opens, 1)
            compare(fake.received[0], '/dav/Test/')
            verify(browser.transferBusy)
            browser.loadDirectory('/dav/Other/')
            compare(browser.currentPath, '/dav/Test/')
            compare(fake.lists, 0)
            fake.pending({success:true, token:'one', text:'text', canOverwrite:false})
            verify(!browser.editorBusy)
            compare(opened, 1)
        }
        function test_error_preserves_directory_no_open() {
            browser.openEditor('/dav/Test/test.txt','')
            fake.pending({success:false,message:'Invalid UTF8'})
            compare(browser.downloadMessage, 'Invalid UTF8')
            compare(opened, 0)
            compare(browser.currentPath, '/dav/Test/')
        }
        function test_new_name_dialog_and_cancel() {
            browser.newTextFile()
            verify(browser.textNameDialog !== null)
            var name=findChild(browser.textNameDialog,'newTextName')
            name.text='Grüße %2F.md'
            verify(browser.transferBusy)
            browser.loadDirectory('/dav/Other/')
            compare(browser.currentPath, '/dav/Test/')
            browser.textNameDialog.hide(); wait(200)
            compare(fake.opens, 0)
        }
    }
}
