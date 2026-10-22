import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import Lomiri.Content 1.3
import "../../qml"

MainView {
    width:400;height:800
    QtObject {
        id:fake
        property var released: []
        property bool fail: false
        function setHandler(name, callback) {}
        function call(method,args,callback) {
            if(method==='main.acquire_batch_exports') {
                if(fail) callback({success:false,message:'No storage'})
                else callback({success:true,files:[
                    {cacheRef:'copy1',fileName:'Grüße %2F.txt',localUrl:'file:///cache/Gr%C3%BC%C3%9Fe%20%252F.txt'},
                    {cacheRef:'copy2',fileName:'second',localUrl:'file:///cache/second'}
                ]})
            } else if(method==='main.release_download') {
                released=released.concat([args[0]]);callback({success:true})
            }
        }
    }
    QtObject {
        id:transfer
        property int state:ContentTransfer.Created
        property var items:[]
        property int finalizations:0
        function finalize(){finalizations++;state=ContentTransfer.Finalized}
    }
    ExportController{id:controller;anchors.fill:parent;backend:fake}
    TestCase {
        name:'MultipleExport'
        when:windowShown
        function init(){
            controller.exportTransfer=null;transfer.state=ContentTransfer.Created;transfer.items=[]
            transfer.finalizations=0;fake.released=[];fake.fail=false
            controller.exportBusy=false;controller.exportFinishing=false;controller.pendingExport=null
            controller.pendingExports=[];controller.exportItems=[];controller.exportCollected=false
            controller.destinationPickerVisible=false;controller.downloadMessage=''
        }
        function prepare(){controller.saveMany([{cacheRef:'original1'},{cacheRef:'original2'}]);verify(controller.destinationPickerVisible)}
        function test_multiple_items_lifetime_and_finalized(){
            prepare()
            var peer={selectionType:ContentTransfer.Single,request:function(){return transfer}}
            controller.startExport(peer)
            compare(peer.selectionType,ContentTransfer.Multiple)
            transfer.state=ContentTransfer.InProgress
            compare(transfer.state,ContentTransfer.Charged);compare(transfer.items.length,2)
            compare(transfer.items[0].name,'Grüße %2F.txt')
            transfer.state=ContentTransfer.Collected
            compare(fake.released.length,0);verify(controller.exportBusy)
            transfer.state=ContentTransfer.Finalized
            compare(fake.released.length,2);verify(!controller.exportBusy)
            compare(fake.released[0],'copy1');compare(fake.released[1],'copy2')
            controller.finishExport('duplicate');compare(fake.released.length,2)
        }
        function test_cancel_picker_then_export_again(){
            prepare();controller.finishExport('cancelled')
            compare(fake.released.length,2)
            prepare();controller.startExport({selectionType:0,request:function(){return transfer}})
            transfer.state=ContentTransfer.Aborted
            compare(fake.released.length,4)
            verify(!controller.exportBusy)
            verify(controller.downloadMessage.indexOf('Check its import results')!==-1)
        }
        function test_failed_request_and_acquisition(){
            prepare();controller.startExport({selectionType:0,request:function(){return null}})
            compare(fake.released.length,2);verify(!controller.exportBusy)
            fake.fail=true;controller.saveMany([{cacheRef:'original1'}])
            compare(fake.released.length,2);verify(!controller.exportBusy)
            compare(controller.downloadMessage,'No storage')
        }
    }
}
