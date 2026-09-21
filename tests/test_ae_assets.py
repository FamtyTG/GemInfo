"""Тесты генератора обучающих видеокарточек для After Effects.

Карточки — инструктаж 16:9 (1920×1080) при 60 fps: демо телефона слева,
панель шагов справа, кольцо подсветки в моменты нажатий. Проверяют
раскадровку, раскладку слоёв, тайминг кадров и собранные артефакты.
Рендер тестируется только при установленном Pillow (кадры 1920×1080 —
поэтому fps в тестах крошечный, а GIF уменьшаются по ширине).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT / "scripts" / "generate_ae_assets.py"
AE_DIR = PROJECT_ROOT / "docs" / "ae"
TUTORIAL_DIR = PROJECT_ROOT / "gamehunter" / "assets" / "tutorial"

TELEGRAM_ANIMATION_LIMIT = 5 * 1024 * 1024  # 50 МБ API, но держим GIF лёгкими


def load_module():
    """Загружает скрипт как модуль (он лежит вне пакета)."""
    spec = importlib.util.spec_from_file_location("generate_ae_assets", SPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ae = load_module()


class TestCards:
    def test_three_cards(self):
        assert [card.key for card in ae.CARDS] == [
            "01_start",
            "03_picking_genres",
            "04_game_list",
        ]

    def test_cards_reference_existing_screens(self):
        files = {screen.file for screen in ae.mockups.SCREENS}
        for card in ae.CARDS:
            assert card.screen_file in files
            assert card.heading and card.description
            assert card.duration > 3

    def test_canvas_is_16_by_9_at_60fps(self):
        assert (ae.CANVAS_W, ae.CANVAS_H) == (1920, 1080)
        assert ae.AE_FPS == 60
        assert ae.DEFAULT_GIF_FPS == 60

    def test_layout_fits_canvas(self):
        for card in ae.CARDS:
            layout = ae.build_layers(card)
            scale = layout["scale"]
            card_h = layout["card_h1"]

            assert scale > 0
            assert layout["delta_h"] >= 0
            assert ae.CARD_W1 * scale <= ae.CANVAS_W
            assert card_h * scale <= ae.CANVAS_H

            names = {layer.name for layer in layout["phone"]}
            assert {"backdrop", "header", "bubble", "caption"} <= names
            for group in (layout["phone"], layout["canvas"]):
                orders = [layer.order for layer in group]
                assert len(set(orders)) == len(orders)


class TestEasings:
    @pytest.mark.parametrize("name", sorted(ae.EASINGS))
    def test_boundaries(self, name):
        assert ae.ease(name, 0.0) == pytest.approx(0.0, abs=1e-9)
        assert ae.ease(name, 1.0) == pytest.approx(1.0, abs=1e-9)

    def test_progress_is_clamped(self):
        assert ae.ease("ease_out", -1) == 0.0
        assert ae.ease("ease_out", 2) == 1.0

    def test_layer_state_hidden_before_first_step(self):
        steps = [ae.Step("bubble", "fade", 1.0, 0.5)]
        assert ae.layer_state(steps, 0.0) == (0.0, 0.0, 1.0)
        alpha, dy, scale = ae.layer_state(steps, 2.0)
        assert alpha == 1.0 and dy == 0.0 and scale == 1.0

    def test_layer_state_slides_and_shifts(self):
        steps = [
            ae.Step("rows_one", "pop", 1.0, 0.2),
            ae.Step("rows_one", "shift_down", 1.2, 0.3, offset=36),
        ]
        _, dy_start, _ = ae.layer_state(steps, 1.2)
        _, dy_end, _ = ae.layer_state(steps, 1.6)
        assert dy_start == 0.0
        assert dy_end == pytest.approx(36, abs=1e-6)

    def test_layer_state_tap_keeps_visibility(self):
        steps = [
            ae.Step("inline_1", "fade", 1.0, 0.2),
            ae.Step("inline_1", "tap", 2.0, 0.3),
        ]
        alpha, _, scale = ae.layer_state(steps, 2.15)
        assert alpha == 1.0
        assert scale < 1.0


class TestSteps:
    @pytest.mark.parametrize("card", ae.CARDS, ids=lambda card: card.key)
    def test_steps_reference_existing_layers(self, card):
        layout = ae.build_layers(card)
        steps, taps = ae.build_steps(card, layout)
        names = (
            {layer.name for layer in layout["phone"] + layout["canvas"]}
            | {"shadow"}
            | {f"pointer_{index}" for index in range(1, len(taps) + 1)}
        )
        assert {step.layer for step in steps} <= names

    @pytest.mark.parametrize("card", ae.CARDS, ids=lambda card: card.key)
    def test_steps_fit_duration_and_sorted(self, card):
        layout = ae.build_layers(card)
        steps, taps = ae.build_steps(card, layout)

        assert steps == sorted(steps, key=lambda step: (step.start, step.layer))
        assert max(step.start + step.duration for step in steps) <= card.duration
        assert all(step.duration >= 0 for step in steps)
        assert taps and all(0 < moment < card.duration for moment, _ in taps)

    @pytest.mark.parametrize("card", ae.CARDS, ids=lambda card: card.key)
    def test_each_tap_has_pointer_step(self, card):
        """На каждое нажатие — шаг кольца подсветки (pointer_N, tap)."""
        layout = ae.build_layers(card)
        steps, taps = ae.build_steps(card, layout)
        pointer_steps = {
            (step.layer, step.start) for step in steps
            if step.effect == "pop" and step.layer.startswith("pointer_")
        }
        assert {
            (f"pointer_{index}", moment)
            for index, (moment, _) in enumerate(taps, start=1)
        } <= pointer_steps

    def test_genres_card_has_selection_swaps(self):
        card = [item for item in ae.CARDS if item.key == "03_picking_genres"][0]
        layout = ae.build_layers(card)
        steps, _ = ae.build_steps(card, layout)
        effects = {(step.layer, step.effect) for step in steps}

        assert ("bubble_one", "fade") in effects
        assert ("bubble_two", "fade") in effects
        assert ("rows_one", "shift_down") in effects
        assert layout["delta_h"] > 0  # сообщение с отметками выше — кнопки съезжают

    def test_step_payload_has_ae_frames(self):
        step = ae.Step("bubble", "slide_up", 1.5, 0.5, offset=20)
        payload = step.to_payload()

        assert payload["ae"]["in_frame"] == round(1.5 * ae.AE_FPS)  # 90
        assert payload["ae"]["out_frame"] == round(2.0 * ae.AE_FPS)  # 120
        assert payload["offset_px"] == 20


class TestFrameTiming:
    """GIF хранит длительности в сантисекундах — тайминг задаём сразу в cs."""

    def test_frame_cs_pattern_at_60fps(self):
        assert [ae.frame_cs(index, 60) for index in range(6)] == [2, 2, 1, 2, 2, 1]

    def test_frame_cs_average_is_exact_at_60fps(self):
        total_cs = sum(ae.frame_cs(index, 60) for index in range(60))
        assert total_cs == 100  # 60 кадров = ровно секунда

    def test_frame_cs_low_fps(self):
        assert ae.frame_cs(0, 10) == 10
        assert ae.frame_cs(1, 10) == 10


class TestArtifacts:
    """Собранные ассеты лежат в репозитории и согласованы между собой."""

    def test_timeline_json(self):
        timeline = json.loads((AE_DIR / "timeline.json").read_text(encoding="utf-8"))

        assert timeline["ae_fps"] == 60
        assert timeline["canvas"] == {"width": 1920, "height": 1080}
        assert [card["key"] for card in timeline["cards"]] == [
            card.key for card in ae.CARDS
        ]
        for card in timeline["cards"]:
            assert card["gif_file"] == f"gamehunter/assets/tutorial/{card['key']}.gif"
            gif = PROJECT_ROOT / card["gif_file"]
            assert gif.exists()
            assert gif.stat().st_size < TELEGRAM_ANIMATION_LIMIT
            assert card["gif_bytes"] == gif.stat().st_size
            assert card["duration_seconds"] > 3
            assert card["ae_fps"] == 60
            assert card["tutorial_steps"]
            for layer in card["layers"]:
                if layer["name"] == "shadow":
                    continue
                assert (AE_DIR / layer["file"]).exists()

    def test_tutorial_gifs_match_texts(self):
        from gamehunter.presentation import texts

        for card in ae.CARDS:
            assert texts.TUTORIAL_STEPS[card.key]

    def test_preview_html_mentions_all_cards(self):
        html = (AE_DIR / "preview.html").read_text(encoding="utf-8")
        for card in ae.CARDS:
            assert f"tutorial/{card.key}.gif" in html
            assert card.heading in html

    def test_ae_script_exists(self):
        jsx = (AE_DIR / "import_layers.jsx").read_text(encoding="utf-8")
        assert "addComp" in jsx and "timeline.json" in jsx


class TestRender:
    """Рендер кадров — только если установлен Pillow."""

    @pytest.fixture()
    def pil(self):
        return pytest.importorskip("PIL")

    @pytest.fixture()
    def card0(self):
        card = ae.CARDS[0]
        layout = ae.build_layers(card)
        steps, taps = ae.build_steps(card, layout)
        rendered, _ = ae.render_layers(layout)
        return card, layout, ae.add_pointers(list(rendered), taps), steps

    def test_frames_have_canvas_size(self, pil, card0):
        _, layout, rendered, steps = card0
        frames, durations = ae.render_card_frames(
            rendered, steps, 2.0, 4, layout["scale"], "#EDF1F7"
        )

        assert all(frame.size == (ae.CANVAS_W, ae.CANVAS_H) for frame in frames)
        assert len(frames) == len(durations) == len(ae.frame_times(2.0, 4))
        # ровно, без потерь на сантисекундах
        assert sum(durations) == len(frames) * ae.frame_cs(0, 4) * 10

    def test_iter_stops_after_animation_end(self, pil, card0):
        """Статический хвост не пересчитывается: генератор останавливается."""
        card, layout, rendered, steps = card0
        animation_end = max(step.start + step.duration for step in steps)

        frames = list(
            ae.iter_card_frames(
                rendered, steps, card.duration, 8, layout["scale"], "#EDF1F7"
            )
        )

        assert len(frames) * (1 / 8) <= animation_end + 1 / 8

    def test_add_pointers_creates_rings(self, pil, card0):
        _, _, rendered, _ = card0
        pointer_names = [
            layer.name for layer in rendered if layer.name.startswith("pointer_")
        ]
        assert pointer_names == ["pointer_1"]
        ring = [layer for layer in rendered if layer.name == "pointer_1"][0]
        assert ring.width > 0 and ring.height > 0

    def test_export_card_frames_gif(self, pil, card0, tmp_path):
        from PIL import Image

        _, layout, rendered, steps = card0
        gif_path = tmp_path / "card.gif"
        frames_dir = tmp_path / "frames"
        size, png_count = ae.export_card_frames(
            rendered, steps, 2.0, 4, layout["scale"], "#EDF1F7",
            gif_path, frames_dir, width=320,
        )

        assert size > 1_000
        opened = Image.open(gif_path)
        assert opened.size == (320, 180)
        assert opened.n_frames >= 2
        assert opened.n_frames <= png_count  # дубликаты в GIF сливаются
        total_ms = 0
        for index in range(opened.n_frames):
            opened.seek(index)
            total_ms += opened.info.get("duration", 0)
        expected_ms = len(ae.frame_times(2.0, 4)) * ae.frame_cs(0, 4) * 10
        assert total_ms == pytest.approx(expected_ms, abs=20)

    def test_export_merges_duplicate_frames(self, pil, card0, tmp_path):
        """Дубликаты кадров сливаются с суммированием длительности (Pillow их
        иначе молча выбрасывает)."""
        from PIL import Image

        _, layout, rendered, steps = card0
        gif_path = tmp_path / "card.gif"
        ae.export_card_frames(
            rendered, steps, 4.0, 4, layout["scale"], "#EDF1F7", gif_path, None,
            width=160,
        )

        opened = Image.open(gif_path)
        assert opened.n_frames <= 4 * 4  # меньше «сырого» числа кадров
        opened.seek(opened.n_frames - 1)
        last_duration = opened.info.get("duration", 0)
        opened.seek(0)
        assert last_duration >= opened.info.get("duration", 0)

    def test_paste_clipped_handles_out_of_canvas(self, pil):
        from PIL import Image

        canvas = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        image = Image.new("RGBA", (50, 50), (10, 20, 30, 255))
        ae.paste_clipped(canvas, image, 80, 80)   # частично за краем
        ae.paste_clipped(canvas, image, -20, -20)  # частично за краем слева
        ae.paste_clipped(canvas, image, 500, 500)  # полностью за краем
        assert canvas.getpixel((90, 90))[3] == 255
