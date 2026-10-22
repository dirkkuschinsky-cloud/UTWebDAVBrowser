.pragma library

// Presentation only: these categories do not change preview or transfer behavior.
function iconName(fileName, isDirectory, contentType) {
    if (isDirectory) return "folder-symbolic"
    var name = String(fileName || "").toLowerCase()
    var dot = name.lastIndexOf(".")
    var extension = dot > 0 ? name.substring(dot + 1) : ""
    var icons = {
        pdf: "application-pdf-symbolic",
        txt: "text-x-generic-symbolic",
        jpg: "image-x-generic-symbolic", jpeg: "image-x-generic-symbolic",
        png: "image-x-generic-symbolic", gif: "image-x-generic-symbolic",
        webp: "image-x-generic-symbolic", bmp: "image-x-generic-symbolic",
        svg: "image-x-generic-symbolic", tif: "image-x-generic-symbolic", tiff: "image-x-generic-symbolic",
        zip: "application-x-archive-symbolic", tar: "application-x-archive-symbolic",
        gz: "application-x-archive-symbolic", tgz: "application-x-archive-symbolic",
        bz2: "application-x-archive-symbolic", tbz2: "application-x-archive-symbolic",
        xz: "application-x-archive-symbolic", txz: "application-x-archive-symbolic",
        "7z": "application-x-archive-symbolic", rar: "application-x-archive-symbolic", zst: "application-x-archive-symbolic",
        doc: "x-office-document-symbolic", docx: "x-office-document-symbolic",
        odt: "x-office-document-symbolic", rtf: "x-office-document-symbolic",
        xls: "x-office-spreadsheet-symbolic", xlsx: "x-office-spreadsheet-symbolic",
        ods: "x-office-spreadsheet-symbolic", csv: "x-office-spreadsheet-symbolic",
        ppt: "x-office-presentation-symbolic", pptx: "x-office-presentation-symbolic",
        odp: "x-office-presentation-symbolic"
    }
    if (Object.prototype.hasOwnProperty.call(icons, extension)) return icons[extension]

    var mime = String(contentType || "").split(";")[0].trim().toLowerCase()
    if (mime === "application/pdf") return "application-pdf-symbolic"
    if (mime.indexOf("image/") === 0) return "image-x-generic-symbolic"
    if (/^(application\/(zip|x-zip-compressed|x-tar|gzip|x-gzip|x-bzip2|x-xz|x-7z-compressed|vnd\.rar|x-rar-compressed|zstd))$/.test(mime))
        return "application-x-archive-symbolic"
    if (/^(application\/(msword|rtf|vnd\.openxmlformats-officedocument\.wordprocessingml\.document|vnd\.oasis\.opendocument\.text))$/.test(mime))
        return "x-office-document-symbolic"
    if (/^(text\/csv|application\/(vnd\.ms-excel|vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet|vnd\.oasis\.opendocument\.spreadsheet))$/.test(mime))
        return "x-office-spreadsheet-symbolic"
    if (/^application\/(vnd\.ms-powerpoint|vnd\.openxmlformats-officedocument\.presentationml\.presentation|vnd\.oasis\.opendocument\.presentation)$/.test(mime))
        return "x-office-presentation-symbolic"
    if (mime.indexOf("text/") === 0) return "text-x-generic-symbolic"
    return "empty-symbolic"
}
