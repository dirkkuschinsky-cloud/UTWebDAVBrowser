.pragma library

function toggle(selected, key) {
    if (!key) return selected.slice()
    var copy = selected.slice()
    var index = copy.indexOf(key)
    if (index < 0) copy.push(key)
    else copy.splice(index, 1)
    return copy
}

function selectedPaths(entries, selected) {
    var seen = [], paths = []
    for (var i = 0; i < entries.length; i++) {
        var item = entries[i]
        if (!item.isDirectory && item.selectKey && selected.indexOf(item.selectKey) >= 0
                && seen.indexOf(item.selectKey) < 0) {
            seen.push(item.selectKey)
            paths.push(item.path)
        }
    }
    return paths
}

function allKeys(entries) {
    var keys = []
    for (var i = 0; i < entries.length; i++)
        if (!entries[i].isDirectory && entries[i].selectKey && keys.indexOf(entries[i].selectKey) < 0)
            keys.push(entries[i].selectKey)
    return keys
}

function acceptSnapshot(jobId, seq, snapshot) {
    if (!snapshot || !snapshot.success || snapshot.jobId !== jobId || snapshot.seq <= seq) return false
    var ids = []
    for (var i = 0; i < snapshot.files.length; i++) {
        var id = snapshot.files[i].fileId
        if (!id || ids.indexOf(id) >= 0) return false
        ids.push(id)
    }
    return !snapshot.currentId || ids.indexOf(snapshot.currentId) >= 0
}

function counts(files) {
    var result = {succeeded: 0, failed: 0, cancelled: 0, processed: 0}
    for (var i = 0; i < files.length; i++) {
        var state = files[i].state
        if (state === "succeeded" || state === "failed" || state === "cancelled") result[state]++
        if (state === "succeeded" || state === "failed") result.processed++
    }
    return result
}

function currentFile(files, id) {
    for (var i = 0; i < files.length; i++)
        if (files[i].fileId === id) return files[i]
    return null
}

function progress(files, currentId) {
    if (!files.length) return 0
    var done = counts(files).processed
    var current = currentFile(files, currentId)
    var fraction = current && current.state === "running" && current.total > 0
        ? Math.min(0.99, current.received / current.total) : 0
    return Math.min(1, (done + fraction) / files.length)
}
