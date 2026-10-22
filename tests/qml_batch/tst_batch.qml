import QtQuick 2.7
import QtTest 1.2
import Lomiri.Components 1.3
import "../../qml"

MainView {
    id: window
    width: 400; height: 850
    QtObject {
        id: fake
        property int prepares: 0
        property int starts: 0
        property int cancels: 0
        property int discards: 0
        property int lists: 0
        property bool deferPrepare: false
        property var pendingPrepare: null
        property var received: []
        property var snapshot: ({})
        function setHandler(name, callback) {}
        function call(method, args, callback) {
            if (method === 'main.list_directory') {
                lists++
                callback({success: true, items: [
                    {name:'Grüße %2F.txt', path:'/dav/parent/a', isDirectory:false, selectKey:'one', size:'10', displaySize:'10 B', contentType:'text/plain', lastModified:''},
                    {name:'Other', path:'/dav/parent/b', isDirectory:false, selectKey:'two', size:'', displaySize:'', contentType:'', lastModified:''},
                    {name:'Folder', path:'/dav/parent/folder/', isDirectory:true, selectKey:'bad-dir', size:'', displaySize:'', contentType:'', lastModified:''},
                    {name:'Unsafe', path:'https://other.org/file', isDirectory:false, selectKey:'', size:'', displaySize:'', contentType:'', lastModified:''}
                ]})
            } else if (method === 'main.prepare_download_job') {
                prepares++; received = args
                if (deferPrepare) pendingPrepare = callback
                else callback({success:true, jobId:'job-' + prepares})
            } else if (method === 'main.start_download_job') { starts++; callback({success:true}) }
            else if (method === 'main.download_job_status') callback(snapshot)
            else if (method === 'main.cancel_download_job') { cancels++; callback({success:true}) }
            else if (method === 'main.discard_download_job') { discards++; callback({success:true}) }
        }
    }
    QtObject {
        id: exporter
        property bool exportBusy: false
        property var saved: []
        signal progress(var received, var total)
        function saveMany(infos) { saved = infos }
    }
    BatchDownloads { id: batch; backend:fake; exportController:exporter }
    BrowserPage { id: page; anchors.fill:parent; backend:fake; exportController:exporter; batchController:batch }
    TestCase {
        name:'BatchDownloads'
        when:windowShown
        function hidePicker(item) {
            if (item.z === 100 && String(item).indexOf('Rectangle') !== -1) item.visible = false
            var children = item.children || []
            for (var i=0;i<children.length;i++) hidePicker(children[i])
        }
        function init() {
            batch.generation++; batch.state='idle'; batch.jobId=''; batch.files=[]; batch.currentId=''
            batch.lastSeq=-1; batch.pollPending=false; batch.cancelRequested=false; batch.message=''
            exporter.exportBusy=false; exporter.saved=[]
            fake.prepares=0; fake.starts=0; fake.cancels=0; fake.discards=0; fake.lists=0
            fake.deferPrepare=false; fake.snapshot={success:false}
            page.loadDirectory('/dav/parent/')
            hidePicker(page)
            wait(100)
        }
        function row(name) {
            var children=findChild(page,'webdavFileList').contentItem.children
            for (var i=0;i<children.length;i++)
                if (children[i].objectName==='webdavFileRow' && children[i].remoteName===name) return children[i]
            fail('Missing row '+name)
        }
        function choose() {
            page.selectionMode=true
            page.selectAllFiles()
            page.startSelectedDownloads()
            compare(fake.prepares,1); compare(fake.starts,1)
        }
        function status(state, seq) {
            return {success:true, jobId:batch.jobId, seq:seq, state:state, currentId:state==='finished'?'':'f2', files:[
                {fileId:'f1', state:'succeeded', received:10, total:10, name:'first', info:{cacheRef:'original-one'}},
                {fileId:'f2', state:state==='finished'?'failed':'running', received:20, total:100, name:'second', message:state==='finished'?'Network error':'', info:null}
            ]}
        }
        function test_checkbox_all_and_directory_exclusion() {
            page.selectionMode=true
            wait(50)
            var file=row('Grüße %2F.txt')
            var box=findChild(file,'fileSelectionBox')
            verify(box.visible)
            mouseClick(box)
            compare(page.selectedKeys.length,1)
            verify(box.checked)
            mouseClick(file,file.width-40,file.height/2)
            compare(page.selectedKeys.length,0)
            verify(!findChild(row('Folder'),'fileSelectionBox').visible)
            verify(!findChild(row('Unsafe'),'fileSelectionBox').visible)
            mouseClick(row('Folder'),150,25)
            compare(page.currentPath,'/dav/parent/')
            page.selectAllFiles()
            compare(page.selectedKeys.length,2)
            verify(!file.swipeEnabled)
        }
        function test_reset_and_leave_selection() {
            page.selectionMode=true;page.selectAllFiles()
            page.loadDirectory('/dav/other/')
            compare(page.selectedKeys.length,0);verify(!page.selectionMode)
            page.selectionMode=true;page.selectAllFiles()
            findChild(page,'selectFilesAction').trigger(null)
            compare(page.selectedKeys.length,0);verify(!page.selectionMode)
            compare(fake.prepares,0)
        }
        function test_start_deduplication_and_busy_navigation_guard() {
            choose()
            compare(fake.received[0],'/dav/parent/')
            compare(fake.received[1].length,2)
            verify(!page.selectionMode);verify(page.transferBusy)
            page.loadDirectory('/dav/other/')
            compare(page.currentPath,'/dav/parent/')
            batch.begin('/dav/parent/',['/dav/parent/a'])
            compare(fake.prepares,1)
            verify(!findChild(page,'newFolderAction').enabled)
            verify(!findChild(page,'refreshAction').enabled)
        }
        function test_cancel_visible_before_prepare_returns() {
            fake.deferPrepare=true
            page.selectionMode=true;page.selectAllFiles();page.startSelectedDownloads()
            batch.cancel()
            compare(batch.state,'cancelling');verify(batch.cancelRequested)
            fake.pendingPrepare({success:true,jobId:'prepared'})
            compare(fake.starts,0);compare(fake.cancels,1)
            batch.applySnapshot({success:true,jobId:'prepared',seq:1,state:'finished',currentId:'',files:[{fileId:'f1',state:'cancelled',name:'first'}]})
            verify(!batch.busy);compare(batch.counts.cancelled,1)
        }
        function test_progress_unknown_sizes_and_stale_snapshots() {
            choose()
            batch.applySnapshot(status('running',2))
            compare(batch.position,2);compare(batch.counts.succeeded,1)
            compare(batch.fraction,0.6)
            var unknown=status('running',3);unknown.files[1].total=null
            batch.applySnapshot(unknown)
            compare(batch.current.total,null);compare(batch.fraction,0.5)
            var old=status('finished',1)
            batch.applySnapshot(old);verify(batch.busy)
            old.seq=99;old.jobId='old-job'
            batch.applySnapshot(old);verify(batch.busy)
            old=status('finished',4);old.currentId='stale-file'
            batch.applySnapshot(old);verify(batch.busy)
            batch.cancel();compare(batch.state,'cancelling')
            batch.applySnapshot(status('running',4));compare(batch.state,'cancelling')
        }
        function test_summary_cache_export_and_explicit_discard() {
            choose();batch.applySnapshot(status('finished',5))
            compare(batch.counts.succeeded,1);compare(batch.counts.failed,1)
            verify(!batch.busy);verify(page.transferBusy)
            batch.save();compare(exporter.saved.length,1)
            compare(exporter.saved[0].cacheRef,'original-one')
            exporter.exportBusy=true;batch.clear();compare(fake.discards,0)
            exporter.exportBusy=false;batch.clear();compare(fake.discards,1)
            verify(!batch.present);verify(!page.transferBusy)
        }
        function test_tablet_layout() {
            window.width=1000;window.height=700
            choose();batch.applySnapshot(status('running',2))
            verify(findChild(page,'cancelDownloadJob').visible)
            verify(findChild(page,'cancelDownloadJob').width>0)
            window.width=400;window.height=850
        }
    }
}
