#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the lock-screen renderer, ``iarch/cli/render_hyprlock.py``.

hyprlock is forgiving the way Noctalia is: an unknown variable is a warning and
the lock screen still appears, so a typo does not fail -- it ships a lock screen
with no blur, or no shadow, or a password field the palette never chose. These
tests assert against the surface recorded in ``data/design/hyprlock.json``
rather than against a frozen snapshot of the output:

* every variable the renderer emits is one the manual documents, with a type,
  enumeration and range the value satisfies;
* the background's blur *is* the intensity's blur recipe, number for number,
  which is the claim that makes the lock screen part of the design system rather
  than a separate drawing;
* motion off means no fade and no capture, because an unblurred screenshot is the
  one background that makes a password field hardest to read;
* the shadow alpha is applied exactly once -- ``shadow_boost`` multiplies the
  shadow's opacity, so putting the alpha in the colour too would square it;
* no label runs a shell command, since the manual's ``cmd[]`` form spawns a
  process inside the lock surface and hangs it if the command never exits;
* ``hypridle.conf`` declares no listener and nothing in the repository starts
  it, because the shell already watches ``ext_idle_notifier_v1`` and two idle
  daemons would race to lock and suspend the same session;
* the three commands it does declare are the ones the record names, and the
  resume command is the spelling a Lua-config Hyprland v0.57.2 can actually
  run -- proved here by running it through ``/bin/sh -c`` the way hypridle does
  and reading the argv a fake ``hyprctl`` receives.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import render_hyprlock as hl  # noqa: E402
from iarch.cli import render_noctalia as noctalia  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS = hl.load_tokens()
SURFACE = json.loads(hl.SURFACE_PATH.read_text(encoding="utf-8"))
PRESET = hl.load_preset(hl.DEFAULT_PRESET)
INTENSITIES = sorted(TOKENS["intensities"])
WIDGETS = ("background", "shape", "input-field", "label", "image")
ANIMATION_TREE = {name for names in SURFACE["sections"]["animations"]["tree"].values()
                  for name in names}
RGBA = re.compile(r"rgba\((\d+), (\d+), (\d+), ([\d.]+)\)")


def render(intensity: str, preset: Dict[str, Any] = PRESET) -> Dict[str, Any]:
    return hl.render_document(TOKENS, preset, intensity, SURFACE)


def emit(intensity: str, preset: Dict[str, Any] = PRESET) -> str:
    return hl.emit_conf(render(intensity, preset), "# test header")


def parse(text: str) -> Tuple[List[str], Dict[str, List[Dict[str, str]]]]:
    """Read hyprlock's INI-like form back: block order, then instances per name.

    tomllib cannot parse it -- ``monitor = `` has an empty value and
    ``animation = fadeIn, 1, 0.12, standard`` is a bare comma list -- so the
    tests use the same nine-line block parser the QA script uses. Repeated
    keywords inside one block (bezier, animation) stay as raw ``__lines__``.
    """
    order: List[str] = []
    blocks: Dict[str, List[Dict[str, str]]] = {}
    name: str = ""
    current: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("{"):
            name = line[:-1].strip()
            current = {"__lines__": []}
            order.append(name)
            blocks.setdefault(name, []).append(current)
        elif line == "}":
            name, current = "", {}
        elif name and "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key in ("bezier", "animation"):
                current["__lines__"].append((key, value))
            else:
                current[key] = value
    return order, blocks


def one(blocks: Dict[str, List[Dict[str, str]]], name: str) -> Dict[str, str]:
    assert len(blocks[name]) == 1, f"expected exactly one {name} block"
    return blocks[name][0]


