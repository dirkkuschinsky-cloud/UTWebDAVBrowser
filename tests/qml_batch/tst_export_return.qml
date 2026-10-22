import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import Lomiri.Content 1.3
import "../../qml"
MainView {
    width: 400; height: 800
    QtObject {
        id: fake
        property var released: []
        property int acquired: 0
        function setHandler(name, callback) {}
        function call(method,args,callback) {
            if (method === 'main.acquire_download' || method === 'main.acquire_batch_exports') {
                acquired++
                var files=[{cacheRef:'export-'+acquired,fileName:'test.md',localUrl:'file:///cache/test.md'}]
                if(method === 'main.acquire_batch_exports') files.push({cacheRef:'second-'+acquired,fileName:'second.txt',localUrl:'file:///cache/second.txt'})
                callback(method === 'main.acquire_download' ? {success:true,cacheRef:files[0].cacheRef,fileName:files[0].fileName,localUrl:files[0].localUrl} : {success:true,files:files})
            } else if(method === 'main.release_download') { released=released.concat(args[0]);callback({success:true}) }
        }
    }
    Component {
        id: transferComponent
        QtObject {
            property int state: ContentTransfer.Created
            property var items: []
            property int finalizations: 0
            function finalize() { finalizations++;state=ContentTransfer.Finalized }
        }
    }
    Component {
        id: unconfirmedComponent
        QtObject {
            property int serverState: ContentTransfer.Charged
            readonly property int state: serverState
            property var items: []
            property int finalizations: 0
            function finalize() { finalizations++;serverState=ContentTransfer.Finalized }
        }
    }
    ExportController { id: controller; anchors.fill:parent; backend:fake }
    TestCase {
        name:'ExportReturn'
        when:windowShown
        property var transfers: []
        function init() { fake.released=[];fake.acquired=0;controller.downloadMessage='' }
        function cleanup() {
            if(controller.exportBusy) controller.returnToApp()
            for(var i=0;i<transfers.length;i++) {
                if(transfers[i].hasOwnProperty('serverState')) transfers[i].serverState=ContentTransfer.Finalized
                else transfers[i].state=ContentTransfer.Finalized
            }
            tryCompare(controller,'retainedExportCount',0)
            for(i=0;i<transfers.length;i++) transfers[i].destroy()
            transfers=[]
        }
        function start(many) {
            if(many) controller.saveMany([{cacheRef:'original1'},{cacheRef:'original2'}])
            else controller.save({fileName:'test.md',remotePath:'/dav/test.md'},false)
            var transfer=transferComponent.createObject(controller)
            transfers=transfers.concat([transfer])
            controller.startExport({selectionType:0,request:function(){return transfer}})
            transfer.state=ContentTransfer.InProgress
            return transfer
        }
        function test_collected_return_retains_files_and_late_finish_isolated() {
            var old=start(false)
            old.state=ContentTransfer.Collected
            verify(findChild(controller,'returnFromExport').visible)
            verify(!findChild(controller,'cancelActiveExport').visible)
            findChild(controller,'returnFromExport').clicked()
            verify(!controller.exportBusy)
            compare(controller.downloadMessage,'')
            compare(controller.retainedExportCount,1)
            compare(fake.released.length,0)
            compare(old.finalizations,0)
            var current=start(false)
            old.state=ContentTransfer.Finalized
            compare(fake.released.length,1)
            compare(fake.released[0],'export-1')
            compare(controller.exportTransfer,current)
            verify(controller.exportBusy)
            compare(controller.pendingExport.cacheRef,'export-2')
            current.state=ContentTransfer.Finalized
            compare(fake.released.length,2)
            old.stateChanged() // stale duplicate notification is harmless
            compare(fake.released.length,2)
        }
        function test_batch_return_keeps_both_copies_until_aborted() {
            var transfer=start(true)
            transfer.state=ContentTransfer.Collected
            verify(controller.returnToApp())
            compare(fake.released.length,0)
            compare(transfer.finalizations,0)
            wait(100)
            compare(fake.released.length,0)
            transfer.state=ContentTransfer.Aborted
            compare(fake.released.length,2)
            compare(transfer.finalizations,1)
        }
        function test_cancel_before_collection_and_export_again() {
            var transfer=start(false)
            findChild(controller,'cancelActiveExport').clicked()
            verify(!controller.exportBusy)
            compare(fake.released.length,1)
            compare(transfer.finalizations,1)
            var next=start(false)
            verify(controller.exportBusy)
            next.state=ContentTransfer.Finalized
        }
        function test_unconfirmed_abort_never_finalizes_or_releases() {
            controller.save({fileName:'test.md',remotePath:'/dav/test.md'},false)
            var transfer=unconfirmedComponent.createObject(controller)
            transfers=transfers.concat([transfer])
            controller.startExport({selectionType:0,request:function(){return transfer}})
            controller.cancelActiveExport()
            verify(!controller.exportBusy)
            compare(controller.retainedExportCount,1)
            compare(fake.released.length,0)
            compare(transfer.finalizations,0)
            transfer.serverState=ContentTransfer.Finalized
            compare(fake.released.length,1)
        }
        function test_charge_waits_for_in_progress() {
            controller.save({fileName:'test.md',remotePath:'/dav/test.md'},false)
            var transfer=transferComponent.createObject(controller,{state:ContentTransfer.Initiated})
            transfers=transfers.concat([transfer])
            controller.startExport({selectionType:0,request:function(){return transfer}})
            compare(transfer.state,ContentTransfer.Initiated)
            verify(!controller.exportCharged)
            transfer.state=ContentTransfer.InProgress
            compare(transfer.state,ContentTransfer.Charged)
            compare(transfer.items.length,1)
            transfer.state=ContentTransfer.Finalized
        }
        function test_finish_cannot_force_collected_cleanup() {
            var transfer=start(false)
            transfer.state=ContentTransfer.Collected
            controller.finishExport('not finished')
            compare(transfer.finalizations,0)
            compare(fake.released.length,0)
            verify(controller.exportBusy)
            verify(!controller.exportFinishing)
            verify(controller.returnToApp())
        }
    }
}
