// Run with Node.js; exercise the actual QML queue functions without Content Hub.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(require('path').join(__dirname, '../qml/BrowserPage.qml'), 'utf8');
const functions = source.slice(source.indexOf('    function uploadNext()'), source.indexOf('    function loadDirectory'));
const context = vm.createContext({
    uploadBusy: false, selectingFiles: true, transferHandled: false,
    uploadDestination: '/custom/dav/B%C3%BCro/', currentPath: '/custom/dav/B%C3%BCro/',
    uploadQueue: [], uploadErrors: '', uploadMessage: '', uploadIndex: 0,
    uploadSucceeded: 0, uploadName: '', uploadFraction: 0, awaitingConfirmation: false,
    i18n: {tr: text => text}, console,
    activeTransfer: {items: [
        {url: 'file:///cache/Gr%C3%BC%C3%9Fe%20%25.txt', name: ''},
        {url: 'file:///cache/fail.txt', name: 'fail.txt'},
        {url: 'file:///cache/last.txt', name: 'last.txt'}
    ]}
});
vm.runInContext('String.prototype.arg = function(value) { return this.replace(/%[123]/, value); };', context);
vm.runInContext(functions, context);
let pending;
const calls = [];
let refreshes = 0;
context.backend = {call(method, args, callback) {
    assert(!pending, 'Only one upload may be active');
    calls.push(args);
    pending = callback;
}};
context.loadDirectory = () => refreshes++;
context.receiveFiles();
assert.equal(calls.length, 1);
assert.equal(calls[0][0], '/cache/Grüße %.txt');
assert.equal(calls[0][1], '/custom/dav/B%C3%BCro/Gr%C3%BC%C3%9Fe%20%25.txt');
context.receiveFiles();
assert.equal(calls.length, 1, 'Duplicate Charged notification must not repeat uploads');
for (const result of [{success:true}, {success:false, status:403, message:'Permission denied'}, {success:true}]) {
    const callback = pending;
    pending = null;
    callback(result);
}
assert.equal(calls.length, 3);
assert.equal(refreshes, 1);
assert.equal(context.uploadBusy, false);
assert.equal(context.uploadSucceeded, 2);
assert(context.uploadErrors.includes('fail.txt: Permission denied (HTTP 403)'));
assert(context.uploadMessage.includes('2 of 3'));
console.log('Upload queue: sequential uploads, Unicode, partial failure and duplicate events passed.');

// Invalid source URLs must show a fixed, translatable message, not a raw URI error.
context.transferHandled = false;
context.activeTransfer = {items: [{url:'file:///cache/%GG-SYNTHETIC_SECRET', name:''}]};
context.i18n = {tr: text => text === 'The selected file could not be prepared. Choose it again.'
    ? 'Die ausgewählte Datei konnte nicht vorbereitet werden. Wähle sie erneut aus.' : text};
context.receiveFiles();
assert.equal(calls.length, 3);
assert(context.uploadErrors.includes('Die ausgewählte Datei'));
assert(!context.uploadErrors.includes('SYNTHETIC_SECRET'));
assert(!context.uploadErrors.includes('URIError'));
console.log('Upload selection: fixed localized errors passed.');