class RecordedSurface(unittest.TestCase):
    """The record has to be trustworthy before it can gate anything."""

    def test_the_record_names_its_source_and_what_it_cannot_cite(self):
        self.assertEqual("hyprlock", SURFACE["tool"])
        self.assertIn("hyprland-wiki", SURFACE["source"])
        self.assertIn("hyprlock.md", SURFACE["source"])
        self.assertIn("hypridle.md", SURFACE["source"])
        # There is no release tag and no JSON schema upstream, so the record says
        # which manual page it read instead of implying a version it did not fetch.
        self.assertIn("manual", SURFACE["verified_against"])
        self.assertIn("no JSON schema", SURFACE["_note"])

    def test_the_record_says_where_hyprlock_looks_for_the_file(self):
        self.assertIn("$XDG_CONFIG_HOME/hypr/hyprlock.conf", SURFACE["search_path"])
        self.assertIn("/etc/xdg/hypr/hyprlock.conf", SURFACE["search_path"])
        self.assertIn("first match", SURFACE["search_path_note"])

    def test_every_variable_declares_a_type_and_a_default(self):
        count = 0
        for group in ("sections", "widgets"):
            for block_name, block in SURFACE[group].items():
                for key, spec in block["keys"].items():
                    path = f"{block_name}.{key}"
                    with self.subTest(variable=path):
                        self.assertIn(spec["type"],
                                      ("bool", "int", "float", "string", "color", "gradient",
                                       "layoutxy"))
                        self.assertIn("default", spec)
                        count += 1
                for key, spec in block.get("repeated", {}).items():
                    with self.subTest(variable=f"{block_name}.{key}"):
                        self.assertIn(spec["type"], ("string", "gradient"))
                        count += 1
        self.assertGreater(count, 60, "the record has lost most of its variables")

    def test_an_enumeration_says_where_its_vocabulary_comes_from(self):
        seen = 0
        for group in ("sections", "widgets"):
            for block_name, block in SURFACE[group].items():
                for key, spec in block["keys"].items():
                    if "enum" not in spec:
                        continue
                    seen += 1
                    with self.subTest(variable=f"{block_name}.{key}"):
                        # hyprlock documents its enumerations inline in the
                        # variable table, so there is no named constant to cite
                        # and the note is the honest citation.
                        self.assertIn("enum_note", spec)
        self.assertGreaterEqual(seen, 4)
        for key, spec in SURFACE["hypridle_fallback"]["general_keys"].items():
            if "enum" in spec:
                with self.subTest(variable=f"hypridle.{key}"):
                    self.assertIn("enum_note", spec)

    def test_a_range_is_a_pair_of_numbers_that_contains_the_default(self):
        seen = 0
        for group in ("sections", "widgets"):
            for block_name, block in SURFACE[group].items():
                for key, spec in block["keys"].items():
                    if "range" not in spec:
                        continue
                    seen += 1
                    low, high = spec["range"]
                    with self.subTest(variable=f"{block_name}.{key}"):
                        self.assertLess(low, high)
                        default = spec["default"]
                        if isinstance(default, (int, float)) and not isinstance(default, bool):
                            self.assertLessEqual(low, default)
                            self.assertLessEqual(default, high)
        self.assertGreaterEqual(seen, 8, "the blur and dot ranges went missing")

    def test_the_blur_variables_match_hyprland_s_own_leaves(self):
        """The claim the whole lock screen rests on: same recipe, same numbers."""
        recorded = SURFACE["widgets"]["background"]["keys"]
        leaves = set(TOKENS["hyprland"]["leaves"])
        for variable in ("blur_passes", "blur_size", "noise", "contrast", "brightness",
                         "vibrancy"):
            with self.subTest(variable=variable):
                self.assertIn(variable, recorded)
                leaf = f"decoration:blur:{variable.replace('blur_', '')}"
                self.assertIn(leaf, leaves, f"{leaf} is not a verified Hyprland leaf")
        self.assertIn("Hyprland's own", SURFACE["widgets"]["background"]["note"])
        self.assertIn("decoration:blur", SURFACE["widgets"]["background"]["note"])

    def test_vibrancy_darkness_is_recorded_as_the_one_variable_with_no_counterpart(self):
        spec = SURFACE["widgets"]["background"]["keys"]["vibrancy_darkness"]
        self.assertIn("no counterpart", spec["note"])
        self.assertNotIn("decoration:blur:vibrancy_darkness", TOKENS["hyprland"]["leaves"])

    def test_the_widgets_the_manual_lists_are_the_widgets_recorded(self):
        self.assertEqual({"background", "shape", "input-field", "label", "image"},
                         set(SURFACE["widgets"]) - {"positioning", "shadowable", "clickable"})
        for name, block in SURFACE["widgets"].items():
            if name in WIDGETS:
                with self.subTest(widget=name):
                    self.assertIn(" { }", block["table"])

    def test_the_animation_tree_is_recorded_leaf_by_leaf(self):
        self.assertEqual({"fadeIn", "fadeOut", "inputFieldColors", "inputFieldFade",
                          "inputFieldWidth", "inputFieldDots"}, ANIMATION_TREE)
        self.assertIn("does nothing", SURFACE["sections"]["animations"]["tree_note"])

    def test_the_record_says_what_hyprlock_cannot_do(self):
        items = SURFACE["not_in_hyprlock"]["items"]
        for wanted in ("per-widget blur", "radius token", "global speed multiplier",
                       "theme or palette file", "unlock command", "idle timeout"):
            with self.subTest(missing=wanted):
                self.assertIn(wanted, items)
                self.assertTrue(items[wanted])

    def test_the_input_field_is_recorded_as_not_clickable(self):
        self.assertIn("not* clickable", SURFACE["widgets"]["clickable"]["note"])
        self.assertFalse(SURFACE["widgets"]["input-field"].get("clickable"))
        self.assertIn("unlock bypass", SURFACE["widgets"]["clickable"]["keys"]["onclick"]["note"])

    def test_the_signal_that_unlocks_without_a_password_is_recorded(self):
        self.assertIn("SIGUSR1", SURFACE["keys_and_signals"]["signals"])
        self.assertIn("without a password", SURFACE["keys_and_signals"]["signals"]["SIGUSR1"])
        self.assertIn("SECURITY.md", SURFACE["keys_and_signals"]["signals"]["SIGUSR1"])

    def test_the_hypridle_fallback_records_both_block_shapes(self):
        fallback = SURFACE["hypridle_fallback"]
        self.assertEqual("hypridle", fallback["tool"])
        self.assertTrue(fallback["required"])
        self.assertIn("lock_cmd", fallback["general_keys"])
        self.assertIn("condition_cmd", fallback["listener_keys"])
        self.assertIn("/bin/sh -c", fallback["listener_keys"]["condition_cmd"]["note"])
        self.assertIn("racing", fallback["note"])


