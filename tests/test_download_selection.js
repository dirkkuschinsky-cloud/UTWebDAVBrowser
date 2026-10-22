const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(__dirname + '/../qml/DownloadSelection.js', 'utf8').replace(/^\.pragma library\s*/, '');
const ctx = vm.createContext({}); vm.runInContext(source, ctx);
const plain = value => JSON.parse(JSON.stringify(value));
const entries = [
    {path: '/dav/a', selectKey: 'one', isDirectory: false},
    {path: '/dav/%61', selectKey: 'one', isDirectory: false},
    {path: '/dav/b', selectKey: 'two', isDirectory: false},
    {path: '/dav/folder/', selectKey: 'folder', isDirectory: true},
    {path: 'https://outside.org/file', selectKey: '', isDirectory: false}
];
assert.deepStrictEqual(plain(ctx.allKeys(entries)), ['one', 'two']);
assert.deepStrictEqual(plain(ctx.selectedPaths(entries, ['one', 'two', 'folder', ''])), ['/dav/a', '/dav/b']);
assert.deepStrictEqual(plain(ctx.toggle(['one'], 'one')), []);
assert.deepStrictEqual(plain(ctx.toggle(['one'], 'two')), ['one', 'two']);
assert.deepStrictEqual(plain(ctx.toggle([], '')), []);
const files = [
    {fileId: '1', state: 'succeeded', received: 3, total: 3},
    {fileId: '2', state: 'running', received: 50, total: 100},
    {fileId: '3', state: 'queued', received: 0, total: null}
];
assert.equal(ctx.progress(files, '2'), 0.5);
files[1].total = null;
assert.equal(ctx.progress(files, '2'), 1 / 3); // Count processed files; never invent unknown byte percentages.
files[1].state = 'failed'; files[2].state = 'cancelled';
assert.deepStrictEqual(plain(ctx.counts(files)), {succeeded: 1, failed: 1, cancelled: 1, processed: 2});
assert.equal(ctx.progress(files, ''), 2 / 3);
const snapshot = {success: true, jobId: 'new', seq: 10, currentId: '2', files};
assert(ctx.acceptSnapshot('new', 9, snapshot));
assert(!ctx.acceptSnapshot('old', 9, snapshot));
assert(!ctx.acceptSnapshot('new', 10, snapshot));
assert(!ctx.acceptSnapshot('new', 9, {...snapshot, currentId: 'stale-file'}));
assert(!ctx.acceptSnapshot('new', 9, {...snapshot, files: [files[0], files[0]]}));
console.log('PASS: batch selection, identity deduplication, unknown sizes, aggregate progress, cancellation counts and stale job/file IDs.');
