"""Тесты генератора анимированных карточек для After Effects.

Проверяют раскадровку, раскладку слоёв и собранные артефакты docs/ae.
Рендер кадров тестируется только при установленном Pillow.
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

    def test_layout_fits_canvas(self):
        for card in ae.CARDS:
            layers, card_h, delta = ae.build_layers(card)
            scale = ae.fit_scale(card_h)
            assert card_h >= delta >= 0
            assert ae.CARD_W1 * scale <= ae.CANVAS_W - 2 * ae.CANVAS_PAD + 1
            assert card_h * scale <= ae.CANVAS_H - 2 * ae.CANVAS_PAD + 1
            names = {layer.name for layer in layers}
            assert {"backdrop", "header", "bubble", "caption"} <= names
            assert len({layer.order for layer in layers}) == len(layers)


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
        layers, _, delta = ae.build_layers(card)
        steps = ae.build_steps(card, layers, delta)
        names = {layer.name for layer in layers} | {"shadow"}
        assert {step.layer for step in steps} <= names

    @pytest.mark.parametrize("card", ae.CARDS, ids=lambda card: card.key)
    def test_steps_fit_duration_and_sorted(self, card):
        layers, _, delta = ae.build_layers(card)
        steps = ae.build_steps(card, layers, delta)
        assert steps == sorted(steps, key=lambda step: (step.start, step.layer))
        assert max(step.start + step.duration for step in steps) <= card.duration
        assert all(step.duration >= 0 for step in steps)

    def test_genres_card_has_selection_swaps(self):
        card = [item for item in ae.CARDS if item.key == "03_picking_genres"][0]
        layers, _, delta = ae.build_layers(card)
        steps = ae.build_steps(card, layers, delta)
        effects = {(step.layer, step.effect) for step in steps}
        assert ("bubble_one", "fade") in effects
        assert ("bubble_two", "fade") in effects
        assert ("rows_one", "shift_down") in effects
        assert delta > 0  # сообщение с отметками выше — кнопки съезжают

    def test_step_payload_has_ae_frames(self):
        step = ae.Step("bubble", "slide_up", 1.5, 0.5, offset=20)
        payload = step.to_payload()
        assert payload["ae"]["in_frame"] == 45
        assert payload["ae"]["out_frame"] == 60
        assert payload["offset_px"] == 20


class TestArtifacts:
    """Собранные ассеты лежат в репозитории и согласованы между собой."""

    def test_timeline_json(self):
        timeline = json.loads((AE_DIR / "timeline.json").read_text(encoding="utf-8"))
        assert timeline["ae_fps"] == 30
        assert [card["key"] for card in timeline["cards"]] == [
            card.key for card in ae.CARDS
        ]
        for card in timeline["cards"]:
            assert card["gif_file"] and (AE_DIR / card["gif_file"]).exists()
            assert (AE_DIR / card["gif_file"]).stat().st_size < 4 * 1024 * 1024
            for layer in card["layers"]:
                if layer["name"] == "shadow":
                    continue
                assert (AE_DIR / layer["file"]).exists()

    def test_preview_html_mentions_all_cards(self):
        html = (AE_DIR / "preview.html").read_text(encoding="utf-8")
        for card in ae.CARDS:
            assert f"cards/{card.key}.gif" in html
            assert card.heading in html

    def test_ae_script_exists(self):
        jsx = (AE_DIR / "import_layers.jsx").read_text(encoding="utf-8")
        assert "addComp" in jsx and "timeline.json" in jsx


class TestRender:
    """Рендер кадров — только если установлен Pillow."""

    @pytest.fixture()
    def pil(self):
        return pytest.importorskip("PIL")

    def test_frames_have_canvas_size(self, pil, tmp_path):
        card = ae.CARDS[0]
        layers, card_h, delta = ae.build_layers(card)
        scale = ae.fit_scale(card_h)
        card_w, card_h_px = int(ae.CARD_W1 * scale), int(card_h * scale)
        rendered = ae.render_layers(
            layers, card_h, scale, (ae.CANVAS_W - card_w) // 2,
            (ae.CANVAS_H - card_h_px) // 2,
        )
        steps = ae.build_steps(card, layers, delta)
        frames, durations = ae.render_card_frames(
            rendered, steps, 2.0, 8, scale, "#EDF1F7"
        )
        assert all(frame.size == (ae.CANVAS_W, ae.CANVAS_H) for frame in frames)
        assert len(frames) == len(durations)
        assert sum(durations) == pytest.approx(2000, abs=200)

    def test_static_tail_is_not_recomputed(self, pil):
        card = ae.CARDS[0]
        layers, card_h, delta = ae.build_layers(card)
        scale = ae.fit_scale(card_h)
        rendered = ae.render_layers(layers, card_h, scale, 54, 54)
        steps = ae.build_steps(card, layers, delta)
        frames, durations = ae.render_card_frames(
            rendered, steps, card.duration, 15, scale, "#EDF1F7"
        )
        # последний кадр держится дольше обычного: статика не дублируется
        assert durations[-1] > durations[0]

    def test_save_gif_produces_playable_file(self, pil, tmp_path):
        from PIL import Image

        card = ae.CARDS[0]
        layers, card_h, delta = ae.build_layers(card)
        scale = ae.fit_scale(card_h)
        rendered = ae.render_layers(layers, card_h, scale, 54, 54)
        steps = ae.build_steps(card, layers, delta)
        frames, durations = ae.render_card_frames(
            rendered, steps, 2.0, 8, scale, "#EDF1F7"
        )
        path = tmp_path / "card.gif"
        size = ae.save_gif(frames, durations, path, width=360)
        assert size > 10_000
        opened = Image.open(path)
        assert opened.size == (360, 450)
        assert opened.n_frames >= 2

    def test_paste_clipped_handles_out_of_canvas(self, pil):
        from PIL import Image

        canvas = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        image = Image.new("RGBA", (50, 50), (10, 20, 30, 255))
        ae.paste_clipped(canvas, image, 80, 80)   # частично за краем
        ae.paste_clipped(canvas, image, -20, -20)  # частично за краем слева
        ae.paste_clipped(canvas, image, 500, 500)  # полностью за краем
        assert canvas.getpixel((90, 90))[3] == 255