class TheRenderStaysInsideTheRecord(unittest.TestCase):
    """hyprlock would warn and continue; the renderer must refuse instead."""

    def test_every_intensity_renders_and_validates(self):
        for intensity in INTENSITIES:
            with self.subTest(intensity=intensity):
                self.assertEqual([], hl.validate(render(intensity), SURFACE))

    def test_every_preset_renders_and_validates(self):
        for path in sorted(noctalia.PRESET_DIR.glob("*.json")):
            preset = noctalia.load_preset(path.stem)
            with self.subTest(preset=path.stem):
                self.assertEqual([],
                                 hl.validate(render(TOKENS["default_intensity"], preset),
                                             SURFACE))

    def test_the_emitted_file_carries_no_variable_the_record_lacks(self):
        _, blocks = parse(emit("frosted"))
        known = hl._blocks(SURFACE)
        positioning = SURFACE["widgets"]["positioning"]["keys"]
        shadowable = SURFACE["widgets"]["shadowable"]["keys"]
        for name, instances in blocks.items():
            allowed = set(known[name]["keys"]) | set(positioning) | set(shadowable)
            for instance in instances:
                for key in instance:
                    if key == "__lines__":
                        continue
                    with self.subTest(variable=f"{name}.{key}"):
                        self.assertIn(key, allowed)

    def test_a_misspelled_variable_is_refused(self):
        for block, key in (("background", "blur_passses"), ("general", "compositor_fad"),
                           ("input-field", "roundingg"), ("label", "font_sizes")):
            doc = render("frosted")
            instances = doc[block] if isinstance(doc[block], list) else [doc[block]]
            instances[0][key] = 3
            with self.subTest(variable=f"{block}.{key}"):
                problems = hl.validate(doc, SURFACE)
                self.assertEqual(1, len(problems))
                # A widget with one instance is named without an index, so the
                # message reads the way the file does; with several, it does not.
                instances = doc[block] if isinstance(doc[block], list) else [doc[block]]
                here = f"{block}.{key}" if len(instances) == 1 else f"{block}[0].{key}"
                self.assertIn(f"{here}: hyprlock has no such variable", problems[0])

    def test_a_bool_where_a_number_belongs_is_refused(self):
        doc = render("frosted")
        doc["background"][0]["blur_passes"] = True
        problems = hl.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("is not an int", problems[0])

    def test_a_number_where_a_bool_belongs_is_refused(self):
        doc = render("frosted")
        doc["general"]["hide_cursor"] = 1
        problems = hl.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("is not a bool", problems[0])

    def test_a_palette_hex_that_never_went_through_rgba_is_refused(self):
        doc = render("frosted")
        doc["background"][0]["color"] = PRESET["palette"]["background"]
        problems = hl.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("not an rgb()/rgba() colour", problems[0])

    def test_a_number_outside_the_documented_range_is_refused(self):
        doc = render("frosted")
        doc["background"][0]["blur_size"] = 1000
        doc["input-field"][0]["dots_size"] = 0.9
        problems = hl.validate(doc, SURFACE)
        self.assertEqual(2, len(problems))
        self.assertTrue(all("outside the documented range" in problem for problem in problems))

    def test_an_alignment_outside_the_documented_vocabulary_is_refused(self):
        doc = render("frosted")
        doc["label"][0]["halign"] = "middle"
        problems = hl.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("is not one of", problems[0])

    def test_a_widget_collapsed_into_a_single_dict_is_refused(self):
        doc = render("frosted")
        doc["label"] = doc["label"][0]
        problems = hl.validate(doc, SURFACE)
        self.assertTrue(any(problem.startswith("label: a widget block must be a list")
                            for problem in problems), problems)

    def test_a_lock_screen_with_no_field_or_no_background_is_refused(self):
        for block in ("background", "input-field"):
            doc = render("frosted")
            del doc[block]
            with self.subTest(missing=block):
                problems = hl.validate(doc, SURFACE)
                self.assertTrue(any(problem.startswith(f"{block}:") for problem in problems))

    def test_a_block_hyprlock_does_not_have_is_refused(self):
        doc = render("frosted")
        doc["backgrund"] = [{"path": "screenshot"}]
        problems = hl.validate(doc, SURFACE)
        self.assertIn("backgrund: is not a block hyprlock documents", problems)


