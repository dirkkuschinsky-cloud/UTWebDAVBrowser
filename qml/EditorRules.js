function validName(name) {
    return typeof name === 'string' && name.trim().length > 0 && /\.(txt|md)$/i.test(name)
        && !/[\/\\\x00-\x1f\x7f]/.test(name)
}
function editable(name) { return /\.(txt|md)$/i.test(name) }
if (typeof module !== 'undefined') module.exports = {validName:validName, editable:editable}
