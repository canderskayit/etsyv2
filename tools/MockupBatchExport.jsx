#target photoshop

/**
 * Etsy Mockup Batch Export v11 — doldur + çerçeve dışı taşmayı kes
 * Manuel akış: SO çift tık → görsel ekle → Ctrl+S → Ctrl+W → tam PSD PNG
 * DIŞ: posterler | İÇ: PSD'ler — her kombinasyon sıfırdan açılır.
 */

(function () {
    var automatedRun = typeof CODEX_AUTOMATED_RUN !== "undefined" && CODEX_AUTOMATED_RUN === true;
    if (app.documents.length > 0 && automatedRun) {
        throw new Error("Photoshop'ta otomasyon disinda acik belge var; guvenlik icin islem baslatilmadi.");
    }
    if (app.documents.length > 0 && !confirm("Açık belgeler var. Devam edilsin mi?")) {
        return;
    }

    var SMART_LAYER_NAME = "Kare 1";
    var ARTWORK_MARKER_NAME = "__CODEX_INSERTED_ARTWORK__";
    var originalDialogMode = app.displayDialogs;
    var originalRulerUnits = app.preferences.rulerUnits;
    var originalTypeUnits = app.preferences.typeUnits;

    app.displayDialogs = DialogModes.NO;
    app.preferences.rulerUnits = Units.PIXELS;
    app.preferences.typeUnits = TypeUnits.PIXELS;

    try {
        runBatch();
    } catch (e) {
        if (!automatedRun) {
            alert("Kritik hata:\n" + e.message + (e.line ? "\nSatır: " + e.line : ""));
        }
    } finally {
        app.displayDialogs = originalDialogMode;
        app.preferences.rulerUnits = originalRulerUnits;
        app.preferences.typeUnits = originalTypeUnits;
    }

    function runBatch() {
        var psdFolder = Folder.selectDialog("1/3 — PSD mockup klasörünü seçin");
        if (!psdFolder) return;

        var posterFolder = Folder.selectDialog("2/3 — Poster görselleri klasörünü seçin");
        if (!posterFolder) return;

        var outputFolder = Folder.selectDialog("3/3 — Export çıktı klasörünü seçin");
        if (!outputFolder) return;

        var psdFiles = collectPsdFiles(psdFolder);
        var posterFiles = collectImageFiles(posterFolder);

        if (psdFiles.length === 0) {
            alert("PSD klasöründe .psd dosyası bulunamadı.");
            return;
        }
        if (posterFiles.length === 0) {
            alert("Poster klasöründe JPG/PNG dosyası bulunamadı.");
            return;
        }

        // Tüm işleri önceden oluştur: poster × psd (sıra garanti)
        var jobs = buildJobQueue(posterFiles, psdFiles, outputFolder);
        var totalJobs = jobs.length;

        var posterList = listFileNames(posterFiles, 8);
        var psdList = listFileNames(psdFiles, 8);

        if (!confirm(
            "Özet\n\n" +
            "PSD sayısı: " + psdFiles.length + "\n" +
            psdList + (psdFiles.length > 8 ? "\n..." : "") + "\n\n" +
            "Poster sayısı: " + posterFiles.length + "\n" +
            posterList + (posterFiles.length > 8 ? "\n..." : "") + "\n\n" +
            "Toplam export: " + totalJobs + " (" + posterFiles.length + " × " + psdFiles.length + ")\n\n" +
            "Başlatılsın mı?"
        )) {
            return;
        }

        var progress = createProgressUI(totalJobs);
        var log = [];
        var success = 0;
        var skipped = 0;

        for (var j = 0; j < jobs.length; j++) {
            var job = jobs[j];
            progress.update(j + 1, totalJobs, job.posterName, job.psdName);

            try {
                processOne(job.psdPath, job.posterPath, job.outPath);
                success++;
            } catch (err) {
                skipped++;
                log.push("[" + job.posterName + " + " + job.psdName + "] " + err.message);
            }

            if ((j + 1) % 25 === 0) {
                try {
                    app.purge(PurgeTarget.ALLCACHES);
                } catch (purgeErr) {}
            }
        }

        progress.close();

        var formatResult = exportPosterFormatPackages(posterFiles, outputFolder, log);

        var summary =
            "Tamamlandı\n\n" +
            "Başarılı: " + success + "\n" +
            "Atlanan: " + skipped + "\n" +
            "Format paketi: " + formatResult.success + "/" + posterFiles.length + "\n" +
            "Beklenen: " + totalJobs + "\n" +
            "Çıktı: " + outputFolder.fsName;

        if (log.length > 0) {
            summary += "\n\nUyarılar / hatalar:\n" + log.slice(0, 15).join("\n");
            if (log.length > 15) {
                summary += "\n... ve " + (log.length - 15) + " kayıt daha";
            }
            writeLog(outputFolder, log);
        }

        writeSummary(outputFolder, summary);
    }

    /**
     * DIŞ: poster | İÇ: PSD
     * Her job benzersiz posterPath + psdPath çifti.
     */
    function buildJobQueue(posterFiles, psdFiles, outputFolder) {
        var jobs = [];
        var sep = outputFolder.fsName.indexOf("\\") >= 0 ? "\\" : "/";

        for (var p = 0; p < posterFiles.length; p++) {
            var posterPath = posterFiles[p];
            var posterName = getFileNameFromPath(posterPath);
            var posterBase = getBaseNameFromPath(posterPath);

            for (var s = 0; s < psdFiles.length; s++) {
                var psdPath = psdFiles[s];
                var psdName = getFileNameFromPath(psdPath);
                var psdBase = getBaseNameFromPath(psdPath);
                var outName = sanitizeFileName(posterBase + "_" + psdBase) + ".png";
                var outPath = outputFolder.fsName + sep + outName;

                jobs.push({
                    posterPath: posterPath,
                    psdPath: psdPath,
                    posterName: posterName,
                    psdName: psdName,
                    outPath: outPath
                });
            }
        }

        return jobs;
    }

    function processOne(psdPath, posterPath, outPath) {
        var psdFile = new File(psdPath);
        var posterFile = new File(posterPath);

        if (!psdFile.exists) {
            throw new Error("PSD bulunamadı: " + psdPath);
        }
        if (!posterFile.exists) {
            throw new Error("Poster bulunamadı: " + posterPath);
        }

        var doc = null;
        var selectedLayerName = "";
        doc = app.open(psdFile);

        try {
            var layer = findSmartObjectLayer(doc, psdFile.name);
            if (!layer) {
                throw new Error(buildSmartObjectNotFoundMessage(doc));
            }
            selectedLayerName = layer.name;

            ensureLayerVisible(layer);

            // Manuel: çift tık → görsel → Ctrl+S → Ctrl+W
            replaceSmartObjectManual(doc, layer, posterFile);

            activateDocumentById(doc.id);
            app.refresh();

            exportFullDocumentPng(doc, new File(outPath));
        } catch (err) {
            if (selectedLayerName) {
                throw new Error("Seçilen smart katman: " + selectedLayerName + " | " + err.message);
            }
            throw err;
        } finally {
            if (doc) {
                closeExtraDocumentsExcept(doc);
                try {
                    doc.close(SaveOptions.DONOTSAVECHANGES);
                } catch (closeErr) {}
            }
        }
    }

    /**
     * Kullanıcının manuel yaptığı işlem:
     * 1) Smart Object'e çift tık (placedLayerEditContents)
     * 2) Poster görselini iç belgeye yapıştır
     * 3) Ctrl+S → save()
     * 4) "Yerleştir" (Place onay) varsa onayla
     * 5) Ctrl+W → close(SAVECHANGES) → ana PSD güncellenir
     */
    function replaceSmartObjectManual(mainDoc, smartLayer, imageFile) {
        var poster = new File(imageFile.fsName);
        if (!poster.exists) {
            throw new Error("Görsel yok: " + poster.fsName);
        }

        var mainDocId = mainDoc.id;
        activateDocumentById(mainDocId);
        selectLayerById(smartLayer.id);

        // Photoshop'un yerleşik Replace Contents komutu katman adı ve Smart
        // Object iç belge yapısından bağımsızdır; mevcut perspektifi korur.
        try {
            replaceSmartObjectContentsDirect(mainDoc, smartLayer.id, poster);
            activateDocumentById(mainDocId);
            waitMs(250);
            app.refresh();
            return;
        } catch (directReplaceErr) {
            activateDocumentById(mainDocId);
            throw new Error("Doğrudan Smart Object değişimi başarısız: " + directReplaceErr.message);
        }

        executeAction(
            stringIDToTypeID("placedLayerEditContents"),
            new ActionDescriptor(),
            DialogModes.NO
        );

        var soDoc = app.activeDocument;

        try {
            var guideLayer = findGuideLayer(soDoc);
            var placeBounds = guideLayer
                ? getPlacementBoundsForLayer(soDoc, guideLayer)
                : detectPlacementBounds(soDoc);

            clearImageLayersOnly(soDoc, placeBounds);

            if (guideLayer) {
                try {
                    placeBounds = refinePlacementBounds(
                        getPlacementBoundsForLayer(soDoc, guideLayer)
                    );
                } catch (guideBoundsErr) {}
            } else {
                placeBounds = refinePlacementBounds(placeBounds);
            }

            insertPosterAtPlacement(soDoc, poster, placeBounds);

            executePlacementCommitForce(soDoc);
            fitActiveLayerToPlacementBounds(soDoc, placeBounds);
            finalizePosterInFrame(soDoc, placeBounds, guideLayer);

            saveSmartObjectDocument(soDoc);

            closeSmartObjectDocument(soDoc);
        } catch (err) {
            try {
                if (app.activeDocument && app.activeDocument.id !== mainDocId) {
                    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
                }
            } catch (cleanupErr) {}
            activateDocumentById(mainDocId);
            throw err;
        }

        activateDocumentById(mainDocId);
        verifySmartObjectUpdate(mainDoc, smartLayer.id);
    }

    function replaceSmartObjectContentsDirect(mainDoc, smartLayerId, imageFile) {
        var canvasSize = readSmartObjectCanvasSize(mainDoc, smartLayerId);
        var preparedFile = createPreparedArtworkFile(
            imageFile,
            canvasSize.width,
            canvasSize.height,
            canvasSize.resolution
        );

        activateDocumentById(mainDoc.id);
        selectLayerById(smartLayerId);

        try {
            var replaceDesc = new ActionDescriptor();
            replaceDesc.putPath(charIDToTypeID("null"), preparedFile);
            executeAction(
                stringIDToTypeID("placedLayerReplaceContents"),
                replaceDesc,
                DialogModes.NO
            );

            // Bağlı Smart Object ise geçici dosyaya bağımlı kalmaması için göm.
            try {
                executeAction(
                    stringIDToTypeID("placedLayerConvertToEmbedded"),
                    new ActionDescriptor(),
                    DialogModes.NO
                );
            } catch (alreadyEmbeddedErr) {}
        } finally {
            try {
                if (preparedFile.exists) preparedFile.remove();
            } catch (removePreparedErr) {}
        }
    }

    function readSmartObjectCanvasSize(mainDoc, smartLayerId) {
        activateDocumentById(mainDoc.id);
        selectLayerById(smartLayerId);
        executeAction(
            stringIDToTypeID("placedLayerEditContents"),
            new ActionDescriptor(),
            DialogModes.NO
        );

        var contentDoc = app.activeDocument;
        var size = null;
        try {
            size = {
                width: Math.round(contentDoc.width.as("px")),
                height: Math.round(contentDoc.height.as("px")),
                resolution: Number(contentDoc.resolution)
            };
        } finally {
            try {
                contentDoc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (contentCloseErr) {}
            activateDocumentById(mainDoc.id);
        }

        if (!size || size.width < 2 || size.height < 2) {
            throw new Error("Smart Object tuval ölçüsü okunamadı.");
        }
        return size;
    }

    function createPreparedArtworkFile(imageFile, targetWidth, targetHeight, targetResolution) {
        var sourceFile = new File(imageFile.fsName);
        var sourceDoc = app.open(sourceFile);
        var tempName = "codex_mockup_" + new Date().getTime() + "_" + Math.floor(Math.random() * 1000000) + ".png";
        var tempFile = new File(Folder.temp.fsName + "/" + tempName);

        try {
            try {
                if (sourceDoc.mode !== DocumentMode.RGB) sourceDoc.changeMode(ChangeMode.RGB);
            } catch (modeErr) {}
            try {
                sourceDoc.bitsPerChannel = BitsPerChannelType.EIGHT;
            } catch (bitsErr) {}

            var sourceWidth = sourceDoc.width.as("px");
            var sourceHeight = sourceDoc.height.as("px");
            var scale = Math.max(targetWidth / sourceWidth, targetHeight / sourceHeight);
            var resizedWidth = Math.ceil(sourceWidth * scale);
            var resizedHeight = Math.ceil(sourceHeight * scale);

            sourceDoc.resizeImage(
                UnitValue(resizedWidth, "px"),
                UnitValue(resizedHeight, "px"),
                targetResolution || 72,
                scale < 1 ? ResampleMethod.BICUBICSHARPER : ResampleMethod.BICUBICSMOOTHER
            );

            var left = Math.max(0, (resizedWidth - targetWidth) / 2);
            var top = Math.max(0, (resizedHeight - targetHeight) / 2);
            sourceDoc.crop([
                UnitValue(left, "px"),
                UnitValue(top, "px"),
                UnitValue(left + targetWidth, "px"),
                UnitValue(top + targetHeight, "px")
            ]);

            var pngOptions = new PNGSaveOptions();
            pngOptions.compression = 0;
            pngOptions.interlaced = false;
            sourceDoc.saveAs(tempFile, pngOptions, true, Extension.LOWERCASE);
        } catch (prepareErr) {
            try {
                if (tempFile.exists) tempFile.remove();
            } catch (cleanupTempErr) {}
            throw prepareErr;
        } finally {
            try {
                sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (sourceCloseErr) {}
        }

        if (!tempFile.exists) {
            throw new Error("Smart Object için geçici görsel hazırlanamadı.");
        }
        return tempFile;
    }

    /** Ctrl+S — ardından "Yerleştir" çıktıysa onayla */
    function saveSmartObjectDocument(soDoc) {
        app.activeDocument = soDoc;
        commitPlacementIfNeeded(soDoc);
        waitMs(150);
        commitPlacementIfNeeded(soDoc);
        var saved = false;
        var firstError = null;
        try {
            soDoc.save();
            saved = true;
        } catch (saveErr) {
            firstError = saveErr;
            try {
                executeAction(charIDToTypeID("save"), new ActionDescriptor(), DialogModes.NO);
                saved = true;
            } catch (actionSaveErr) {}
        }
        if (!saved) {
            throw new Error("Smart Object kaydedilemedi: " + (firstError ? firstError.message : "bilinmeyen hata"));
        }
        waitMs(250);
        try {
            app.refresh();
        } catch (e) {}
        commitPlacementIfNeeded(soDoc);
        waitMs(150);
        commitPlacementIfNeeded(soDoc);
    }

    /** Ctrl+W — önce kalan Yerleştir onayını kapat */
    function closeSmartObjectDocument(soDoc) {
        app.activeDocument = soDoc;
        commitPlacementIfNeeded(soDoc);
        waitMs(100);
        saveSmartObjectDocument(soDoc);
        waitMs(150);
        try {
            soDoc.close(SaveOptions.SAVECHANGES);
        } catch (closeErr) {
            try {
                var closeDesc = new ActionDescriptor();
                closeDesc.putEnumerated(charIDToTypeID("Svng"), charIDToTypeID("YsN "), charIDToTypeID("Ys  "));
                executeAction(charIDToTypeID("Cls "), closeDesc, DialogModes.NO);
            } catch (fallbackCloseErr) {
                try {
                    soDoc.close(SaveOptions.DONOTSAVECHANGES);
                } catch (ignoreCloseErr) {}
                throw closeErr;
            }
        }
    }

    /**
     * Photoshop "Yerleştir" (Place commit) butonu — varsa onaylar.
     * Yerleştir modu yoksa hiçbir şey yapmaz.
     */
    function commitPlacementIfNeeded(soDoc) {
        app.activeDocument = soDoc;

        if (!isPlacementModeActive()) {
            return false;
        }

        return executePlacementCommit();
    }

    function isPlacementModeActive() {
        if (checkActiveToolIsPlace()) {
            return true;
        }
        if (checkActiveLayerIsPlacing()) {
            return true;
        }
        return false;
    }

    function checkActiveToolIsPlace() {
        try {
            var ref = new ActionReference();
            ref.putProperty(stringIDToTypeID("property"), stringIDToTypeID("tool"));
            ref.putEnumerated(
                charIDToTypeID("Trgt"),
                charIDToTypeID("Trgt"),
                stringIDToTypeID("application")
            );
            var result = executeActionGet(ref);
            if (result.hasKey(stringIDToTypeID("tool"))) {
                var tool = result.getString(stringIDToTypeID("tool"));
                if (/place|placed|yerle/i.test(tool)) {
                    return true;
                }
            }
        } catch (e) {}
        return false;
    }

    function checkActiveLayerIsPlacing() {
        try {
            var ref = new ActionReference();
            ref.putEnumerated(charIDToTypeID("Trgt"), charIDToTypeID("Trgt"), charIDToTypeID("Trgt"));
            var desc = executeActionGet(ref);
            if (desc.hasKey(stringIDToTypeID("placedLayer"))) {
                return true;
            }
            if (desc.hasKey(stringIDToTypeID("smartObjectMore"))) {
                return false;
            }
        } catch (e) {}
        return false;
    }

    /** Yerleştir modu tespit edilemese bile bir kez onay dene */
    function executePlacementCommitForce(soDoc) {
        app.activeDocument = soDoc;
        var actionIds = [
            "placedLayerConfirm",
            "placedLayerApply",
            "confirmPlacement",
            "placeConfirm"
        ];
        var i;
        for (i = 0; i < actionIds.length; i++) {
            try {
                executeAction(stringIDToTypeID(actionIds[i]), undefined, DialogModes.NO);
            } catch (e) {}
        }
        waitMs(100);
    }

    /**
     * paste() Place modunu açıp görseli %100 ölçekte bırakır (zoom sorunu).
     * Bunun yerine poster önce küçültülür, duplicate ile eklenir.
     */
    function insertPosterAtPlacement(soDoc, posterFile, placeBounds) {
        var poster = new File(posterFile.fsName);
        var posterDoc = app.open(poster);

        try {
            var targetW = placeBounds.width;
            var targetH = placeBounds.height;
            var srcW = posterDoc.width.as("px");
            var srcH = posterDoc.height.as("px");
            var scalePct = Math.max(targetW / srcW, targetH / srcH) * 100;

            posterDoc.resizeImage(
                UnitValue(srcW * scalePct / 100, "px"),
                UnitValue(srcH * scalePct / 100, "px"),
                null,
                ResampleMethod.BICUBICSHARPER
            );

            // duplicate yalnızca ÖNDEKİ (kaynak) belgeden çalışır
            app.activeDocument = posterDoc;
            var insertedLayer = posterDoc.artLayers[0].duplicate(soDoc, ElementPlacement.PLACEATBEGINNING);

            app.activeDocument = soDoc;
            soDoc.activeLayer = insertedLayer;
            insertedLayer.name = ARTWORK_MARKER_NAME;
            insertedLayer.visible = true;
            insertedLayer.opacity = 100;
            posterDoc.close(SaveOptions.DONOTSAVECHANGES);
            posterDoc = null;
        } catch (insertErr) {
            try {
                if (posterDoc) {
                    posterDoc.close(SaveOptions.DONOTSAVECHANGES);
                }
            } catch (closePosterErr) {}
            throw insertErr;
        }

        app.activeDocument = soDoc;
        if (!soDoc.activeLayer) {
            throw new Error("Poster Smart Object içine eklenemedi.");
        }
        if (soDoc.activeLayer.name !== ARTWORK_MARKER_NAME) {
            throw new Error("Eklenen poster katmanı aktif edilemedi.");
        }
    }

    function verifySmartObjectUpdate(mainDoc, smartLayerId) {
        activateDocumentById(mainDoc.id);
        selectLayerById(smartLayerId);
        executeAction(
            stringIDToTypeID("placedLayerEditContents"),
            new ActionDescriptor(),
            DialogModes.NO
        );

        var verifyDoc = app.activeDocument;
        var verified = false;
        try {
            var allLayers = collectAllArtLayers(verifyDoc);
            for (var i = 0; i < allLayers.length; i++) {
                if (allLayers[i].name === ARTWORK_MARKER_NAME && allLayers[i].visible) {
                    var bounds = getLayerBoundsPx(allLayers[i]);
                    if (bounds.width > 1 && bounds.height > 1) {
                        verified = true;
                        break;
                    }
                }
            }
        } finally {
            try {
                verifyDoc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (verifyCloseErr) {}
            activateDocumentById(mainDoc.id);
        }

        if (!verified) {
            throw new Error("Smart Object doğrulaması başarısız: poster kaydedilmedi.");
        }
    }

    function findGuideLayer(doc) {
        var allLayers = collectAllArtLayers(doc);
        var i;
        var docW = doc.width.as("px");
        var docH = doc.height.as("px");
        var namedCandidates = [];

        for (i = 0; i < allLayers.length; i++) {
            if (isPlaceholderLayerName(allLayers[i].name)) {
                namedCandidates.push(allLayers[i]);
            }
        }

        if (namedCandidates.length === 0) {
            return null;
        }

        var best = null;
        var bestScore = 999999999999;

        for (i = 0; i < namedCandidates.length; i++) {
            try {
                var b = getPlacementBoundsForLayer(doc, namedCandidates[i]);
                var area = b.width * b.height;
                var score = area;

                if (!isValidPlacementBounds(b, docW, docH)) {
                    score += docW * docH;
                }
                if (isStrongPlaceholderLayerName(namedCandidates[i].name)) {
                    score -= docW * docH;
                }

                if (!best || score < bestScore) {
                    best = namedCandidates[i];
                    bestScore = score;
                }
            } catch (e) {}
        }

        return best;
    }

    function getPlacementBoundsForLayer(doc, layer) {
        var docW = doc.width.as("px");
        var docH = doc.height.as("px");
        var loose = getLayerBoundsPx(layer);
        var docArea = docW * docH;

        if (loose.width * loose.height < docArea * 0.85) {
            return loose;
        }

        var tight = getTightBoundsViaSelection(doc, layer);
        if (tight && isValidPlacementBounds(tight, docW, docH)) {
            return tight;
        }

        return loose;
    }

    function getTightBoundsViaSelection(doc, layer) {
        var previous = doc.activeLayer;
        doc.activeLayer = layer;

        try {
            var desc = new ActionDescriptor();
            var ref = new ActionReference();
            ref.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Trsp"));
            desc.putReference(charIDToTypeID("null"), ref);
            var refLayer = new ActionReference();
            refLayer.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
            desc.putReference(charIDToTypeID("T   "), refLayer);
            executeAction(charIDToTypeID("setd"), desc, DialogModes.NO);

            var sel = doc.selection.bounds;
            var left = sel[0].as("px");
            var top = sel[1].as("px");
            var right = sel[2].as("px");
            var bottom = sel[3].as("px");

            doc.selection.deselect();

            return {
                left: left,
                top: top,
                right: right,
                bottom: bottom,
                width: right - left,
                height: bottom - top
            };
        } catch (e) {
            try {
                doc.selection.deselect();
            } catch (e2) {}
            return null;
        } finally {
            try {
                doc.activeLayer = previous;
            } catch (e3) {}
        }
    }

    function executePlacementCommit() {
        var actionIds = [
            "placedLayerConfirm",
            "placedLayerApply",
            "confirmPlacement",
            "placeConfirm"
        ];
        var i;

        for (i = 0; i < actionIds.length; i++) {
            try {
                executeAction(stringIDToTypeID(actionIds[i]), undefined, DialogModes.NO);
                waitMs(150);
                try {
                    app.refresh();
                } catch (r) {}
                if (!isPlacementModeActive()) {
                    return true;
                }
            } catch (e) {}
        }

        try {
            app.runMenuItem(stringIDToTypeID("placedLayerConfirm"));
            waitMs(150);
            return !isPlacementModeActive();
        } catch (e2) {}

        return false;
    }

    function waitMs(ms) {
        var until = new Date().getTime() + ms;
        while (new Date().getTime() < until) {}
    }

    /**
     * Eski poster görsellerini sil; mavi çizgi / placeholder katmanı kalır.
     */
    function clearImageLayersOnly(doc, placeBounds) {
        app.activeDocument = doc;
        var allLayers = collectAllArtLayers(doc);
        var i;

        for (i = allLayers.length - 1; i >= 0; i--) {
            var layer = allLayers[i];
            if (shouldPreserveGuideLayer(layer, placeBounds, doc)) {
                continue;
            }
            try {
                doc.activeLayer = layer;
                if (layer.isBackgroundLayer) {
                    layer.isBackgroundLayer = false;
                }
                layer.remove();
            } catch (e) {
                try {
                    executeAction(charIDToTypeID("Dlt "), undefined, DialogModes.NO);
                } catch (e2) {}
            }
        }
    }

    function shouldPreserveGuideLayer(layer, placeBounds, doc) {
        if (isPlaceholderLayerName(layer.name)) {
            return true;
        }
        try {
            var b = getLayerBoundsPx(layer);
            if (boundsNearlyEqual(b, placeBounds, 4)) {
                return true;
            }
        } catch (e) {}
        return false;
    }

    function isPlaceholderLayerName(name) {
        return /kare|placeholder|your\s*design|replace|mockup|border|guide|frame|area|template|rectangle|shape|safe|crop|design\s*here|photo|tasar[ıi]m|g[oö]rsel|yerle[sş]tir|alan|[cç]er[cç]eve|mavi|kilavuz|k[ıi]lavuz/i.test(name);
    }

    function isStrongPlaceholderLayerName(name) {
        return /kare|placeholder|your\s*design|replace|design\s*here|yerle[sş]tir|tasar[ıi]m|g[oö]rsel|alan/i.test(name);
    }

    /**
     * Smart Object içindeki mavi çizgi dikdörtgeninin sınırlarını bulur.
     * Tüm .psb tuvaline değil, bu alana sığdırma yapılır.
     */
    function detectPlacementBounds(doc) {
        var docW = doc.width.as("px");
        var docH = doc.height.as("px");
        var docArea = docW * docH;
        var allLayers = collectAllArtLayers(doc);
        var i;
        var candidates = [];

        for (i = 0; i < allLayers.length; i++) {
            var layer = allLayers[i];
            var b;
            try {
                b = getPlacementBoundsForLayer(doc, layer);
            } catch (e) {
                continue;
            }
            if (!isValidPlacementBounds(b, docW, docH)) {
                continue;
            }
            var area = b.width * b.height;
            var score = area;
            if (isPlaceholderLayerName(layer.name)) {
                score -= docArea;
            }
            candidates.push({
                bounds: b,
                area: area,
                score: score,
                name: layer.name
            });
        }

        if (candidates.length > 0) {
            candidates.sort(function (a, b) {
                if (a.score !== b.score) {
                    return a.score - b.score;
                }
                return a.area - b.area;
            });
            return candidates[0].bounds;
        }

        return {
            left: 0,
            top: 0,
            right: docW,
            bottom: docH,
            width: docW,
            height: docH
        };
    }

    function isValidPlacementBounds(b, docW, docH) {
        var docArea = docW * docH;
        var area = b.width * b.height;
        if (area <= 0) {
            return false;
        }
        if (area >= docArea * 0.92) {
            return false;
        }
        if (area < docArea * 0.005) {
            return false;
        }
        return true;
    }

    function getLayerBoundsPx(layer) {
        var b = layer.bounds;
        var left = b[0].as("px");
        var top = b[1].as("px");
        var right = b[2].as("px");
        var bottom = b[3].as("px");
        return {
            left: left,
            top: top,
            right: right,
            bottom: bottom,
            width: right - left,
            height: bottom - top
        };
    }

    function boundsNearlyEqual(a, b, tolerance) {
        tolerance = tolerance || 3;
        return (
            Math.abs(a.left - b.left) <= tolerance &&
            Math.abs(a.top - b.top) <= tolerance &&
            Math.abs(a.right - b.right) <= tolerance &&
            Math.abs(a.bottom - b.bottom) <= tolerance
        );
    }

    function collectAllArtLayers(parent, list) {
        if (!list) {
            list = [];
        }
        var layers = parent.layers;
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            if (layer.typename === "LayerSet") {
                collectAllArtLayers(layer, list);
            } else if (layer.typename === "ArtLayer") {
                list.push(layer);
            }
        }
        return list;
    }

    /**
     * Mavi alanı tam doldurur (cover): üst/alt boşluk kalmaz, gerekirse yanlardan kırpılır.
     */
    function fitActiveLayerToPlacementBounds(doc, placeBounds) {
        var layer = doc.activeLayer;
        scaleLayerToCoverPlacement(layer, placeBounds);
        centerLayerInPlacementBounds(layer, placeBounds);
        removePlacementGaps(layer, placeBounds);
    }

    /** Mavi çerçeve: taşmayı kes, boşluğu kapat, rehber katmanı gizle */
    function finalizePosterInFrame(doc, placeBounds, guideLayer) {
        var posterLayer = doc.activeLayer;
        if (!posterLayer) {
            return;
        }

        clipLayerToPlacementBounds(doc, posterLayer, placeBounds);

        if (guideLayer) {
            try {
                guideLayer.visible = false;
            } catch (clipErr) {}
        }

        removePlacementGaps(posterLayer, placeBounds);
        clipLayerToPlacementBounds(doc, posterLayer, placeBounds);
    }

    function refinePlacementBounds(bounds) {
        var inset = 2;
        if (bounds.width <= inset * 4 || bounds.height <= inset * 4) {
            return bounds;
        }
        return {
            left: bounds.left + inset,
            top: bounds.top + inset,
            right: bounds.right - inset,
            bottom: bounds.bottom - inset,
            width: bounds.width - inset * 2,
            height: bounds.height - inset * 2
        };
    }

    function clipLayerToPlacementBounds(doc, layer, placeBounds) {
        doc.activeLayer = layer;

        var region = [
            [placeBounds.left, placeBounds.top],
            [placeBounds.right, placeBounds.top],
            [placeBounds.right, placeBounds.bottom],
            [placeBounds.left, placeBounds.bottom]
        ];

        doc.selection.select(region);

        try {
            var desc = new ActionDescriptor();
            desc.putClass(charIDToTypeID("Nw  "), charIDToTypeID("Chnl"));
            var ref = new ActionReference();
            ref.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Msk "));
            desc.putReference(charIDToTypeID("At  "), ref);
            desc.putEnumerated(
                charIDToTypeID("Usng"),
                charIDToTypeID("UsrM"),
                charIDToTypeID("RvlS")
            );
            executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
        } catch (maskErr) {
            try {
                layer.grouped = false;
            } catch (e) {}
        }

        try {
            doc.selection.deselect();
        } catch (e2) {}
    }

    function scaleLayerToCoverPlacement(layer, placeBounds) {
        var b = layer.bounds;
        var layW = b[2].as("px") - b[0].as("px");
        var layH = b[3].as("px") - b[1].as("px");

        if (layW <= 0 || layH <= 0) {
            return;
        }

        var scale = Math.max(placeBounds.width / layW, placeBounds.height / layH) * 100;

        if (Math.abs(scale - 100) > 0.05) {
            layer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
        }
    }

    function centerLayerInPlacementBounds(layer, placeBounds) {
        var b = layer.bounds;
        var layW = b[2].as("px") - b[0].as("px");
        var layH = b[3].as("px") - b[1].as("px");
        var targetCenterX = placeBounds.left + placeBounds.width / 2;
        var targetCenterY = placeBounds.top + placeBounds.height / 2;
        var layerCenterX = b[0].as("px") + layW / 2;
        var layerCenterY = b[1].as("px") + layH / 2;

        layer.translate(
            UnitValue(targetCenterX - layerCenterX, "px"),
            UnitValue(targetCenterY - layerCenterY, "px")
        );
    }

    /** Üst/alt veya yan boşluk varsa merkezden büyüt */
    function removePlacementGaps(layer, placeBounds) {
        var tolerance = 1.5;
        var pass;
        var maxPasses = 6;

        for (pass = 0; pass < maxPasses; pass++) {
            var b = layer.bounds;
            var left = b[0].as("px");
            var top = b[1].as("px");
            var right = b[2].as("px");
            var bottom = b[3].as("px");
            var layW = right - left;
            var layH = bottom - top;

            var gapTop = top > placeBounds.top + tolerance;
            var gapBottom = bottom < placeBounds.bottom - tolerance;
            var gapLeft = left > placeBounds.left + tolerance;
            var gapRight = right < placeBounds.right - tolerance;

            if (!gapTop && !gapBottom && !gapLeft && !gapRight) {
                return;
            }

            if (layW <= 0 || layH <= 0) {
                return;
            }

            var bump = Math.max(placeBounds.width / layW, placeBounds.height / layH) * 100;
            if (bump <= 100.02) {
                return;
            }

            layer.resize(bump, bump, AnchorPosition.MIDDLECENTER);
            centerLayerInPlacementBounds(layer, placeBounds);
        }
    }

    function purgeAllLayersDeep(container) {
        var guard = 0;
        while (container.layers.length > 0 && guard < 100) {
            guard++;
            var removed = false;
            for (var i = container.layers.length - 1; i >= 0; i--) {
                var layer = container.layers[i];
                try {
                    container.activeLayer = layer;
                    layer.visible = true;
                    if (layer.typename === "LayerSet") {
                        purgeAllLayersDeep(layer);
                    }
                    if (layer.isBackgroundLayer) {
                        layer.isBackgroundLayer = false;
                    }
                    layer.remove();
                    removed = true;
                } catch (e) {
                    try {
                        executeAction(charIDToTypeID("Dlt "), undefined, DialogModes.NO);
                        removed = true;
                    } catch (e2) {}
                }
            }
            if (!removed) {
                break;
            }
        }
    }

    function activateDocumentById(docId) {
        for (var i = 0; i < app.documents.length; i++) {
            if (app.documents[i].id === docId) {
                app.activeDocument = app.documents[i];
                return app.activeDocument;
            }
        }
        throw new Error("Ana PSD belgesi bulunamadı.");
    }

    /**
     * Tüm mockup sahnesini PNG export eder.
     * Orijinal PSD'ye dokunmamak için kopya oluşturulur, düzleştirilir, kaydedilir.
     */
    function exportFullDocumentPng(sourceDoc, outFile) {
        activateDocumentById(sourceDoc.id);

        if (outFile.exists) {
            outFile.remove();
        }

        var parentFolder = outFile.parent;
        if (parentFolder && !parentFolder.exists) {
            parentFolder.create();
        }

        var exportDoc = sourceDoc.duplicate("_mockup_export_", true);

        try {
            app.activeDocument = exportDoc;
            exportDoc.flatten();
            try {
                if (exportDoc.mode !== DocumentMode.RGB) {
                    exportDoc.changeMode(ChangeMode.RGB);
                }
            } catch (modeErr) {}
            try {
                exportDoc.bitsPerChannel = BitsPerChannelType.EIGHT;
            } catch (bitsErr) {}

            var opts = new PNGSaveOptions();
            opts.compression = 6;
            opts.interlaced = false;

            try {
                exportDoc.saveAs(outFile, opts, true, Extension.LOWERCASE);
            } catch (saveErr) {
                if (outFile.exists) {
                    outFile.remove();
                }
                var webOpts = new ExportOptionsSaveForWeb();
                webOpts.format = SaveDocumentType.PNG;
                webOpts.PNG8 = false;
                webOpts.transparency = true;
                webOpts.interlaced = false;
                webOpts.quality = 100;
                exportDoc.exportDocument(outFile, ExportType.SAVEFORWEB, webOpts);
                if (!outFile.exists) {
                    throw saveErr;
                }
            }
        } finally {
            try {
                exportDoc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (dupCloseErr) {}
            app.activeDocument = sourceDoc;
        }
    }

    /**
     * Each source poster gets its own folder with fixed marketplace filenames:
     * cmyk.pdf, rgb.pdf, png.png and jpg.jpg.
     */
    function exportPosterFormatPackages(posterFiles, outputFolder, log) {
        var sep = getFolderSeparator(outputFolder);
        var formatsFolder = new Folder(outputFolder.fsName + sep + "source_formats");
        var success = 0;

        if (!formatsFolder.exists && !formatsFolder.create()) {
            throw new Error("Format output folder cannot be created: " + formatsFolder.fsName);
        }

        for (var i = 0; i < posterFiles.length; i++) {
            var sourceFile = new File(posterFiles[i]);
            try {
                exportPosterFormatPackage(sourceFile, formatsFolder);
                success++;
            } catch (err) {
                log.push("[format " + sourceFile.name + "] " + err.message);
            }
        }

        return { success: success };
    }

    function exportPosterFormatPackage(sourceFile, formatsFolder) {
        if (!sourceFile.exists) {
            throw new Error("Source image not found: " + sourceFile.fsName);
        }

        var sep = getFolderSeparator(formatsFolder);
        var packageName = sanitizeFileName(getBaseNameFromPath(sourceFile.fsName));
        var packageFolder = new Folder(formatsFolder.fsName + sep + packageName);

        if (!packageFolder.exists && !packageFolder.create()) {
            throw new Error("Poster format folder cannot be created: " + packageFolder.fsName);
        }

        var sourceDoc = app.open(sourceFile);

        try {
            saveSourceAsPng(sourceDoc, new File(packageFolder.fsName + sep + "png.png"));
            saveSourceAsJpg(sourceDoc, new File(packageFolder.fsName + sep + "jpg.jpg"));
            saveSourceAsPdf(sourceDoc, new File(packageFolder.fsName + sep + "rgb.pdf"), false);
            saveSourceAsPdf(sourceDoc, new File(packageFolder.fsName + sep + "cmyk.pdf"), true);
        } finally {
            try {
                sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (closeErr) {}
        }
    }

    function saveSourceAsPng(sourceDoc, outFile) {
        var exportDoc = createSourceExportDocument(sourceDoc, false);

        try {
            removeExistingFile(outFile);

            var opts = new PNGSaveOptions();
            opts.compression = 0;
            opts.interlaced = false;
            exportDoc.saveAs(outFile, opts, true, Extension.LOWERCASE);
        } finally {
            closeExportDocument(exportDoc);
        }
    }

    function saveSourceAsJpg(sourceDoc, outFile) {
        var exportDoc = createSourceExportDocument(sourceDoc, false);

        try {
            removeExistingFile(outFile);

            var opts = new JPEGSaveOptions();
            opts.quality = 12;
            opts.embedColorProfile = true;
            opts.formatOptions = FormatOptions.STANDARDBASELINE;
            exportDoc.saveAs(outFile, opts, true, Extension.LOWERCASE);
        } finally {
            closeExportDocument(exportDoc);
        }
    }

    function saveSourceAsPdf(sourceDoc, outFile, useCmyk) {
        var exportDoc = createSourceExportDocument(sourceDoc, useCmyk);

        try {
            removeExistingFile(outFile);

            var opts = new PDFSaveOptions();
            opts.preserveEditing = false;
            opts.embedColorProfile = true;
            opts.optimization = true;
            opts.encoding = PDFEncoding.ZIP;
            exportDoc.saveAs(outFile, opts, true, Extension.LOWERCASE);
        } finally {
            closeExportDocument(exportDoc);
        }
    }

    function createSourceExportDocument(sourceDoc, useCmyk) {
        var exportDoc = sourceDoc.duplicate("_source_format_export_", true);
        app.activeDocument = exportDoc;

        try {
            exportDoc.flatten();
        } catch (flattenErr) {}

        try {
            if (exportDoc.bitsPerChannel !== BitsPerChannelType.EIGHT) {
                exportDoc.bitsPerChannel = BitsPerChannelType.EIGHT;
            }
        } catch (bitDepthErr) {}

        if (useCmyk) {
            if (exportDoc.mode !== DocumentMode.CMYK) {
                exportDoc.changeMode(ChangeMode.CMYK);
            }
        } else if (exportDoc.mode !== DocumentMode.RGB) {
            exportDoc.changeMode(ChangeMode.RGB);
        }

        return exportDoc;
    }

    function removeExistingFile(file) {
        if (file.exists && !file.remove()) {
            throw new Error("Existing output cannot be replaced: " + file.fsName);
        }
    }

    function closeExportDocument(doc) {
        try {
            doc.close(SaveOptions.DONOTSAVECHANGES);
        } catch (closeErr) {}
    }

    function getFolderSeparator(folder) {
        return folder.fsName.indexOf("\\") >= 0 ? "\\" : "/";
    }

    function closeExtraDocumentsExcept(keepDoc) {
        var keepId = keepDoc.id;
        for (var i = app.documents.length - 1; i >= 0; i--) {
            var d = app.documents[i];
            if (d.id !== keepId) {
                try {
                    d.close(SaveOptions.DONOTSAVECHANGES);
                } catch (e) {}
            }
        }
    }

    // -------------------------------------------------------------------------
    // Dosya toplama — getFiles() tek dosyada dizi döndürmez; manuel tarama şart
    // -------------------------------------------------------------------------

    function collectPsdFiles(folder) {
        return collectByExtension(folder, /\.psd$/i);
    }

    function collectImageFiles(folder) {
        return collectByExtension(folder, /\.(jpe?g|png)$/i);
    }

    function collectByExtension(folder, pattern) {
        var raw = folder.getFiles();
        var items = toArray(raw);
        var result = [];

        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            if (item instanceof File && pattern.test(item.name)) {
                result.push(item.fsName);
            }
        }

        result.sort(function (a, b) {
            var an = getFileNameFromPath(a).toLowerCase();
            var bn = getFileNameFromPath(b).toLowerCase();
            return an < bn ? -1 : an > bn ? 1 : 0;
        });

        return result;
    }

    /** ExtendScript: tek eşleşmede File, çoklu eşleşmede Array — her zaman diziye çevir */
    function toArray(value) {
        if (!value) return [];
        if (value instanceof Array) return value;
        return [value];
    }

    function getFileNameFromPath(path) {
        var parts = path.replace(/\\/g, "/").split("/");
        return parts[parts.length - 1];
    }

    function getBaseNameFromPath(path) {
        var name = getFileNameFromPath(path);
        var dot = name.lastIndexOf(".");
        return dot > 0 ? name.substring(0, dot) : name;
    }

    function sanitizeFileName(name) {
        return name.replace(/[\\\/:\*\?"<>\|]/g, "_").replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
    }

    function listFileNames(paths, max) {
        var lines = [];
        var limit = Math.min(paths.length, max);
        for (var i = 0; i < limit; i++) {
            lines.push("  • " + getFileNameFromPath(paths[i]));
        }
        return lines.join("\n");
    }

    function ensureLayerVisible(layer) {
        layer.visible = true;
        var parent = layer.parent;
        while (parent && parent.typename === "LayerSet") {
            parent.visible = true;
            parent = parent.parent;
        }
    }

    function normalizeLayerName(name) {
        return String(name)
            .replace(/\u00a0/g, " ")
            .replace(/\s+/g, " ")
            .replace(/^\s+|\s+$/g, "")
            .toLowerCase();
    }

    function isKare1LayerName(name) {
        var n = normalizeLayerName(name);
        return n === "kare 1" || n === "kare1" || /^kare\s*1$/i.test(n);
    }

    function collectSmartObjectLayers(parent, results) {
        if (!results) {
            results = [];
        }
        var layers = parent.layers;
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            try {
                if (layer.kind === LayerKind.SMARTOBJECT) {
                    results.push(layer);
                }
            } catch (kindErr) {}
            if (layer.typename === "LayerSet") {
                collectSmartObjectLayers(layer, results);
            }
        }
        return results;
    }

    function findSmartObjectLayer(doc, psdName) {
        var all = collectSmartObjectLayers(doc);
        var i;

        if (all.length === 0) {
            return null;
        }

        // Katman adı ne olursa olsun tek Smart Object doğrudan baskı alanıdır.
        if (all.length === 1) {
            return all[0];
        }

        for (i = 0; i < all.length; i++) {
            if (all[i].name === SMART_LAYER_NAME) {
                return all[i];
            }
        }

        if (isGenel4Psd(psdName)) {
            for (i = 0; i < all.length; i++) {
                if (isGenel4ArtworkLayer(all[i])) {
                    return all[i];
                }
            }
            return null;
        }

        var best = null;
        var bestScore = 999;
        for (i = 0; i < all.length; i++) {
            var score = scoreSmartObjectCandidate(all[i]);
            if (score < bestScore) {
                best = all[i];
                bestScore = score;
            }
        }
        if (best && bestScore < 50) {
            return best;
        }

        for (i = 0; i < all.length; i++) {
            if (isKare1LayerName(all[i].name)) {
                return all[i];
            }
        }

        for (i = 0; i < all.length; i++) {
            if (/kare/i.test(all[i].name) && !isGeneratedPosterLayerName(all[i].name)) {
                return all[i];
            }
        }

        // Birden fazla serbest isimli Smart Object varsa görünürlük ve alan
        // bilgisini kullan. Böylece yeni PSD adları için kod değişikliği gerekmez.
        best = null;
        bestScore = 999999;
        var docArea = doc.width.as("px") * doc.height.as("px");
        for (i = 0; i < all.length; i++) {
            var fallbackScore = 0;
            try {
                if (!isLayerVisibleThroughParents(all[i])) fallbackScore += 10000;
                var bounds = getLayerBoundsPx(all[i]);
                var area = Math.max(0, bounds.width * bounds.height);
                var ratio = docArea > 0 ? area / docArea : 0;
                if (area <= 1) fallbackScore += 5000;
                if (ratio < 0.005) fallbackScore += 1000;
                if (ratio > 3) fallbackScore += 500;
                fallbackScore += Math.abs(0.2 - Math.min(ratio, 1)) * 10;
            } catch (boundsErr) {
                fallbackScore += 5000;
            }
            fallbackScore += i / 1000;
            if (fallbackScore < bestScore) {
                best = all[i];
                bestScore = fallbackScore;
            }
        }
        return best;
    }

    function isLayerVisibleThroughParents(layer) {
        var current = layer;
        while (current && current.typename !== "Document") {
            try {
                if (!current.visible) return false;
                current = current.parent;
            } catch (e) {
                break;
            }
        }
        return true;
    }

    function scoreSmartObjectCandidate(layer) {
        var n = normalizeLayerName(layer.name);
        if (n === "smart") {
            return 0;
        }
        if (/^smart(\s|[-_]|$)/i.test(n)) {
            return 1;
        }
        if (isKare1LayerName(layer.name)) {
            return 2;
        }
        if (/\bsmart\b/i.test(n)) {
            return 3;
        }
        if (isGeneratedPosterLayerName(layer.name)) {
            return 99;
        }
        if (/placeholder|your\s*design|replace|design\s*here|mockup|kare/i.test(n)) {
            return 10;
        }
        return 80;
    }

    function isGeneratedPosterLayerName(name) {
        return /generated|image|poster|source|orijinal|original|karesi/i.test(normalizeLayerName(name));
    }

    function isGenel4Psd(psdName) {
        return /genel\s*4/i.test(normalizeLayerName(psdName || ""));
    }

    function isGenel4ArtworkLayer(layer) {
        var n = normalizeLayerName(layer.name + " " + getLayerPath(layer));
        if (/orijinal|original/.test(n)) {
            return false;
        }
        return /karesi|a93b[0-9a-f-]*/i.test(n);
    }

    function getLayerPath(layer) {
        var parts = [];
        var item = layer;
        while (item && item.name) {
            parts.unshift(item.name);
            try {
                if (!item.parent || item.parent.typename === "Document") {
                    break;
                }
                item = item.parent;
            } catch (e) {
                break;
            }
        }
        return parts.join(" / ");
    }

    function selectLayerById(layerId) {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerId);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        desc.putBoolean(charIDToTypeID("MkVs"), false);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
    }

    function buildSmartObjectNotFoundMessage(doc) {
        var all = collectSmartObjectLayers(doc);
        var names = [];
        for (var i = 0; i < all.length; i++) {
            names.push('"' + all[i].name + '"');
        }
        if (names.length === 0) {
            return '"' + SMART_LAYER_NAME + '" bulunamadı (PSD içinde Smart Object yok).';
        }
        return '"' + SMART_LAYER_NAME + '" bulunamadı. Mevcut Smart Object katmanları: ' + names.join(", ");
    }

    function writeLog(outputFolder, lines) {
        try {
            var logFile = new File(outputFolder.fsName + "/mockup-batch-log.txt");
            logFile.encoding = "UTF-8";
            logFile.open("w");
            logFile.writeln("Mockup Batch Export — " + new Date().toString());
            for (var i = 0; i < lines.length; i++) {
                logFile.writeln(lines[i]);
            }
            logFile.close();
        } catch (e) {}
    }

    function writeSummary(outputFolder, summary) {
        try {
            var summaryFile = new File(outputFolder.fsName + "/mockup-batch-summary.txt");
            summaryFile.encoding = "UTF-8";
            summaryFile.open("w");
            summaryFile.write(summary);
            summaryFile.close();
        } catch (e) {}
    }

    function createProgressUI(total) {
        var win = new Window("palette", "Mockup Batch Export", undefined, { closeButton: false });
        win.orientation = "column";
        win.alignChildren = "fill";
        win.margins = 16;
        win.spacing = 10;

        win.status = win.add("statictext", undefined, "Hazırlanıyor...");
        win.status.preferredSize.width = 420;
        win.detail = win.add("statictext", undefined, "");
        win.detail.preferredSize.width = 420;
        win.bar = win.add("progressbar", undefined, 0, total);
        win.bar.preferredSize.width = 420;
        win.counter = win.add("statictext", undefined, "0 / " + total);
        win.center();
        win.show();

        return {
            update: function (current, max, posterName, psdName) {
                win.bar.value = current;
                win.counter.text = current + " / " + max;
                win.status.text = "Poster " + current + " — tam mockup export";
                win.detail.text = posterName + "  ×  " + psdName;
                win.update();
            },
            close: function () {
                try { win.close(); } catch (e) {}
            }
        };
    }
})();