class MotionReachesTheLockScreen(unittest.TestCase):
    """The lock screen is part of the session, so it obeys the same switch."""

    def test_the_fade_durations_are_the_preset_s_own_leaves(self):
        preset = hl.load_preset_animation(TOKENS["intensities"]["frosted"]["motion"]["preset"])
        _, blocks = parse(emit("frosted"))
        animations = one(blocks, "animations")
        for leaf in ("fadeIn", "fadeOut"):
            event = preset["events"][leaf]
            emitted = [value for key, value in animations["__lines__"]
                       if key == "animation" and value.startswith(f"{leaf},")]
            with self.subTest(leaf=leaf):
                self.assertEqual(1, len(emitted), f"{leaf} was not emitted exactly once")
                parts = [part.strip() for part in emitted[0].split(",")]
                self.assertEqual(
                    [leaf, "1", f"{event['duration_ms'] / 1000:g}", event["curve"]], parts)

    def test_the_bezier_lines_are_the_preset_s_control_points(self):
        _, blocks = parse(emit("frosted"))
        animations = one(blocks, "animations")
        preset = hl.load_preset_animation(TOKENS["intensities"]["frosted"]["motion"]["preset"])
        declared = {}
        for key, value in animations["__lines__"]:
            if key == "bezier":
                parts = [part.strip() for part in value.split(",")]
                declared[parts[0]] = [float(part) for part in parts[1:]]
        self.assertTrue(declared)
        for name, points in declared.items():
            curve = preset["curves"][name]
            self.assertEqual("bezier", curve["type"])
            self.assertEqual([float(coordinate) for point in curve["points"]
                              for coordinate in point], points)

    def test_a_spring_curve_is_refused_rather_than_approximated(self):
        """hyprlock's bezier keyword takes four numbers; a spring has no such form."""
        spring = TOKENS["motion"]["spring"]
        with self.assertRaises(hl.HyprlockError) as caught:
            hl.bezier_line("spring", {"type": "spring", **spring})
        self.assertIn("cannot be expressed", str(caught.exception))
        # The presets that carry a spring use it for window motion, so this is a
        # guard rather than a limitation anyone hits -- prove that stays true.
        for path in sorted(hl.ANIMATION_DIR.glob("*.json")):
            animation_preset = json.loads(path.read_text(encoding="utf-8"))
            for leaf in ("fadeIn", "fadeOut"):
                event = animation_preset["events"].get(leaf)
                if not isinstance(event, dict) or not event.get("enabled"):
                    continue
                with self.subTest(preset=path.stem, leaf=leaf):
                    curve = animation_preset["curves"][event["curve"]]
                    self.assertEqual("bezier", curve["type"])

    def test_a_curve_with_the_wrong_shape_is_refused(self):
        for curve in ({"type": "bezier", "points": [[0.4, 0.0]]},
                      {"type": "bezier", "points": [[0.4, 0.0], [0.2, 1.0, 0.5]]},
                      {"type": "steps"}):
            with self.subTest(curve=curve):
                with self.assertRaises(hl.HyprlockError):
                    hl.bezier_line("odd", curve)

    def test_motion_off_emits_no_animation_line_at_all(self):
        doc = render("performance")
        self.assertIs(False, doc["animations"]["enabled"])
        self.assertEqual([], doc["animations"]["lines"])
        self.assertIs(False, doc["general"]["compositor_fade"])
        text = hl.emit_conf(doc, "# test")
        self.assertNotIn("animation = ", text)
        self.assertNotIn("bezier = ", text)

    def test_compositor_fade_follows_the_intensity_s_motion_switch(self):
        for intensity in INTENSITIES:
            with self.subTest(intensity=intensity):
                enabled = TOKENS["intensities"][intensity]["motion"]["enabled"]
                self.assertIs(enabled, render(intensity)["general"]["compositor_fade"])
                self.assertIs(enabled, render(intensity)["animations"]["enabled"])

    def test_a_preset_with_no_enabled_fade_is_refused_not_guessed(self):
        tokens = json.loads(json.dumps(TOKENS))
        tokens["intensities"]["frosted"]["motion"] = {"enabled": True, "preset": "off"}
        with self.assertRaises(hl.HyprlockError) as caught:
            hl.render_document(tokens, PRESET, "frosted", SURFACE)
        self.assertIn("no enabled fadeIn", str(caught.exception))

    def test_the_speed_multiplier_is_deliberately_not_applied(self):
        """hyprlock has no multiplier, so scaling one side would desynchronise them."""
        self.assertIn("speed_multiplier", hl.ANIMATION_COMMENT)
        animation_preset = hl.load_preset_animation(
            TOKENS["intensities"]["frosted"]["motion"]["preset"])
        milliseconds = animation_preset["events"]["fadeIn"]["duration_ms"]
        # The emitted duration is the preset's own, unscaled. If a multiplier were
        # ever folded in here this assertion is what would notice.
        emitted = [value for key, value in
                   parse(emit("frosted"))[1]["animations"][0]["__lines__"]
                   if key == "animation" and value.startswith("fadeIn,")]
        self.assertEqual(1, len(emitted))
        self.assertEqual(f"fadeIn, 1, {milliseconds / 1000:g}, standard", emitted[0])


