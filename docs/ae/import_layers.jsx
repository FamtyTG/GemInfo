// GameHunter: импорт слоёв обучающей карточки в After Effects.
//
// Как пользоваться:
//   1. File -> Scripts -> Run Script File... и выберите этот файл.
//   2. Укажите папку docs/ae/layers/<экран> (например, 01_start).
//   3. Скрипт создаст композицию 1920x1080, 60 fps, разложит слои и
//      проставит ключевые кадры Opacity/Position из timeline.json.
//
// Эффекты «pop», «tap» и «shift_down» доделайте вручную по раскадровке
// (docs/10_ae_animaciya_kartochek.md): Scale с Easy Ease (F9).
(function () {
    var WIDTH = 1920, HEIGHT = 1080, FPS = 60;

    var layersFolder = Folder.selectDialog("Выберите папку слоёв (docs/ae/layers/<экран>)");
    if (!layersFolder) return;

    var cardKey = layersFolder.name;
    var timelineFile = new File(layersFolder.parent.parent.fsName + "/timeline.json");
    var cardInfo = null;
    if (timelineFile.exists) {
        timelineFile.open("r");
        timelineFile.encoding = "UTF-8";
        var raw = timelineFile.read();
        timelineFile.close();
        try {
            var timeline = JSON.parse(raw);
            for (var i = 0; i < timeline.cards.length; i++) {
                if (timeline.cards[i].key === cardKey) cardInfo = timeline.cards[i];
            }
        } catch (e) { cardInfo = null; }
    }

    app.beginUndoGroup("GameHunter: карточка " + cardKey);
    var comp = app.project.items.addComp(
        "GameHunter " + cardKey, WIDTH, HEIGHT, 1,
        cardInfo ? cardInfo.duration_seconds : 6, FPS
    );

    var files = layersFolder.getFiles(function (f) {
        return f instanceof File && /\.png$/i.test(f.name);
    });
    files.sort(function (a, b) { return a.name < b.name ? -1 : 1; });

    var added = [];
    for (var k = files.length - 1; k >= 0; k--) {
        var item = app.project.importFile(new ImportOptions(files[k]));
        var layer = comp.layers.add(item);
        added.push(layer);
        if (cardInfo) {
            var shortName = item.name.replace(/\.png$/i, "").replace(/^\d+_/, "");
            for (var m = 0; m < cardInfo.layers.length; m++) {
                var meta = cardInfo.layers[m];
                if (meta.name === shortName) {
                    layer.property("Position").setValue(
                        [meta.x + meta.width / 2, meta.y + meta.height / 2]
                    );
                }
            }
        }
    }

    if (cardInfo) {
        for (var s = 0; s < cardInfo.steps.length; s++) {
            var step = cardInfo.steps[s];
            if (step.effect !== "fade" && step.effect !== "slide_up"
                && step.effect !== "hide") continue;
            for (var L = 1; L <= comp.numLayers; L++) {
                var cl = comp.layer(L);
                if (cl.name.replace(/^\d+_/, "").replace(/\.png$/i, "") !== step.layer) continue;
                var t0 = step.start_s, t1 = step.start_s + step.duration_s;
                var op = cl.property("Opacity");
                if (step.effect === "hide") {
                    op.setValueAtTime(t0, 100);
                    op.setValueAtTime(t1, 0);
                } else {
                    op.setValueAtTime(t0, 0);
                    op.setValueAtTime(t1, 100);
                }
                if (step.effect === "slide_up") {
                    var pos = cl.property("Position");
                    var base = pos.value;
                    var factor = (cardInfo.layers && step.layer.indexOf("step_") === 0
                        || step.layer === "panel_heading" || step.layer === "progress") ? 2 : cardInfo.scale;
                    pos.setValueAtTime(t0, [base[0], base[1] + step.offset_px * factor]);
                    pos.setValueAtTime(t1, base);
                }
            }
        }
    }

    comp.openInViewer();
    app.endUndoGroup();
    alert("Композиция «GameHunter " + cardKey + "» готова.\nСлоёв: " + added.length);
})();
