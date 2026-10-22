const fs = require('fs'), vm = require('vm'), assert = require('assert');
const scope = vm.createContext({});
vm.runInContext(fs.readFileSync(require('path').join(__dirname, '../qml/FileIcons.js'), 'utf8').replace(/^\.pragma library\s*/, ''), scope);
const icon = scope.iconName;
const cases = [
    ['Ordner.pdf', true, 'application/pdf', 'folder-symbolic'],
    ['BSW', true, '', 'folder-symbolic'],
    ['Bericht.PDF', false, 'application/octet-stream', 'application-pdf-symbolic'],
    ['Grüße & <b>Welt</b>.txt', false, 'application/octet-stream', 'text-x-generic-symbolic'],
    ['Bild.JpEg', false, 'text/plain', 'image-x-generic-symbolic'],
    ['backup.TAR.GZ', false, '', 'application-x-archive-symbolic'],
    ['backup.tar.xz', false, '', 'application-x-archive-symbolic'],
    ['file.7z', false, '', 'application-x-archive-symbolic'],
    ['Brief.DOCX', false, 'application/zip', 'x-office-document-symbolic'],
    ['Tabelle.ODS', false, 'application/zip', 'x-office-spreadsheet-symbolic'],
    ['Folien.PPTX', false, 'application/zip', 'x-office-presentation-symbolic'],
    ['no-extension', false, 'Application/PDF; charset=binary', 'application-pdf-symbolic'],
    ['unknown.ext', false, 'image/png', 'image-x-generic-symbolic'],
    ['file', false, 'application/vnd.oasis.opendocument.text', 'x-office-document-symbolic'],
    ['file', false, 'application/vnd.ms-excel', 'x-office-spreadsheet-symbolic'],
    ['file', false, 'application/vnd.ms-powerpoint', 'x-office-presentation-symbolic'],
    ['file', false, 'application/x-7z-compressed', 'application-x-archive-symbolic'],
    ['file', false, 'text/plain; charset=utf-8', 'text-x-generic-symbolic'],
    ['file', false, 'text/csv', 'x-office-spreadsheet-symbolic'],
    ['.pdf', false, '', 'empty-symbolic'],
    ['name.', false, '', 'empty-symbolic'],
    ['name', false, 'application/octet-stream', 'empty-symbolic'],
    ['name.weird', false, '', 'empty-symbolic'],
    [null, false, null, 'empty-symbolic'],
    ['test.constructor', false, '', 'empty-symbolic'],
    ['test.__proto__', false, '', 'empty-symbolic'],
    ['ü'.repeat(500) + '.PNG', false, '', 'image-x-generic-symbolic']
];
for (const [name, directory, mime, expected] of cases)
    assert.equal(icon(name, directory, mime), expected, JSON.stringify({name, directory, mime}));
for (const [extensions, expected] of [
    ['jpg jpeg png gif webp bmp svg tif tiff', 'image-x-generic-symbolic'],
    ['zip tar gz tgz bz2 tbz2 xz txz 7z rar zst', 'application-x-archive-symbolic'],
    ['doc docx odt rtf', 'x-office-document-symbolic'],
    ['xls xlsx ods csv', 'x-office-spreadsheet-symbolic'],
    ['ppt pptx odp', 'x-office-presentation-symbolic']
]) for (const extension of extensions.split(' ')) {
    assert.equal(icon('file.' + extension, false, ''), expected);
    assert.equal(icon('folder.' + extension, true, ''), 'folder-symbolic');
}
console.log('PASS: file icon categories, extensions, MIME fallback, directory precedence and Unicode.');