class TheGlassRecipe(unittest.TestCase):
    """Every number and colour comes from a token or a palette, never from here."""

    def test_the_background_blur_is_the_intensity_s_blur_number_for_number(self):
        for intensity in INTENSITIES:
            blur = TOKENS["intensities"][intensity]["blur"]
            background = render(intensity)["background"][0]
            with self.subTest(intensity=intensity):
                self.assertEqual(int(blur["passes"]), background["blur_passes"])
                self.assertEqual(int(blur["size"]), background["blur_size"])
                self.assertEqual(float(blur["noise"]), background["noise"])
                self.assertEqual(float(blur["contrast"]), background["contrast"])
                self.assertEqual(float(blur["brightness"]), background["brightness"])
                self.assertEqual(float(blur["vibrancy"]), background["vibrancy"])

    def test_a_blurred_intensity_captures_the_desktop_and_a_flat_one_does_not(self):
        for intensity in INTENSITIES:
            background = render(intensity)["background"][0]
            blurred = TOKENS["intensities"][intensity]["blur"]["enabled"]
            with self.subTest(intensity=intensity):
                self.assertEqual("screenshot" if blurred else "", background["path"])

    def test_the_background_comment_changes_with_the_capture_decision(self):
        self.assertIn("screenshot", emit("frosted"))
        flat = emit("performance")
        self.assertIn("No capture and no blur", flat)
        self.assertNotIn("No capture and no blur", emit("frosted"))

    def test_the_card_is_the_panel_recipe(self):
        intensity = TOKENS["intensities"]["frosted"]
        card = render("frosted")["shape"][0]
        palette = PRESET["palette"]
        self.assertEqual(hl.rgba(palette["surface"], intensity["glass"]["tint_alpha"]),
                         card["color"])
        radius = TOKENS["radius"]
        self.assertEqual(radius[radius["panel"]], card["rounding"])
        self.assertEqual(TOKENS["layout"]["border_size"], card["border_size"])
        self.assertEqual(hl.rgba(palette["outline_variant"], intensity["glass"]["border_alpha"]),
                         card["border_color"])
        self.assertEqual(hl.rgba(palette["outline_variant"], intensity["glass"]["border_alpha"]),
                         render("frosted")["input-field"][0]["outer_color"])
        self.assertEqual(hl.rgba(palette["surface_variant"],
                                 intensity["glass"]["tint_alpha_strong"]),
                         render("frosted")["input-field"][0]["inner_color"])

    def test_the_shadow_alpha_is_applied_exactly_once(self):
        """shadow_boost multiplies the shadow's opacity, so it carries the alpha."""
        alpha = TOKENS["intensities"]["frosted"]["glass"]["shadow_alpha"]
        card = render("frosted")["shape"][0]
        self.assertEqual(round(alpha, 2), card["shadow_boost"])
        self.assertEqual(hl.opaque(PRESET["palette"]["shadow"]), card["shadow_color"])
        self.assertNotIn(f", {alpha:g})", card["shadow_color"])
        clock = render("frosted")["label"][0]
        self.assertEqual(round(alpha, 2), clock["shadow_boost"])
        self.assertEqual(hl.opaque(PRESET["palette"]["shadow"]), clock["shadow_color"])

    def test_an_intensity_without_shadows_emits_no_shadow_at_all(self):
        card = render("performance")["shape"][0]
        self.assertNotIn("shadow_passes", card)
        clock = render("performance")["label"][0]
        self.assertEqual(0, clock["shadow_passes"])

    def test_the_three_state_colours_are_the_palette_s_semantic_accents(self):
        palette = PRESET["palette"]["accent"]
        field = render("frosted")["input-field"][0]
        self.assertEqual(hl.opaque(palette["warning"]), field["check_color"])
        self.assertEqual(hl.opaque(palette["danger"]), field["fail_color"])
        self.assertEqual(hl.opaque(palette["primary"]), field["capslock_color"])

    def test_every_colour_in_the_file_is_a_palette_colour(self):
        channels = set()
        for role, value in PRESET["palette"].items():
            if isinstance(value, str):
                channels.add(hl.rgb(value))
            elif isinstance(value, dict):
                for colour in value.values():
                    channels.add(hl.rgb(colour))
        self.assertGreater(len(channels), 10)
        text = emit("frosted")
        found = 0
        for match in RGBA.finditer(text):
            red, green, blue, _alpha = match.groups()
            found += 1
            with self.subTest(colour=match.group(0)):
                self.assertIn((int(red), int(green), int(blue)), channels)
        self.assertGreater(found, 8)
        self.assertNotRegex(text, r"#[0-9a-fA-F]{6}", "a palette hex reached the file")

    def test_the_type_and_radii_come_from_the_tokens(self):
        sizes, font = TOKENS["font"]["sizes"], TOKENS["font"]
        radius = TOKENS["radius"]
        text = emit("frosted")
        self.assertIn(f"font_family = {font['ui']}", text)
        self.assertIn(f"font_size = {sizes['xxl']}", text)
        self.assertIn(f"font_size = {sizes['lg']}", text)
        self.assertIn(f"font_size = {sizes['sm']}", text)
        self.assertIn(f"rounding = {radius[radius['panel']]}", text)
        self.assertIn(f"rounding = {radius[radius['input']]}", text)

    def test_the_field_is_hyprlock_s_own_documented_size(self):
        field = render("frosted")["input-field"][0]
        default = SURFACE["widgets"]["input-field"]["keys"]["size"]["default"]
        self.assertEqual(default, field["size"])

    def test_the_field_stays_visible_while_empty(self):
        """A field that hides until you type gives no affordance at all."""
        for intensity in INTENSITIES:
            with self.subTest(intensity=intensity):
                self.assertIs(False, render(intensity)["input-field"][0]["fade_on_empty"])
        self.assertIn("fade_on_empty = false", emit("frosted"))

    def test_the_z_order_puts_the_capture_behind_the_card_behind_the_field(self):
        doc = render("frosted")
        self.assertEqual(-1, doc["background"][0]["zindex"])
        self.assertEqual(1, doc["shape"][0]["zindex"])
        self.assertEqual(2, doc["input-field"][0]["zindex"])
        self.assertTrue(all(label["zindex"] == 3 for label in doc["label"]))

    def test_the_composition_is_one_capture_one_card_and_one_field(self):
        order, blocks = parse(emit("frosted"))
        self.assertEqual(1, len(blocks["background"]))
        self.assertEqual(1, len(blocks["shape"]))
        self.assertEqual(1, len(blocks["input-field"]))
        self.assertEqual(3, len(blocks["label"]))
        self.assertLess(order.index("background"), order.index("shape"))
        self.assertLess(order.index("shape"), order.index("input-field"))


