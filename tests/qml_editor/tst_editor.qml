import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"
MainView {
    id: appWindow
    width: 400
    height: 800
    QtObject {
        id: fake
        property int saves: 0
        property int closes: 0
        property var pending: null
        property var received: []
        function call(method, args, callback) {
            if (method === "main.save_editor") { saves++; received = args; pending = callback }
            if (method === "main.close_editor") { closes++; callback({success:true}) }
        }
    }
    PageStack { id: stack; anchors.fill: parent }
    Component { id: component; TextEditorPage { backend: fake } }
    TestCase {
        name: "TextEditor"
        when: windowShown
        property var page: null
        property int closed: 0
        property int saved: 0
        function init() {
            fake.saves = 0; closed = 0; saved = 0
            page = component.createObject(appWindow, {width:appWindow.width, height:appWindow.height,
                session:{token:'session', name:'Grüße.txt', text:'original\n', canOverwrite:true}})
            stack.push(page)
            page.closeRequested.connect(function() { closed++ })
            page.saved.connect(function() { saved++ })
            wait(100)
        }
        function cleanup() {
            if (page.closeDialog) findChild(page.closeDialog, 'continueEditing').clicked()
            if (page.nameDialog) { page.nameDialog.hide(); wait(100) }
            stack.pop(); page.destroy(); wait(100)
        }
        function input() { return findChild(page, 'editorText') }
        function test_header_icons_accessibility_and_actions() {
            var save = page.header.trailingActionBar.actions[0]
            var saveAs = page.header.trailingActionBar.actions[1]
            verify(save.iconSource.toString().indexOf('editor-save.svg') !== -1)
            compare(saveAs.iconName, 'add')
            var button=findChild(page,'saveEditorAction_button')
            var plus=findChild(page,'saveEditorAsAction_button')
            verify(button !== null && plus !== null)
            compare(button.Accessible.name, save.text)
            compare(plus.Accessible.name, saveAs.text)
            plus.pressAndHold()
            compare(page.actionHint, saveAs.text)
            compare(fake.saves,0)
            saveAs.trigger(null)
            verify(page.nameDialog !== null)
            compare(fake.saves,0)
            page.nameDialog.hide(); wait(100)
            input().text = 'changed'
            save.trigger(null)
            compare(fake.saves,1)
            fake.pending({success:true,name:'Grüße.txt',canOverwrite:false})
            verify(!save.enabled)
            verify(saveAs.enabled)
        }
        function test_long_press_only_shows_hint_no_put() {
            var button=findChild(page,'saveEditorAction_button')
            input().text='changed'
            mousePress(button,button.width/2,button.height/2,Qt.LeftButton)
            wait(1100)
            mouseRelease(button,button.width/2,button.height/2,Qt.LeftButton)
            compare(page.actionHint,page.header.trailingActionBar.actions[0].text)
            compare(fake.saves,0)
            verify(page.dirty)
        }
        function test_save_double_and_repeat() {
            compare(input().text, 'original\n')
            input().text = 'Grüße\n'
            verify(page.dirty)
            page.save(''); page.save('')
            compare(fake.saves, 1)
            verify(page.busy)
            page.requestClose(); compare(closed, 0)
            compare(fake.received[1], 'Grüße\n')
            fake.pending({success:true, name:'Grüße.txt', canOverwrite:true})
            verify(!page.dirty)
            compare(saved, 1)
            input().text = 'second'
            page.save('')
            compare(fake.saves, 2)
            fake.pending({success:true, name:'Grüße.txt', canOverwrite:false})
            verify(!page.writable)
        }
        function test_specific_messages_preserve_text_and_navigation_guard() {
            var messages = [
                'The file changed on the server. Reload or save under a new name.',
                'The file or path could not be checked safely. Reload before saving.',
                'The file exceeds the editor limit of 256 KiB.',
                'This text is not valid UTF-8.',
                'This text format is not supported. Use UTF-8 with consistent line endings.',
                'The connection failed. Check the network.',
                'Saving could not be confirmed. Check the server before trying again.'
            ]
            input().text = 'UNSAVED Grüße <b>literal</b>'
            for (var i = 0; i < messages.length; i++) {
                page.save('copy' + i + '.md')
                fake.pending({success:false, message:messages[i]})
                compare(findChild(page,'editorMessage').text, messages[i])
                compare(findChild(page,'editorMessage').textFormat, Text.PlainText)
                compare(input().text,'UNSAVED Grüße <b>literal</b>')
                verify(page.dirty)
                verify(!page.writable)
                page.requestClose()
                verify(page.closeDialog !== null)
                findChild(page.closeDialog,'continueEditing').clicked()
            }
            page.saveAs()
            page.save('existing.md')
            var conflict='A file with this name already exists. Choose another name.'
            fake.pending({success:false, message:conflict})
            compare(findChild(page.nameDialog,'editorSaveAsError').text,conflict)
            compare(input().text,'UNSAVED Grüße <b>literal</b>')
            compare(closed,0)
        }
        function test_failure_keeps_text_and_save_as() {
            input().text = 'private changed text'
            page.save('')
            fake.pending({success:false, status:412, message:'Conflict'})
            compare(input().text, 'private changed text')
            verify(page.dirty)
            verify(!page.writable)
            page.save(''); compare(fake.saves, 1)
            page.save('copy.md'); compare(fake.saves, 2)
            fake.pending({success:true, name:'copy.md', canOverwrite:true})
            verify(!page.dirty)
        }
        function test_navigation_continue_discard() {
            input().text = 'changed'
            page.requestClose()
            verify(page.closeDialog !== null)
            compare(closed, 0)
            findChild(page.closeDialog, 'continueEditing').clicked()
            compare(input().text, 'changed')
            page.requestClose()
            findChild(page.closeDialog, 'discardEditor').clicked()
            compare(closed, 1)
            compare(fake.saves, 0)
        }
        function test_stack_header_back_is_guarded() {
            input().text = 'changed'
            page.header.leadingActionBar.actions[0].trigger(null)
            compare(stack.currentPage, page)
            verify(page.closeDialog !== null)
            compare(closed, 0)
        }
        function test_keyboard_back_and_escape() {
            input().text = 'changed'
            input().forceActiveFocus()
            keyClick(Qt.Key_Escape)
            verify(page.closeDialog !== null)
            compare(closed, 0)
            findChild(page.closeDialog, 'continueEditing').clicked()
            input().forceActiveFocus()
            keyClick(Qt.Key_Back)
            verify(page.closeDialog !== null)
            compare(closed, 0)
            compare(fake.saves, 0)
        }
        function test_clean_close_and_tablet_plain_text() {
            page.requestClose(); compare(closed, 1)
            page.width = 1000; page.height = 700
            input().text = '<b>literal</b>'
            compare(input().textFormat, TextEdit.PlainText)
            verify(input().width > 0)
            compare(fake.saves, 0)
        }
    }
}
