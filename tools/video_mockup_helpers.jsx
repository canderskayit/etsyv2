
    function filterMissingStaticMockupJobs(jobs) {
        var result = [];

        for (var i = 0; i < jobs.length; i++) {
            var outFile = new File(jobs[i].outPath);
            if (!outFile.exists) {
                result.push(jobs[i]);
            }
        }

        return result;
    }

    function filterAllowedPsdFiles(files, allowedStems) {
        if (!allowedStems || allowedStems.length === 0) {
            return files;
        }
        var allowed = {};
        for (var i = 0; i < allowedStems.length; i++) {
            allowed[normalizeFilterName(allowedStems[i])] = true;
        }
        var result = [];
        for (var f = 0; f < files.length; f++) {
            var stem = getBaseNameFromPath(files[f]);
            if (allowed[normalizeFilterName(stem)]) {
                result.push(files[f]);
            }
        }
        return result;
    }

    function normalizeFilterName(value) {
        return String(value || "").replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "").toLowerCase();
    }

    function collectEtsySourceImages(folder) {
        var files = collectImageFiles(folder);
        var result = [];
        var pattern = /_2k_3x4\.(jpe?g|png)$/i;

        for (var i = 0; i < files.length; i++) {
            var name = getFileNameFromPath(files[i]).toLowerCase();
            if (pattern.test(name)) {
                result.push(files[i]);
            }
        }

        return result;
    }

    function processVideoMockups(posterFolders, videoPsdFile, forceVideoMockup) {
        var result = {
            success: 0,
            skipped: 0,
            log: []
        };

        var progress = createProgressUI(posterFolders.length);

        for (var i = 0; i < posterFolders.length; i++) {
            var posterFolder = posterFolders[i];
            progress.update(i + 1, posterFolders.length, posterFolder.name, "vertical video");

            try {
                var posterFiles = collectEtsySourceImages(posterFolder);
                if (posterFiles.length === 0) {
                    throw new Error("2K source image not found.");
                }

                var outputFile = new File(posterFolder.fsName + "/" + "vertical.mp4");
                if (!forceVideoMockup && outputFile.exists && outputFile.length > 0) {
                    result.skipped++;
                    result.log.push("[Video | " + posterFolder.name + "] Already exists, skipped.");
                    continue;
                }

                processOneVideoSimple(videoPsdFile.fsName, posterFiles[0], outputFile.fsName);
                result.success++;
            } catch (err) {
                result.skipped++;
                result.log.push("[Video | " + posterFolder.name + "] " + err.message);
            }
        }

        progress.close();
        return result;
    }

    function processOneVideoSimple(videoPsdPath, posterPath, outPath) {
        var psdFile = new File(videoPsdPath);
        var posterFile = new File(posterPath);
        var outputFile = new File(outPath);
        var doc = null;

        if (!psdFile.exists) {
            throw new Error("Video PSD not found: " + videoPsdPath);
        }
        if (!posterFile.exists) {
            throw new Error("Poster image not found: " + posterPath);
        }

        videoCloseOpenDocumentByFile(psdFile);
        doc = app.open(psdFile);

        try {
            var artworkLayers = videoCollectVisibleArtworkLayers(
                doc,
                "ARTWORK",
                []
            );
            if (artworkLayers.length === 0) {
                var fallbackArtwork = videoFindTopArtworkLayer(doc, "ARTWORK");
                if (fallbackArtwork) artworkLayers.push(fallbackArtwork);
            }
            if (artworkLayers.length === 0) {
                throw new Error("Visible ARTWORK smart object not found.");
            }

            for (var artworkIndex = 0; artworkIndex < artworkLayers.length; artworkIndex++) {
                videoReplaceTopArtwork(doc, artworkLayers[artworkIndex], posterFile);
                videoActivateDocumentById(doc.id);
            }
            app.refresh();
            try { app.purge(PurgeTarget.ALLCACHES); } catch (purgeError) {}
            videoWaitMs(500);
            videoExportMp4(outputFile);
        } finally {
            videoCloseExtraDocumentsExcept(doc);
            if (doc) {
                try {
                    doc.close(SaveOptions.DONOTSAVECHANGES);
                } catch (closeErr) {}
            }
        }
    }

    function videoFindTopArtworkLayer(doc, targetName) {
        var normalizedTarget = videoNormalizeName(targetName);
        var layers = doc.layers;

        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            try {
                if (
                    layer.typename === "ArtLayer" &&
                    layer.kind === LayerKind.SMARTOBJECT &&
                    videoNormalizeName(layer.name) === normalizedTarget
                ) {
                    return layer;
                }
            } catch (err) {}
        }

        return null;
    }

    function videoLayerIsEffectivelyVisible(layer) {
        var current = layer;
        while (current && current.typename !== "Document") {
            if (!current.visible) return false;
            current = current.parent;
        }
        return true;
    }

    function videoCollectVisibleArtworkLayers(container, targetName, results) {
        results = results || [];
        var normalizedTarget = videoNormalizeName(targetName);
        for (var i = 0; i < container.layers.length; i++) {
            var layer = container.layers[i];
            try {
                if (
                    layer.typename === "ArtLayer" &&
                    layer.kind === LayerKind.SMARTOBJECT &&
                    videoNormalizeName(layer.name) === normalizedTarget &&
                    videoLayerIsEffectivelyVisible(layer)
                ) {
                    results.push(layer);
                }
            } catch (kindErr) {}
            if (layer.typename === "LayerSet") {
                videoCollectVisibleArtworkLayers(layer, targetName, results);
            }
        }
        return results;
    }

    function videoReplaceTopArtwork(mainDoc, artworkLayer, imageFile) {
        var mainDocId = mainDoc.id;
        videoActivateDocumentById(mainDocId);
        videoUnlockLayerPath(artworkLayer, mainDoc);
        videoSelectLayerById(artworkLayer.id);

        try {
            executeAction(
                stringIDToTypeID("placedLayerEditContents"),
                new ActionDescriptor(),
                DialogModes.NO
            );
        } catch (editContentsErr) {
            var replaceDescriptor = new ActionDescriptor();
            replaceDescriptor.putPath(charIDToTypeID("null"), new File(imageFile.fsName));
            executeAction(
                stringIDToTypeID("placedLayerReplaceContents"),
                replaceDescriptor,
                DialogModes.NO
            );
            videoWaitMs(250);
            return;
        }
        videoWaitMs(350);

        var artworkDoc = app.activeDocument;
        if (!artworkDoc || artworkDoc.id === mainDocId) {
            videoActivateDocumentById(mainDocId);
            throw new Error("ARTWORK smart object ic belgesi acilamadi.");
        }

        try {
            videoActivateDocumentById(artworkDoc.id);
            var placedLayer = videoPlaceImageInDocument(artworkDoc, imageFile);
            videoFitLayerToCoverDocument(artworkDoc, placedLayer);
            videoHideAllLayersExcept(artworkDoc, placedLayer);
            artworkDoc.save();
            videoWaitMs(250);
            artworkDoc.close(SaveOptions.DONOTSAVECHANGES);
        } catch (err) {
            try {
                if (app.activeDocument && app.activeDocument.id !== mainDocId) {
                    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
                }
            } catch (cleanupErr) {}
            videoActivateDocumentById(mainDocId);
            throw err;
        }

        videoActivateDocumentById(mainDocId);
    }

    function videoUnlockLayerPath(layer, mainDoc) {
        var current = layer;
        while (current && current !== mainDoc && current.typename !== "Document") {
            try {
                current.allLocked = false;
            } catch (allLockErr) {}
            try {
                current.positionLocked = false;
            } catch (positionLockErr) {}
            try {
                current.pixelsLocked = false;
            } catch (pixelsLockErr) {}
            try {
                current.transparentPixelsLocked = false;
            } catch (transparentLockErr) {}
            current = current.parent;
        }
    }

    function videoPlaceImageInDocument(doc, imageFile) {
        videoActivateDocumentById(doc.id);

        var desc = new ActionDescriptor();
        desc.putPath(charIDToTypeID("null"), new File(imageFile.fsName));
        desc.putEnumerated(
            charIDToTypeID("FTcs"),
            charIDToTypeID("QCSt"),
            charIDToTypeID("Qcsa")
        );
        executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);
        videoWaitMs(250);

        if (!app.activeDocument || app.activeDocument.id !== doc.id) {
            throw new Error("Gorsel ARTWORK ic belgesi disinda bir yere yerlestirildi; islem iptal edildi.");
        }

        videoCommitPlacement();
        videoActivateDocumentById(doc.id);

        if (!doc.activeLayer) {
            throw new Error("ARTWORK icine gorsel yerlestirilemedi.");
        }

        try {
            doc.activeLayer.name = "ARTWORK_IMAGE";
        } catch (nameErr) {}

        return doc.activeLayer;
    }

    function videoFitLayerToCoverDocument(doc, layer) {
        videoActivateDocumentById(doc.id);
        doc.activeLayer = layer;

        var docW = doc.width.as("px");
        var docH = doc.height.as("px");
        var maxPasses = 8;

        for (var pass = 0; pass < maxPasses; pass++) {
            var b = layer.bounds;
            var left = b[0].as("px");
            var top = b[1].as("px");
            var right = b[2].as("px");
            var bottom = b[3].as("px");
            var layerW = right - left;
            var layerH = bottom - top;

            if (layerW <= 0 || layerH <= 0) {
                throw new Error("ARTWORK icindeki gorsel boyutu okunamadi.");
            }

            var scale = Math.max(docW / layerW, docH / layerH) * 100;
            if (Math.abs(scale - 100) > 0.02) {
                layer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
            }

            videoCenterLayerInDocument(doc, layer);

            b = layer.bounds;
            left = b[0].as("px");
            top = b[1].as("px");
            right = b[2].as("px");
            bottom = b[3].as("px");

            if (left <= 1 && top <= 1 && right >= docW - 1 && bottom >= docH - 1) {
                return;
            }

            layer.resize(101, 101, AnchorPosition.MIDDLECENTER);
            videoCenterLayerInDocument(doc, layer);
        }
    }

    function videoCenterLayerInDocument(doc, layer) {
        var b = layer.bounds;
        var layerW = b[2].as("px") - b[0].as("px");
        var layerH = b[3].as("px") - b[1].as("px");
        var docW = doc.width.as("px");
        var docH = doc.height.as("px");
        var dx = docW / 2 - (b[0].as("px") + layerW / 2);
        var dy = docH / 2 - (b[1].as("px") + layerH / 2);
        layer.translate(UnitValue(dx, "px"), UnitValue(dy, "px"));
    }

    function videoRemoveAllLayersExcept(doc, keepLayer) {
        videoActivateDocumentById(doc.id);
        var keepId = "";
        try {
            keepId = String(keepLayer.id);
        } catch (idErr) {}

        for (var i = doc.layers.length - 1; i >= 0; i--) {
            var layer = doc.layers[i];
            var layerId = "";
            try {
                layerId = String(layer.id);
            } catch (layerIdErr) {}

            if (layerId && keepId && layerId === keepId) {
                continue;
            }

            videoRemoveLayer(doc, layer);
        }

        doc.activeLayer = keepLayer;
    }

    function videoHideAllLayersExcept(doc, keepLayer) {
        videoActivateDocumentById(doc.id);
        var keepId = "";
        try {
            keepId = String(keepLayer.id);
        } catch (idErr) {}

        for (var i = 0; i < doc.layers.length; i++) {
            var layer = doc.layers[i];
            var layerId = "";
            try {
                layerId = String(layer.id);
            } catch (layerIdErr) {}
            try {
                layer.visible = Boolean(layerId && keepId && layerId === keepId);
            } catch (visibilityErr) {}
        }

        keepLayer.visible = true;
        doc.activeLayer = keepLayer;
    }

    function videoRemoveLayer(doc, layer) {
        videoActivateDocumentById(doc.id);
        try {
            layer.allLocked = false;
        } catch (lockErr) {}
        try {
            if (layer.isBackgroundLayer) {
                layer.isBackgroundLayer = false;
            }
        } catch (bgErr) {}
        try {
            doc.activeLayer = layer;
            layer.remove();
        } catch (removeErr) {
            try {
                videoSelectLayerById(layer.id);
                executeAction(charIDToTypeID("Dlt "), undefined, DialogModes.NO);
            } catch (deleteErr) {}
        }
    }

    function videoExportMp4(outFile) {
        if (outFile.exists) {
            try {
                outFile.remove();
            } catch (removeErr) {}
        }

        var s2t = function (s) {
            return app.stringIDToTypeID(s);
        };

        var descriptor = new ActionDescriptor();
        var videoExport = new ActionDescriptor();

        videoExport.putPath(s2t("directory"), outFile.parent);
        videoExport.putString(s2t("name"), outFile.name);
        videoExport.putString(s2t("ameFormatName"), "H.264");
        videoExport.putString(s2t("amePresetName"), "1_High Quality.epr");
        videoExport.putBoolean(s2t("useDocumentSize"), true);
        videoExport.putBoolean(s2t("useDocumentFrameRate"), true);
        videoExport.putDouble(s2t("frameRate"), 30);
        videoExport.putEnumerated(s2t("pixelAspectRatio"), s2t("pixelAspectRatio"), s2t("document"));
        videoExport.putEnumerated(s2t("fieldOrder"), s2t("videoField"), s2t("preset"));
        videoExport.putBoolean(s2t("manage"), true);
        videoExport.putBoolean(s2t("allFrames"), true);
        videoExport.putEnumerated(s2t("renderAlpha"), s2t("alphaRendering"), s2t("none"));
        videoExport.putInteger(s2t("quality"), 1);
        videoExport.putInteger(s2t("Z3DPrefHighQualityErrorThreshold"), 5);

        descriptor.putObject(s2t("using"), s2t("videoExport"), videoExport);
        executeAction(s2t("export"), descriptor, DialogModes.NO);
    }

    function videoSelectLayerById(layerId) {
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerId);
        desc.putReference(charIDToTypeID("null"), ref);
        desc.putBoolean(charIDToTypeID("MkVs"), false);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
        videoWaitMs(100);
    }

    function videoActivateDocumentById(docId) {
        for (var i = 0; i < app.documents.length; i++) {
            if (app.documents[i].id === docId) {
                app.activeDocument = app.documents[i];
                return app.activeDocument;
            }
        }
        throw new Error("Photoshop belgesi bulunamadi.");
    }

    function videoCloseOpenDocumentByFile(targetFile) {
        var targetPath = String(targetFile.fsName).toLowerCase();

        for (var i = app.documents.length - 1; i >= 0; i--) {
            var doc = app.documents[i];
            try {
                if (doc.fullName && String(doc.fullName.fsName).toLowerCase() === targetPath) {
                    app.activeDocument = doc;
                    doc.close(SaveOptions.DONOTSAVECHANGES);
                }
            } catch (closeErr) {}
        }
    }

    function videoCloseExtraDocumentsExcept(keepDoc) {
        if (!keepDoc) {
            return;
        }

        var keepId = keepDoc.id;
        for (var i = app.documents.length - 1; i >= 0; i--) {
            var doc = app.documents[i];
            if (doc.id !== keepId) {
                try {
                    doc.close(SaveOptions.DONOTSAVECHANGES);
                } catch (closeErr) {}
            }
        }
    }

    function videoCommitPlacement() {
        var actionIds = [
            "placedLayerConfirm",
            "placedLayerApply",
            "confirmPlacement",
            "placeConfirm"
        ];

        for (var i = 0; i < actionIds.length; i++) {
            try {
                executeAction(stringIDToTypeID(actionIds[i]), undefined, DialogModes.NO);
            } catch (err) {}
        }

        try {
            app.runMenuItem(stringIDToTypeID("placedLayerConfirm"));
        } catch (menuErr) {}

        videoWaitMs(150);
    }

    function videoNormalizeName(name) {
        return String(name)
            .replace(/\u00a0/g, " ")
            .replace(/\s+/g, " ")
            .replace(/^\s+|\s+$/g, "")
            .toLowerCase();
    }

    function videoWaitMs(ms) {
        var until = new Date().getTime() + ms;
        while (new Date().getTime() < until) {}
    }