class NoCommandRunsOnTheLockScreen(unittest.TestCase):
    """A lock surface that spawns processes is a lock surface that can hang."""

    def test_no_label_runs_a_command(self):
        """Checked on the parsed values, not the file: the comments name cmd[] to
        explain why it is *not* used, so a plain substring search would fail on
        the explanation rather than on a command."""
        _, blocks = parse(emit("frosted"))
        for name, instances in blocks.items():
            for instance in instances:
                for key, value in instance.items():
                    with self.subTest(variable=f"{name}.{key}"):
                        self.assertNotIn("cmd[", str(value))
                        self.assertNotIn(key, ("onclick", "reload_cmd", "reload_time"))

    def test_the_labels_use_hyprlock_s_own_substitutions(self):
        labels = render("frosted")["label"]
        self.assertEqual("$TIME", labels[0]["text"])
        self.assertEqual("$DESC", labels[1]["text"])
        for name in ("$TIME", "$DESC"):
            with self.subTest(substitution=name):
                self.assertIn(name, SURFACE["substitutions"]["names"])

    def test_the_hint_names_the_keys_the_manual_documents(self):
        keys = SURFACE["keys_and_signals"]["default_keys"]
        self.assertIn("ESC", keys)
        self.assertIn("Esc clears the field", render("frosted")["label"][2]["text"])

    def test_no_pam_module_is_named(self):
        doc = render("frosted")
        self.assertEqual({"pam:enabled": True}, doc["auth"])
        self.assertIn("/etc/pam.d", hl.BLOCK_COMMENTS["auth"])

    def test_empty_input_is_never_ignored(self):
        self.assertNotIn("ignore_empty_input", emit("frosted"))
        self.assertIn("never does", SURFACE["sections"]["general"]["keys"]
                      ["ignore_empty_input"]["note"])


