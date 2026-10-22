import QtQuick 2.7
import "DownloadSelection.js" as Selection

Item {
    id: controller
    property var backend
    property var exportController
    property string jobId: ""
    property string state: "idle"
    property bool cancelRequested: false
    property bool pollPending: false
    property int generation: 0
    property real lastSeq: -1
    property var files: []
    property string currentId: ""
    property string message: ""
    property bool busy: state === "preparing" || state === "starting" || state === "running" || state === "cancelling"
    property bool present: state !== "idle"
    property var counts: Selection.counts(files)
    property var current: Selection.currentFile(files, currentId)
    property real fraction: Selection.progress(files, currentId)
    property int position: current ? files.indexOf(current) + 1 : 0

    function begin(parent, paths) {
        if (present || (exportController && exportController.exportBusy) || !paths.length) return
        generation++
        var request = generation
        state = "preparing"
        cancelRequested = false
        message = ""
        files = []
        currentId = ""
        lastSeq = -1
        backend.call("main.prepare_download_job", [parent, paths], function(result) {
            if (request !== generation) return
            if (!result || !result.success) {
                state = "finished"
                message = result && result.message ? result.message : i18n.tr("The download job could not be prepared.")
                return
            }
            jobId = result.jobId
            if (cancelRequested) {
                backend.call("main.cancel_download_job", [jobId], function(result) { poll() })
            } else {
                state = "starting"
                backend.call("main.start_download_job", [jobId], function(result) {
                    if (request !== generation) return
                    if (!result || !result.success) {
                        message = i18n.tr("The download job could not be started.")
                        cancel()
                    }
                    poll()
                })
            }
        })
    }

    function applySnapshot(snapshot) {
        if (!Selection.acceptSnapshot(jobId, lastSeq, snapshot)) return
        lastSeq = snapshot.seq
        files = snapshot.files
        currentId = snapshot.currentId
        state = snapshot.state === "finished" ? "finished" : cancelRequested ? "cancelling" : snapshot.state
    }

    function poll() {
        if (!jobId || pollPending) return
        pollPending = true
        var expected = jobId
        backend.call("main.download_job_status", [expected], function(result) {
            if (expected !== jobId) return
            pollPending = false
            applySnapshot(result)
        })
    }

    function cancel() {
        if (!busy || cancelRequested) return
        cancelRequested = true
        state = "cancelling" // Immediate, even while the backend is validating/reading.
        if (jobId)
            backend.call("main.cancel_download_job", [jobId], function(result) { poll() })
    }

    function save() {
        if (busy || !counts.succeeded || exportController.exportBusy) return
        var infos = []
        for (var i = 0; i < files.length; i++)
            if (files[i].state === "succeeded") infos.push(files[i].info)
        exportController.saveMany(infos)
    }

    function clear() {
        if (busy || exportController.exportBusy) return
        if (!jobId) { state = "idle"; message = ""; return }
        var expected = jobId
        backend.call("main.discard_download_job", [expected], function(result) {
            if (expected !== jobId) return
            if (!result || !result.success) {
                message = result && result.message ? result.message : i18n.tr("The download job could not be discarded.")
                return
            }
            generation++
            jobId = ""
            currentId = ""
            files = []
            pollPending = false
            lastSeq = -1
            state = "idle"
            message = result.warning || ""
        })
    }

    Timer {
        interval: 150
        running: controller.busy && controller.jobId !== ""
        repeat: true
        onTriggered: controller.poll()
    }
}
