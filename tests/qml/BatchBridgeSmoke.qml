import QtQuick 2.7
import Lomiri.Components 1.3
import io.thp.pyotherside 1.4
import "../../qml"

MainView {
    width:400;height:600
    property int ticks:0
    property bool closing:false
    property bool prepared:false
    QtObject { id:exporter; property bool exportBusy:false }
    BatchDownloads { id:batch;backend:python;exportController:exporter }
    Python {
        id:python
        Component.onCompleted:{
            addImportPath(Qt.resolvedUrl('../../src'))
            addImportPath(Qt.resolvedUrl('..'))
            importModule('batch_smoke_backend',function(){
                call('batch_smoke_backend.setup',[],function(){
                    importModule('main',function(){
                        prepared=true
                        batch.begin('/dav/test/',['/dav/test/large','/dav/test/next'])
                    })
                })
            })
        }
        onError:{console.error('BATCH_BRIDGE_SMOKE_FAIL: '+traceback);Qt.quit()}
    }
    Timer {
        interval:25;repeat:true;running:prepared
        onTriggered:{
            ticks++
            if(batch.current && batch.current.received>0 && !batch.cancelRequested) batch.cancel()
            if(batch.state==='finished' && !closing){
                closing=true
                if(batch.counts.cancelled!==2 || batch.counts.succeeded!==0){
                    console.error('BATCH_BRIDGE_SMOKE_FAIL: incorrect cancellation counts');Qt.quit();return
                }
                batch.clear()
            }
            if(closing && !batch.present){
                prepared=false
                python.call('batch_smoke_backend.cleanup',[],function(result){
                    if(result.gets===1 && result.reads<64 && result.partial===0 && result.leases===0 && ticks>3)
                        console.log('BATCH_BRIDGE_SMOKE_PASS')
                    else console.error('BATCH_BRIDGE_SMOKE_FAIL: cleanup or responsiveness')
                    Qt.quit()
                })
            }
        }
    }
    Timer {interval:10000;running:true;onTriggered:{console.error('BATCH_BRIDGE_SMOKE_FAIL: timeout');Qt.quit()}}
}
