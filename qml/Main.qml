/*
 * Copyright (C) 2026  Dirk Kuschinsky
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * utwebdavbrowser is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

import QtQuick 2.7
import Lomiri.Components 1.3
import io.thp.pyotherside 1.4

MainView {
    id: root
    objectName: "mainView"
    applicationName: "utwebdavbrowser.dkuschinsky"
    automaticOrientation: true

    function releasePreview(info) {
        if (info && info.cacheRef)
            python.call("main.release_download", [info.cacheRef], function(result) {
                if (!result.success) console.log("Temporary preview cleanup failed.")
            })
    }

    function openPreview(component, properties) {
        try {
            if (pageStack.push(component, properties)) return
        } catch (error) {
            console.log("Preview could not be opened")
        }
        releasePreview(properties.downloadInfo)
        sharedExport.downloadMessage = i18n.tr("The preview could not be opened.")
    }

    ExportController {
        id: sharedExport
        objectName: "sharedExportController"
        anchors.fill: parent
        backend: python
        z: 200
    }

    BatchDownloads {
        id: batchDownloads
        backend: python
        exportController: sharedExport
    }

    property bool backendReady: false

    width: units.gu(45)
    height: units.gu(75)

PageStack {
    id: pageStack
    anchors.fill: parent

    Component.onCompleted: {
        push(loginPageComponent)
    }
}

Component {
    id: loginPageComponent

    LoginPage {
        backend: python
        backendReady: root.backendReady

        onLoginSuccessful: {
            pageStack.push(browserPageComponent)
            pageStack.currentPage.loadDirectory("/")
            if (warning) pageStack.currentPage.downloadMessage = warning
        }
    }
}

Component {
    id: browserPageComponent

    BrowserPage {
        id: browser
        onEditText: {
            try {
                var page = pageStack.push(textEditorComponent, {"session": session})
                if (!page) throw new Error("Editor unavailable")
                page.saved.connect(function() { browser.loadDirectory(browser.currentPath) })
            } catch (error) {
                python.call("main.close_editor", [session.token], function(result) {})
                browser.downloadMessage = i18n.tr("The editor could not be opened.")
            }
        }
        backend: python
        exportController: sharedExport
        batchController: batchDownloads
        onOpenTextFile: {
            root.openPreview(textViewerPageComponent, {
                "fileName": fileName,
                "fileContent": fileContent,
                "downloadInfo": downloadInfo
            })
        }

        onOpenImageFile: {
            root.openPreview(imageViewerPageComponent, {
                "fileName": fileName,
                "imageSource": imageSource,
                "downloadInfo": downloadInfo
            })
        }

        onOpenPdfFile: {
            root.openPreview(pdfViewerPageComponent, {
                "fileName": fileName,
                "filePath": filePath,
                "downloadInfo": downloadInfo
            })
        }

    }
}

Component {
    id: textEditorComponent
    TextEditorPage {
        backend: python
        onCloseRequested: pageStack.pop()
    }
}

Component {
    id: textViewerPageComponent
    TextViewerPage {
        saveBusy: sharedExport.exportBusy
        onSaveRequested: sharedExport.save(downloadInfo, true)
        Component.onDestruction: root.releasePreview(downloadInfo)
    }
}

Component {
    id: imageViewerPageComponent
    ImageViewerPage {
        saveBusy: sharedExport.exportBusy
        onSaveRequested: sharedExport.save(downloadInfo, true)
        Component.onDestruction: root.releasePreview(downloadInfo)
    }
}

Component {
    id: pdfViewerPageComponent
    PdfViewerPage {
        saveBusy: sharedExport.exportBusy
        onSaveRequested: sharedExport.save(downloadInfo, true)
        // Releasing this lease leaves the PDF's external-reader pin intact.
        Component.onDestruction: root.releasePreview(downloadInfo)
    }
}


    Python {
        id: python
        objectName: "pythonBackend"

        Component.onCompleted: {
            i18n.bindtextdomain(root.applicationName,
                decodeURIComponent(Qt.resolvedUrl("../share/locale").toString().replace(/^file:\/\//, "")))
            i18n.domain = root.applicationName
            addImportPath(Qt.resolvedUrl("../src/"))

            importModule("main", function() {
                console.log("main module imported")
                root.backendReady = true
            })
        }

        onError: {
            console.log("Backend operation failed.")
            sharedExport.downloadMessage = i18n.tr("The operation could not be completed. Restart the app if it remains busy.")
        }
    }
}