class TheIdleFallback(unittest.TestCase):
    """Shipped unlaunched, with no timer of its own."""

    def test_the_fallback_declares_no_listener(self):
        doc = hl.render_idle_document(SURFACE)
        self.assertEqual({"general"}, set(doc))
        self.assertEqual([], hl.validate_idle(doc, SURFACE))
        text = hl.emit_idle_conf(doc, "# test")
        self.assertNotIn("listener {", text)

    def test_the_fallback_carries_exactly_three_commands(self):
        general = hl.render_idle_document(SURFACE)["general"]
        self.assertEqual(["lock_cmd", "before_sleep_cmd", "after_sleep_cmd"], list(general))
        self.assertEqual(hl.IDLE_LOCK_CMD, general["lock_cmd"])

    def test_the_lock_command_prefers_a_shell_that_is_already_running(self):
        self.assertEqual("pidof noctalia || hyprlock", hl.IDLE_LOCK_CMD)
        # The same shape the hypridle manual's own example uses.
        self.assertIn("pidof", SURFACE["hypridle_fallback"]["note"] + hl.IDLE_COMMENT)

    def test_every_shipped_command_is_the_one_the_record_names(self):
        commands = SURFACE["hypridle_fallback"]["commands"]
        self.assertEqual("Hyprland v0.57.2", commands["compositor_verified_against"])
        for name, constant in (("lock_cmd", hl.IDLE_LOCK_CMD),
                               ("before_sleep_cmd", hl.IDLE_BEFORE_SLEEP_CMD),
                               ("after_sleep_cmd", hl.IDLE_AFTER_SLEEP_CMD)):
            with self.subTest(command=name):
                self.assertEqual(constant, commands[name]["value"])
                self.assertGreater(len(commands[name]["note"]), 40)
        # And the file on disk carries all three, so the record cannot drift
        # away from the payload it describes.
        text = hl.emit_idle_conf(hl.render_idle_document(SURFACE), "# test")
        for name in ("lock_cmd", "before_sleep_cmd", "after_sleep_cmd"):
            self.assertIn(f"{name} = {commands[name]['value']}", text)

    def test_the_resume_command_is_the_spelling_this_compositor_can_run(self):
        # Hyprland v0.57.2 answers `hyprctl dispatch X` by evaluating
        # `return hl.dispatch(X)` as Lua when the config provider is Lua
        # (src/ipc/s1/Commands.cpp:1332-1350), and this session's config is Lua.
        command = hl.IDLE_AFTER_SLEEP_CMD
        self.assertIn("hl.dsp.dpms", command)
        self.assertIn("action = 'enable'", command)
        self.assertTrue(command.startswith("hyprctl dispatch "))

    def test_the_manuals_spelling_is_recorded_as_rejected_not_silently_dropped(self):
        entry = SURFACE["hypridle_fallback"]["commands"]["after_sleep_cmd"]
        self.assertEqual("hyprctl dispatch dpms on", entry["rejected_spelling"])
        self.assertNotEqual(entry["value"], entry["rejected_spelling"])
        self.assertNotIn(entry["rejected_spelling"], hl.IDLE_AFTER_SLEEP_CMD)
        # The reason has to name both the mechanism that broke it and the
        # alternative that is not available either, or the next reader will
        # "simplify" the string straight back.
        for phrase in ("hyprctl keyword", "hyprctl.1.rst", "unknown request",
                       "PluginAPI.cpp", "S1.cpp", "Lua-config"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry["rejected_note"])
        for phrase in ("Commands.cpp:1332-1350", "LuaBindingsDispatchers.cpp:1380",
                       "LuaBindingsInternal.cpp:317-325", "silently toggling",
                       "hyprctl/src/main.cpp:283-288"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry["note"])

    def test_the_resume_command_reaches_hyprctl_as_one_lua_argument(self):
        """Run it the way hypridle does, and read the argv a fake hyprctl gets.

        hypridle spawns every command through ``/bin/sh -c`` (``spawn()``,
        hypridle ``src/core/Hypridle.cpp:286-289``, the same at v0.1.8 and on
        main), so the quoting in the emitted line is what decides how many
        arguments the compositor sees. No compositor is needed to prove that
        half, and the rejected spelling is run the same way to show the
        difference: three arguments, which the compositor would paste into
        ``hl.dispatch(dpms on)`` and fail to compile.
        """
        script = (
            "#!/bin/sh\n"
            'for arg in "$@"; do printf "%s\\n" "$arg"; done > "$ARGV_LOG"\n'
            'printf "ok\\n"\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "argv.log"
            fake = Path(tmp) / "hyprctl"
            fake.write_text(script.replace("$ARGV_LOG", str(log)), encoding="utf-8")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=tmp)

            def argv_for(command: str) -> List[str]:
                result = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                                        text=True, env=env, timeout=30, check=False)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("ok", result.stdout.strip())
                return log.read_text(encoding="utf-8").splitlines()

            self.assertEqual(["dispatch", "hl.dsp.dpms({ action = 'enable' })"],
                             argv_for(hl.IDLE_AFTER_SLEEP_CMD))
            rejected = SURFACE["hypridle_fallback"]["commands"]["after_sleep_cmd"][
                "rejected_spelling"]
            self.assertEqual(["dispatch", "dpms", "on"], argv_for(rejected))

    def test_an_unknown_hypridle_variable_is_refused(self):
        doc = hl.render_idle_document(SURFACE)
        doc["general"]["lock_command"] = "hyprlock"
        problems = hl.validate_idle(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("hypridle has no such variable", problems[0])

    def test_a_listener_is_refused_because_it_would_own_a_timer(self):
        doc = hl.render_idle_document(SURFACE)
        doc["listener"] = [{"timeout": 900, "on-timeout": "systemctl suspend"}]
        problems = hl.validate_idle(doc, SURFACE)
        self.assertTrue(any("declares only general" in problem for problem in problems))

    def test_a_listener_with_an_unknown_variable_is_refused(self):
        doc = hl.render_idle_document(SURFACE)
        doc["listeners"] = [{"timeout": 900, "on_timeout": "systemctl suspend"}]
        problems = hl.validate_idle(doc, SURFACE)
        self.assertIn("listener.on_timeout: hypridle has no such variable", problems)

    def test_the_file_says_why_it_is_not_started(self):
        text = hl.emit_idle_conf(hl.render_idle_document(SURFACE), "# test")
        for phrase in ("UNLAUNCHED", "ext_idle_notifier_v1", "racing", "startup.lua"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_nothing_in_the_session_starts_hypridle(self):
        startup = (ROOT / ".config/hypr/startup.lua").read_text(encoding="utf-8")
        self.assertNotIn("hypridle", startup)
        # Nor may any other shipped file start it: two idle daemons is the failure
        # this whole design avoids.
        offenders = []
        for path in sorted((ROOT / ".config").rglob("*")):
            if not path.is_file() or path.name == "hypridle.conf":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if re.search(r"(?<![.\w-])hypridle(?![.\w-])", text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_the_shell_owns_idle_instead(self):
        with (ROOT / ".config/noctalia/config.toml").open("rb") as handle:
            import tomllib
            config = tomllib.load(handle)
        behaviors = config["idle"]["behavior"]
        self.assertEqual({"lock", "screen_off"}, set(behaviors))
        self.assertEqual("lock", behaviors["lock"]["action"])
        self.assertEqual("screen_off", behaviors["screen_off"]["action"])
        self.assertLess(behaviors["lock"]["timeout"], behaviors["screen_off"]["timeout"])
        self.assertTrue(all(value["enabled"] for value in behaviors.values()))


class TheShippedPayload(unittest.TestCase):
    """What is committed must be exactly what a fresh render produces."""

    def test_the_shipped_files_match_a_fresh_render(self):
        code, out, err = self.cli("--check")
        self.assertEqual(0, code, out + err)
        self.assertIn("2 shipped file(s)", out)

    def test_the_shipped_files_carry_the_generated_header(self):
        for name in ("hyprlock.conf", "hypridle.conf"):
            path = ROOT / ".config/hypr" / name
            with self.subTest(file=name):
                self.assertTrue(path.is_file())
                first = path.read_text(encoding="utf-8").splitlines()[0]
                self.assertTrue(configstore.is_header_line(first), first)

    def test_the_shipped_lock_file_proves_its_own_provenance(self):
        text = (ROOT / ".config/hypr/hyprlock.conf").read_text(encoding="utf-8")
        self.assertIn("data/design/tokens.json", text)
        self.assertIn(f"intensity={TOKENS['default_intensity']}", text)
        self.assertIn("data/design/hyprlock.json", text)
        self.assertIn(SURFACE["verified_against"], text)

    def test_the_shipped_file_is_the_default_intensity_and_not_somebody_s(self):
        """The payload has to be reproducible from repository state alone."""
        shipped = (ROOT / ".config/hypr/hyprlock.conf").read_text(encoding="utf-8")
        self.assertEqual(hl.rendered_text(ROOT / ".config/hypr/hyprlock.conf",
                                          hl.emit_conf(render(TOKENS["default_intensity"]),
                                                       hl.provenance(
                                                           TOKENS, PRESET, SURFACE,
                                                           TOKENS["default_intensity"]))),
                         shipped)
        # And a different intensity really does produce different bytes, so the
        # assertion above is not comparing two constants.
        self.assertNotEqual(shipped, hl.rendered_text(
            ROOT / ".config/hypr/hyprlock.conf",
            hl.emit_conf(render("performance"),
                         hl.provenance(TOKENS, PRESET, SURFACE, "performance"))))

    def cli(self, *argv):
        """Run main() with the streams captured. Not named run(): that is
        unittest's own entry point and shadowing it breaks the test runner."""
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = hl.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_print_writes_the_config_to_stdout(self):
        code, out, _err = self.cli("--print")
        self.assertEqual(0, code)
        self.assertIn("input-field {", out)
        self.assertIn("general {", out)

    def test_an_unknown_intensity_is_a_usage_error(self):
        code, _out, err = self.cli("--intensity", "glassy", "--print")
        self.assertEqual(2, code)
        self.assertIn("unknown intensity", err)

    def test_an_unknown_preset_is_a_usage_error(self):
        code, _out, err = self.cli("--preset", "nope", "--print")
        self.assertEqual(2, code)
        self.assertIn("no preset", err)

    def test_writing_into_a_directory_produces_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.cli("--output-dir", tmp)
            self.assertEqual(0, code, out + err)
            written = sorted(path.name for path in Path(tmp).iterdir())
            self.assertEqual(["hypridle.conf", "hyprlock.conf"], written)
            self.assertIn("NOT started", out)
            for name in written:
                first = (Path(tmp) / name).read_text(encoding="utf-8").splitlines()[0]
                self.assertTrue(configstore.is_header_line(first))

    def test_a_render_that_leaves_the_record_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "hyprlock.conf"
            original = hl.render_document

            def broken(*args, **kwargs):
                doc = original(*args, **kwargs)
                doc["general"]["compositor_fade"] = "yes"
                return doc

            self.addCleanup(setattr, hl, "render_document", original)
            hl.render_document = broken
            code, _out, err = self.cli("--output-dir", tmp)
            self.assertEqual(2, code)
            self.assertIn("is not valid", err)
            self.assertFalse(target.exists(), "a refused render still wrote a file")


if __name__ == "__main__":
    unittest.main()
