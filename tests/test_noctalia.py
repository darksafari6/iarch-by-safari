#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Noctalia renderer, ``iarch/cli/render_noctalia.py``.

Noctalia is forgiving in exactly the wrong way for a generated config: an
unknown key produces a warning and is ignored, and an out-of-range number is
clamped with a warning. Neither stops the shell starting, so a mistake here
ships as a design that silently does not match the tokens. These tests
therefore assert against the upstream contract recorded in
``data/design/noctalia.json`` rather than against a frozen snapshot:

* every setting the renderer emits exists in the extracted v5.4.1 schema, with
  a type, enum and numeric range that the value satisfies;
* the two keys the previously shipped ``config.toml`` carried under
  ``[bar.default]`` -- ``layer`` and a plain ``radius`` -- are refused, because
  upstream declares them only in ``barMonitorOverrideSchema``;
* every number and colour the renderer writes is derived from a token or a
  preset, never chosen inside the renderer;
* a palette carries the 16 ``m*`` colours Noctalia reads, plus the optional
  terminal block, for both modes;
* nothing is written unless the whole render validates, and a failed write
  leaves the filesystem byte-for-byte as it was.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import render_noctalia as noctalia  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS = noctalia.load_tokens()
SURFACE = noctalia.load_surface()
PRESET_IDS = sorted(path.stem for path in noctalia.PRESET_DIR.glob("*.json"))
INTENSITIES = sorted(TOKENS["intensities"])
HEX = re.compile(r"^#[0-9a-f]{6}([0-9a-f]{2})?$")

# Every preset at every intensity is a configuration a user can ask for, so the
# contract is checked across the whole product rather than for one sample.
COMBINATIONS: List[Tuple[str, str]] = [
    (preset, intensity) for preset in PRESET_IDS for intensity in INTENSITIES
]


def render(preset_id: str, intensity: str) -> Dict[str, Any]:
    return noctalia.render_config(TOKENS, noctalia.load_preset(preset_id), intensity)


def flat(doc: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested tables into dotted paths, the way Noctalia names them."""
    out: Dict[str, Any] = {}
    for key, value in doc.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flat(value, path))
        else:
            out[path] = value
    return out


class VerifiedSurface(unittest.TestCase):
    """The extracted schema itself must be trustworthy before it can gate."""

    def test_surface_names_the_upstream_release_it_was_read_from(self):
        self.assertRegex(SURFACE["verified_against"], r"^v\d+\.\d+\.\d+$")
        self.assertIn("config_schema.cpp", SURFACE["source"])
        self.assertIn("config_validate.cpp", SURFACE["source"])

    def test_every_section_maps_to_a_schema_function(self):
        for name, section in SURFACE["sections"].items():
            with self.subTest(section=name):
                self.assertRegex(section["schema"], r"^[a-zA-Z]+Schema$")
                self.assertTrue(section["keys"], f"{name} records no keys")

    def test_no_key_is_flagged_as_missing_from_upstream(self):
        """The point of the surface: the renderer must not invent settings."""
        offenders = []
        for name, section in SURFACE["sections"].items():
            for key, spec in section["keys"].items():
                if spec.get("not_in_upstream_schema"):
                    offenders.append(f"{name}.{key}")
        self.assertEqual([], offenders)

    def test_every_key_declares_a_type_and_cites_its_bounds(self):
        def walk(keys, prefix):
            for key, spec in keys.items():
                path = f"{prefix}.{key}"
                with self.subTest(setting=path):
                    if "keys" in spec:  # a subTable() reference, not a leaf
                        self.assertRegex(spec["table"], r"^[a-zA-Z]+Schema$")
                        walk(spec["keys"], path)
                        continue
                    self.assertIn(spec["type"], ("bool", "integer", "float", "string", "array"))
                    if "enum" in spec:
                        self.assertTrue(spec["enum"])
                        # A custom parser has no kEnum constant, and a vocabulary this project
                        # enforces because upstream silently ignores an unknown value has
                        # neither -- but both have to say which of those they are.
                        self.assertTrue(spec.get("enum_constant") or spec.get("parser")
                                        or spec.get("enum_note"),
                                        f"{path} lists an enum with no upstream constant "
                                        f"and no note explaining where it came from")
                    if "range" in spec:
                        self.assertLessEqual(spec["range"][0], spec["range"][1])
                        # An inline Range<...>{lo, hi} passed straight to field() has no named
                        # constant, so a note citing the expression counts as the citation --
                        # the same escape hatch `parser` gives an enum with no kEnum constant.
                        self.assertTrue(spec.get("range_constant") or spec.get("range_note"),
                                        f"{path} lists a range with no upstream citation")

        for name, section in SURFACE["sections"].items():
            walk(section["keys"], name)

    def test_colour_settings_are_marked_as_colour_settings(self):
        marked = [
            (f"{name}.{key}", spec)
            for name, section in SURFACE["sections"].items()
            for key, spec in section["keys"].items()
            if spec.get("color")
        ]
        self.assertTrue(marked, "no colour setting was recorded")
        for path, spec in sorted(marked):
            with self.subTest(setting=path):
                self.assertEqual("string", spec["type"])

    def test_colour_roles_are_the_documented_set(self):
        roles = SURFACE["color_roles"]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertIn("surface_container", roles)
        self.assertIn("outline_variant", roles)
        # Noctalia renamed these for plugin API 43; a palette or a colourField
        # that still uses the old name is rewritten on load with a warning.
        self.assertNotIn("surface_variant", roles)
        self.assertNotIn("outline", roles)

    def test_palette_contract_records_what_the_loader_reads(self):
        palette = SURFACE["palette"]
        self.assertEqual(16, len(palette["fields"]))
        self.assertTrue(all(field.startswith("m") for field in palette["fields"]))
        self.assertEqual(["dark", "light"], palette["modes"])
        self.assertEqual({"normal", "bright"}, set(palette["terminal_groups"]))
        self.assertEqual(8, len(palette["terminal_ansi"]))

    def test_bar_container_exception_is_recorded_with_its_reason(self):
        """``position`` and ``name`` are read for a bar but declared elsewhere."""
        container = SURFACE["bar_container"]
        self.assertEqual("order", container["order_key"])
        self.assertIn("position", container["keyed_outside_fields"])
        self.assertEqual("barMonitorOverrideSchema", container["monitor_override_schema"])
        keys = SURFACE["sections"]["bar.default"]["keys"]
        # These two belong to the per-monitor override table only. Writing them
        # under [bar.default] warns "unknown setting" and is then ignored, which
        # is what the previously shipped config.toml did.
        self.assertNotIn("layer", keys)
        self.assertNotIn("radius", keys)
        for corner in ("radius_top_left", "radius_top_right",
                       "radius_bottom_left", "radius_bottom_right"):
            self.assertIn(corner, keys)


class EveryCombinationIsValid(unittest.TestCase):
    def test_every_preset_at_every_intensity_validates(self):
        self.assertEqual(24, len(COMBINATIONS))
        for preset, intensity in COMBINATIONS:
            with self.subTest(preset=preset, intensity=intensity):
                self.assertEqual([], noctalia.validate(render(preset, intensity), SURFACE))

    def test_every_render_parses_as_toml_and_survives_the_round_trip(self):
        for preset, intensity in COMBINATIONS:
            with self.subTest(preset=preset, intensity=intensity):
                body = noctalia.emit_toml(render(preset, intensity),
                                          noctalia.provenance(TOKENS, noctalia.load_preset(preset),
                                                              SURFACE, intensity))
                parsed = tomllib.loads(body)
                self.assertEqual(flat(render(preset, intensity)), flat(parsed))

    def test_bar_order_names_every_bar_and_nothing_else(self):
        for preset, intensity in COMBINATIONS:
            with self.subTest(preset=preset, intensity=intensity):
                self.assertEqual([], noctalia.order_only(render(preset, intensity)))

    def test_an_invented_setting_is_refused(self):
        """The gate has to actually refuse something."""
        doc = render("midnight-glass", "frosted")
        doc["shell"]["corner_roundness"] = 1.5
        problems = noctalia.validate(doc, SURFACE)
        self.assertTrue(any("no such setting" in line for line in problems), problems)

    def test_an_out_of_range_number_is_refused_rather_than_clamped(self):
        doc = render("midnight-glass", "frosted")
        doc["dock"]["magnification_scale"] = 3.5  # kDockMagnificationScale is 1-2
        problems = noctalia.validate(doc, SURFACE)
        self.assertTrue(any("kDockMagnificationScale" in line for line in problems), problems)

    def test_a_bad_enum_value_is_refused(self):
        doc = render("midnight-glass", "frosted")
        doc["shell"]["panel"]["transparency_mode"] = "acrylic"
        self.assertTrue(any("transparency_mode" in line
                            for line in noctalia.validate(doc, SURFACE)))

    def test_a_wrong_type_is_refused(self):
        doc = render("midnight-glass", "frosted")
        doc["dock"]["auto_hide"] = "yes"
        self.assertTrue(any("not a boolean" in line
                            for line in noctalia.validate(doc, SURFACE)))

    def test_a_colour_that_is_neither_role_nor_hex_is_refused(self):
        doc = render("midnight-glass", "frosted")
        doc["notification"]["border_color"] = "surface-variant"  # the pre-rename spelling
        problems = noctalia.validate(doc, SURFACE)
        self.assertTrue(any("neither a colour role nor a hex colour" in line for line in problems),
                        problems)


class ValuesAreDerivedFromTokens(unittest.TestCase):
    """Nothing here may be a number the renderer chose for itself."""

    def setUp(self):
        self.doc = render("midnight-glass", "frosted")
        self.intensity = TOKENS["intensities"]["frosted"]
        self.radius = TOKENS["radius"]
        self.shell = self.intensity["shell"]

    def test_corner_radius_scale_is_the_panel_radius_over_the_medium_radius(self):
        expected = round(self.radius[self.radius["panel"]] / self.radius["md"], 2)
        self.assertEqual(expected, self.doc["shell"]["corner_radius_scale"])
        self.assertEqual(expected, noctalia.corner_radius_scale(TOKENS))

    def test_animation_speed_is_the_token_duration_against_the_baseline(self):
        expected = round(noctalia.MOTION_BASELINE_MS / TOKENS["motion"]["normal_ms"], 2)
        self.assertEqual(expected, self.doc["shell"]["animation"]["speed"])

    def test_the_shell_animation_switch_follows_the_intensity(self):
        # The intensity is the coarse motion switch and it is repository state, so
        # the committed payload stays reproducible from a clean clone while still
        # meaning something: Performance stops the shell's own panels animating for
        # the same reason it stops the compositor's windows.
        for name in INTENSITIES:
            with self.subTest(intensity=name):
                self.assertEqual(TOKENS["intensities"][name]["motion"]["enabled"],
                                 render("midnight-glass", name)["shell"]["animation"]["enabled"])

    def test_performance_turns_the_shell_animations_off(self):
        self.assertTrue(self.doc["shell"]["animation"]["enabled"],
                        "the default intensity animates")
        self.assertFalse(render("midnight-glass", "performance")["shell"]["animation"]["enabled"])

    def test_the_switch_actually_varies_rather_than_being_a_constant(self):
        # It used to be `motion.normal_ms > 0`, which is true for every intensity
        # the tokens ship: the key existed and never did anything. If a future edit
        # makes it constant again, this is what catches it.
        rendered = {render("midnight-glass", name)["shell"]["animation"]["enabled"]
                    for name in INTENSITIES}
        self.assertEqual({True, False}, rendered)

    def test_opacities_come_from_the_intensity(self):
        self.assertEqual(self.shell["bar_opacity"], self.doc["bar"]["default"]["background_opacity"])
        self.assertEqual(self.shell["capsule_opacity"],
                         self.doc["bar"]["default"]["capsule_opacity"])
        self.assertEqual(self.shell["dock_opacity"], self.doc["dock"]["background_opacity"])
        self.assertEqual(self.shell["notification_opacity"],
                         self.doc["notification"]["background_opacity"])

    def test_panel_transparency_mode_is_the_intensity_setting(self):
        self.assertEqual(self.shell["panel_transparency"],
                         self.doc["shell"]["panel"]["transparency_mode"])

    def test_radii_are_the_token_radii(self):
        bar = self.doc["bar"]["default"]
        # radius roles name a size, which then names the number: panel -> lg -> 24.
        panel = self.radius[self.radius["panel"]]
        card = self.radius[self.radius["card"]]
        for corner in ("radius_top_left", "radius_top_right",
                       "radius_bottom_left", "radius_bottom_right"):
            self.assertEqual(panel, bar[corner])
            self.assertIsInstance(bar[corner], int)  # kBarRadiusRange is an integer field
        self.assertEqual(float(card), bar["capsule_radius"])
        self.assertEqual(panel, self.doc["dock"]["radius"])
        self.assertIsInstance(self.doc["dock"]["radius"], int)

    def test_border_width_is_the_layout_token_and_uses_a_colour_role(self):
        self.assertIn(noctalia.BORDER_ROLE, SURFACE["color_roles"])
        self.assertIn(noctalia.FILL_ROLE, SURFACE["color_roles"])
        width = float(TOKENS["layout"]["border_size"])
        bar = self.doc["bar"]["default"]
        self.assertEqual(width, bar["border_width"])
        self.assertEqual(noctalia.BORDER_ROLE, bar["border"])
        self.assertEqual(noctalia.FILL_ROLE, bar["capsule_fill"])
        self.assertEqual(noctalia.BORDER_ROLE, bar["capsule_border"])
        # The same border treatment on every floating surface, so the shell
        # reads as one material rather than six.
        self.assertEqual(width, self.doc["dock"]["border_width"])
        self.assertEqual(noctalia.BORDER_ROLE, self.doc["dock"]["border"])
        self.assertEqual(width, self.doc["shell"]["panel"]["border_width"])
        self.assertEqual(noctalia.BORDER_ROLE, self.doc["shell"]["panel"]["border_color"])
        self.assertEqual(width, self.doc["notification"]["border_width"])
        self.assertEqual(noctalia.BORDER_ROLE, self.doc["notification"]["border_color"])

    def test_blur_follows_the_intensity(self):
        enabled = self.intensity["blur"]["enabled"]
        self.assertEqual(enabled, self.doc["bar"]["default"]["compositor_blur"])
        self.assertEqual(enabled, self.doc["dock"]["compositor_blur"])

    def test_performance_preset_switches_every_heavy_effect_off(self):
        doc = render("midnight-glass", "performance")
        performance = TOKENS["intensities"]["performance"]
        self.assertEqual("solid", doc["shell"]["panel"]["transparency_mode"])
        self.assertEqual("solid", performance["shell"]["panel_transparency"])
        self.assertFalse(doc["bar"]["default"]["compositor_blur"])
        self.assertFalse(doc["dock"]["compositor_blur"])
        self.assertFalse(doc["shell"]["settings_window_translucent"])
        self.assertFalse(performance["blur"]["enabled"])
        self.assertFalse(performance["shell"]["settings_translucent"])
        self.assertGreaterEqual(performance["shell"]["bar_opacity"], 0.9)

    def test_privacy_defaults_hold_in_every_render(self):
        for preset, intensity in COMBINATIONS:
            with self.subTest(preset=preset, intensity=intensity):
                doc = render(preset, intensity)
                self.assertFalse(doc["shell"]["telemetry_enabled"])
                self.assertFalse(doc["audio"]["enable_notification_sounds"])

    def test_theme_selects_the_presets_own_palette(self):
        for preset_id in PRESET_IDS:
            preset = noctalia.load_preset(preset_id)
            with self.subTest(preset=preset_id):
                theme = render(preset_id, "frosted")["theme"]
                self.assertEqual("custom", theme["source"])
                self.assertEqual(preset["noctalia"]["palette_id"], theme["custom_palette"])

    def test_font_family_is_left_to_fontconfig(self):
        # An empty string means "inherit"; Task 8 points sans-serif at Inter
        # through fontconfig rather than pinning a family Noctalia may not find.
        self.assertEqual("", self.doc["shell"]["font_family"])


class PaletteContract(unittest.TestCase):
    def test_every_palette_validates_and_carries_both_modes(self):
        for preset_id in PRESET_IDS:
            preset = noctalia.load_preset(preset_id)
            with self.subTest(preset=preset_id):
                document = noctalia.render_palette(preset)
                self.assertEqual([], noctalia.validate_palette(document, SURFACE))
                self.assertEqual({"dark", "light"}, set(document))
                self.assertNotEqual(document["dark"], document["light"])

    def test_each_mode_carries_exactly_the_sixteen_fields_noctalia_reads(self):
        expected = set(SURFACE["palette"]["fields"])
        for preset_id in PRESET_IDS:
            document = noctalia.render_palette(noctalia.load_preset(preset_id))
            for mode in ("dark", "light"):
                with self.subTest(preset=preset_id, mode=mode):
                    colours = {k for k in document[mode] if k != "terminal"}
                    self.assertEqual(expected, colours)

    def test_every_colour_is_a_hex_string(self):
        for preset_id in PRESET_IDS:
            document = noctalia.render_palette(noctalia.load_preset(preset_id))
            for mode in ("dark", "light"):
                for key, value in document[mode].items():
                    if key == "terminal":
                        continue
                    with self.subTest(preset=preset_id, mode=mode, field=key):
                        self.assertRegex(value, HEX)

    def test_terminal_block_covers_the_base_colours_and_both_ansi_groups(self):
        for preset_id in PRESET_IDS:
            terminal = noctalia.render_palette(noctalia.load_preset(preset_id))["dark"]["terminal"]
            with self.subTest(preset=preset_id):
                for field in SURFACE["palette"]["terminal_fields"]:
                    self.assertIn(field, terminal)
                for group in ("normal", "bright"):
                    self.assertEqual(set(SURFACE["palette"]["terminal_ansi"]),
                                     set(terminal[group]))
                    for name, value in terminal[group].items():
                        self.assertRegex(value, HEX, f"{group}.{name}")

    def test_no_palette_colour_is_invented(self):
        """Every emitted colour must exist in the preset, or in its counterpart.

        The counterpart supplies the mode the preset does not have, so its
        colours are legitimate too; anything outside both files would be a value
        the renderer chose for itself.
        """
        for preset_id in PRESET_IDS:
            preset = noctalia.load_preset(preset_id)
            other = noctalia.load_preset(preset["noctalia"]["counterpart"]["preset"])
            pool = {value.lower()
                    for source in (preset, other)
                    for value in re.findall(r"#[0-9a-fA-F]{6,8}", json.dumps(source))}
            document = noctalia.render_palette(preset)
            for mode in ("dark", "light"):
                block = document[mode]
                emitted = {key: [value] for key, value in block.items() if key != "terminal"}
                terminal = block.get("terminal", {})
                emitted["terminal.base"] = [terminal[f]
                                            for f in SURFACE["palette"]["terminal_fields"]]
                for group in SURFACE["palette"]["terminal_groups"]:
                    emitted[f"terminal.{group}"] = list(terminal[group].values())
                for field, colours in sorted(emitted.items()):
                    for colour in colours:
                        with self.subTest(preset=preset_id, mode=mode, field=field):
                            self.assertIn(colour.lower(), pool)

    def test_the_other_mode_comes_from_the_named_counterpart(self):
        for preset_id in PRESET_IDS:
            preset = noctalia.load_preset(preset_id)
            counterpart = preset["noctalia"]["counterpart"]
            with self.subTest(preset=preset_id):
                other = noctalia.load_preset(counterpart["preset"])
                self.assertEqual(counterpart["mode"], other["mode"])
                self.assertNotEqual(preset["mode"], other["mode"])
                document = noctalia.render_palette(preset)
                self.assertEqual(dict(noctalia.palette_mode(other)),
                                 dict(document[counterpart["mode"]]))

    def test_a_missing_counterpart_is_refused(self):
        preset = noctalia.load_preset("midnight-glass")
        del preset["noctalia"]["counterpart"]
        with self.assertRaises((noctalia.NoctaliaError, KeyError)):
            noctalia.render_palette(preset)


class RefusesToWriteUnlessEverythingIsValid(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.env = {**os.environ,
                    "IARCH_CONFIG_DIR": str(self.root / "config"),
                    "IARCH_STATE_DIR": str(self.state)}
        # patch.dict restores the environment exactly on stop. Clearing and
        # re-updating by hand is wrong here: cleanups run last-in-first-out, so
        # a clear() registered before the restore runs after it and leaves
        # later tests with no PATH at all.
        patcher = unittest.mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def targets(self, root: Optional[Path] = None) -> List[Tuple[Path, str]]:
        return noctalia.user_targets(TOKENS, SURFACE, noctalia.load_preset("midnight-glass"),
                                     "frosted", root or (self.root / "noctalia"))

    def test_a_failed_validation_writes_nothing_at_all(self):
        base = self.root / "noctalia"
        original = noctalia.validate
        noctalia.validate = lambda doc, surface: ["shell.corner_roundness: invented"]
        try:
            with self.assertRaises(noctalia.NoctaliaError) as caught:
                self.targets(base)
        finally:
            noctalia.validate = original
        self.assertIn("not valid", str(caught.exception))
        self.assertEqual([], list(base.rglob("*")) if base.exists() else [])

    def test_a_document_that_does_not_parse_is_refused(self):
        original = noctalia.emit_toml
        noctalia.emit_toml = lambda doc, header: "theme = [ unclosed"
        try:
            with self.assertRaises(noctalia.NoctaliaError):
                self.targets()
        finally:
            noctalia.emit_toml = original

    def test_writing_produces_a_config_and_a_palette_under_the_requested_root(self):
        base = self.root / "noctalia"
        written = noctalia.write_all(self.targets(base), self.env)
        self.assertEqual([base / "config.toml",
                          base / "palettes" / "iarch-midnight.json"], written)
        parsed = tomllib.loads((base / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual([], noctalia.validate(parsed, SURFACE))
        palette = json.loads((base / "palettes" / "iarch-midnight.json").read_text(encoding="utf-8"))
        self.assertEqual([], noctalia.validate_palette(
            {k: v for k, v in palette.items() if k != "_generated"}, SURFACE))

    def test_a_failure_part_way_through_leaves_the_filesystem_as_it_was(self):
        base = self.root / "noctalia"
        good = base / "config.toml"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text("previous = true\n", encoding="utf-8")
        blocked = self.root / "blocked" / "palettes" / "iarch-midnight.json"
        blocked.parent.mkdir(parents=True, exist_ok=True)
        # Read and traverse only: atomic_write cannot create its temporary file
        # in here, so the write fails the way a full disk or a read-only mount
        # would.
        os.chmod(blocked.parent, 0o500)
        self.addCleanup(os.chmod, blocked.parent, 0o700)

        with self.assertRaises(OSError):
            noctalia.write_all([(good, "theme = {}\n"), (blocked, "{}")], self.env)

        self.assertEqual("previous = true\n", good.read_text(encoding="utf-8"),
                         "the first file was not restored after the second failed")
        self.assertFalse(blocked.exists())

    def test_an_existing_file_keeps_its_mode_and_gains_a_backup(self):
        base = self.root / "noctalia"
        base.mkdir(parents=True)
        target = base / "config.toml"
        target.write_text("previous = true\n", encoding="utf-8")
        os.chmod(target, 0o640)
        noctalia.write_all([(target, "theme = {}\n")], self.env)
        self.assertEqual(0o640, target.stat().st_mode & 0o777,
                         "an atomic write must not tighten or loosen the user's mode")
        backups = list((self.state / "backups").rglob("*"))
        self.assertTrue([p for p in backups if p.is_file()], "no backup was kept")

    def test_a_newly_created_file_is_readable_by_its_owner_and_not_private(self):
        base = self.root / "noctalia"
        written = noctalia.write_all(self.targets(base), self.env)
        for path in written:
            with self.subTest(path=path.name):
                self.assertTrue(path.stat().st_mode & 0o044,
                                "a rendered payload file must be world-readable")


class ShippedPayload(unittest.TestCase):
    """What the repository ships is the renderer's output, checked in."""

    @classmethod
    def setUpClass(cls):
        cls.config_path = noctalia.REPO_CONFIG
        cls.config_text = cls.config_path.read_text(encoding="utf-8")
        cls.config = tomllib.loads(cls.config_text)

    def test_the_shipped_config_validates_against_the_upstream_surface(self):
        self.assertEqual([], noctalia.validate(self.config, SURFACE))

    def test_the_shipped_config_carries_the_invalid_bar_keys_no_longer(self):
        bar = self.config["bar"]["default"]
        self.assertNotIn("layer", bar)
        self.assertNotIn("radius", bar)

    def test_the_shipped_config_says_where_it_came_from(self):
        self.assertTrue(self.config_text.startswith(configstore.header_for(self.config_path)))
        self.assertIn(SURFACE["verified_against"], self.config_text)
        self.assertIn("midnight-glass", self.config_text)

    def test_the_shipped_palettes_are_exactly_the_presets(self):
        shipped = sorted(p.stem for p in noctalia.REPO_PALETTES.glob("*.json"))
        wanted = sorted(noctalia.load_preset(preset_id)["noctalia"]["palette_id"]
                        for preset_id in PRESET_IDS)
        self.assertEqual(wanted, shipped)

    def test_every_shipped_palette_validates(self):
        for path in sorted(noctalia.REPO_PALETTES.glob("*.json")):
            with self.subTest(palette=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(configstore.GENERATED_HEADER, document["_generated"])
                self.assertEqual([], noctalia.validate_palette(
                    {k: v for k, v in document.items() if k != "_generated"}, SURFACE))

    def test_the_repo_default_is_the_default_preset_at_the_default_intensity(self):
        self.assertEqual(7, len(noctalia.repo_targets(TOKENS, SURFACE)),
                         "one config.toml plus one palette per preset")
        expected = render("midnight-glass", TOKENS["default_intensity"])
        self.assertEqual(flat(expected), flat(self.config))

    def test_every_file_in_the_deployed_payload_is_readable(self):
        unreadable = [
            str(path.relative_to(ROOT))
            for path in (ROOT / ".config").rglob("*")
            if path.is_file() and not path.stat().st_mode & 0o044
        ]
        self.assertEqual([], unreadable,
                         "lib/stage-v5-config.sh copies these with their modes intact")


class CommandLine(unittest.TestCase):
    def run_cli(self, argv: List[str]) -> Tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = noctalia.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_print_writes_a_valid_document_to_stdout(self):
        code, out, err = self.run_cli(["--preset", "aurora", "--intensity", "crystal", "--print"])
        self.assertEqual(0, code, err)
        parsed = tomllib.loads(out)
        self.assertEqual([], noctalia.validate(parsed, SURFACE))

    def test_an_unknown_preset_exits_two_and_says_which_exist(self):
        code, _, err = self.run_cli(["--preset", "vaporwave", "--print"])
        self.assertEqual(2, code)
        self.assertIn("vaporwave", err)

    def test_an_unknown_intensity_exits_two_and_lists_the_real_ones(self):
        code, _, err = self.run_cli(["--intensity", "ultra", "--print"])
        self.assertEqual(2, code)
        for intensity in INTENSITIES:
            self.assertIn(intensity, err)

    def test_output_dir_writes_both_files_where_it_was_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "noctalia"
            env = {**os.environ, "IARCH_STATE_DIR": str(Path(tmp) / "state")}
            with unittest.mock.patch.dict(os.environ, env):
                code, out, err = self.run_cli(["--preset", "frosted-light",
                                               "--output-dir", str(dest)])
            self.assertEqual(0, code, err + out)
            self.assertTrue((dest / "config.toml").is_file())
            self.assertTrue((dest / "palettes" / "iarch-frosted-light.json").is_file())
            self.assertIn("frosted-light", out)

    def test_check_passes_on_the_shipped_payload(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "iarch" / "cli" / "render_noctalia.py"), "--check"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("match a fresh render", result.stdout)

    def test_check_reports_drift_and_points_at_the_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "palettes").mkdir()
            config = root / "config.toml"
            config.write_text(noctalia.rendered_text(
                config, noctalia.emit_toml(render("midnight-glass", TOKENS["default_intensity"]),
                                           noctalia.provenance(
                                               TOKENS, noctalia.load_preset("midnight-glass"),
                                               SURFACE, TOKENS["default_intensity"]))),
                encoding="utf-8")
            for preset_id in PRESET_IDS:
                preset = noctalia.load_preset(preset_id)
                path = root / "palettes" / f"{preset['noctalia']['palette_id']}.json"
                path.write_text(noctalia.rendered_text(
                    path, json.dumps(noctalia.render_palette(preset), indent=2) + "\n"),
                    encoding="utf-8")
            config.write_text(config.read_text(encoding="utf-8") + "\n# hand edited\n",
                              encoding="utf-8")

            with unittest.mock.patch.object(noctalia, "REPO_CONFIG", config), \
                    unittest.mock.patch.object(noctalia, "REPO_PALETTES", root / "palettes"):
                code, out, err = self.run_cli(["--check"])
            self.assertEqual(1, code)
            self.assertIn("config.toml", err)
            self.assertIn("--write-repo-default", err)
            self.assertEqual("", out)

    def test_the_script_runs_on_its_own(self):
        script = ROOT / "iarch" / "cli" / "render_noctalia.py"
        self.assertIn('if __name__ == "__main__":', script.read_text(encoding="utf-8"))
        result = subprocess.run([sys.executable, str(script), "--help"],
                                capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(0, result.returncode, result.stderr)
        for flag in ("--preset", "--intensity", "--print", "--check",
                     "--write-repo-default", "--output-dir"):
            self.assertIn(flag, result.stdout)



class NotificationSurface(unittest.TestCase):
    """The toast settings: what the payload picks, and what the record knows.

    iArch never runs a second notification daemon, so the whole of Part 3's
    notification work is these keys plus the shell's own IPC verbs. The record in
    ``data/design/noctalia.json`` has to be complete even where the payload is
    deliberately silent: filter tables, the legacy blacklist shim and the
    section-level urgency list all exist at v5.4.1, and a later change that
    reaches for one of them must find it already verified rather than invent it.
    """

    # config_schema.cpp:292-372 notificationSchema(), in declaration order,
    # including the three customs and the section-level allowed_urgencies.
    UPSTREAM_KEYS = [
        "enable_daemon", "show_app_name", "show_actions", "position", "layer",
        "scale", "width", "background_opacity", "border", "border_color",
        "border_width", "follow_focused_output", "offset_x", "offset_y",
        "monitors", "collapse_on_dismiss", "keep_dismissed_in_history",
        "history_retention_hours", "max_visible", "blacklist",
        "blacklist_allow_critical", "filter_order", "filter", "allowed_urgencies",
    ]

    # config_schema.cpp:247-291 notificationFilterSchema(), same rule.
    UPSTREAM_FILTER_KEYS = [
        "enabled", "matches", "match", "match_content", "show_toast",
        "save_history", "play_sound", "bypass_dnd", "allow_permanent",
        "override_duration", "allowed_urgencies", "allow_critical",
    ]

    def setUp(self):
        self.keys = SURFACE["sections"]["notification"]["keys"]
        self.filter_section = SURFACE["sections"]["notification.filter"]
        self.doc = render(noctalia.DEFAULT_PRESET, TOKENS["default_intensity"])
        self.notification = self.doc["notification"]

    def test_the_record_covers_every_setting_upstream_declares(self):
        self.assertEqual(sorted(self.UPSTREAM_KEYS), sorted(self.keys))

    def test_the_filter_table_is_recorded_as_a_table_and_as_its_own_section(self):
        self.assertEqual("notificationFilterSchema", self.keys["filter"]["table"])
        self.assertEqual("notificationFilterSchema", self.filter_section["schema"])
        # One definition, two ways in: a sub-table of [notification] and a
        # section of its own, so either spelling validates the same keys.
        self.assertEqual(self.keys["filter"]["keys"], self.filter_section["keys"])
        self.assertEqual(sorted(self.UPSTREAM_FILTER_KEYS),
                         sorted(self.filter_section["keys"]))

    def test_the_two_keys_upstream_accepts_and_ignores_say_so(self):
        for key in ("blacklist_allow_critical", "allow_critical"):
            spec = (self.keys if key == "blacklist_allow_critical"
                    else self.filter_section["keys"])[key]
            with self.subTest(setting=key):
                self.assertIn("ignored", spec["note"],
                              "a no-op key has to be recorded as one, or someone "
                              "will wire a setting to it")

    def test_the_payload_emits_no_filter_tables(self):
        # A filter needs a real sender to match. Inventing one would ship a rule
        # that silently swallows somebody's notifications.
        self.assertNotIn("filter", self.notification)
        for key, value in self.notification.items():
            with self.subTest(setting=key):
                self.assertNotIsInstance(value, dict, f"{key} would render a sub-table")

    def test_the_keys_left_unemitted_are_still_recorded(self):
        unused = [key for key in self.UPSTREAM_KEYS if key not in self.notification]
        self.assertEqual(
            sorted(["blacklist", "blacklist_allow_critical", "filter_order",
                    "filter", "allowed_urgencies"]), sorted(unused))
        for key in unused:
            with self.subTest(setting=key):
                self.assertIn("note", self.keys[key],
                              "a key we choose not to emit still needs its reason recorded")

    def test_the_margin_is_one_number_on_both_axes(self):
        self.assertEqual(16, self.notification["offset_x"])
        self.assertEqual(self.notification["offset_x"], self.notification["offset_y"])
        for key in ("offset_x", "offset_y"):
            with self.subTest(setting=key):
                self.assertIsInstance(self.notification[key], int)
                self.assertGreaterEqual(self.notification[key], 0)
                self.assertIn("note", self.keys[key],
                              "offset_x and offset_y are not applied the same way "
                              "upstream, and the difference has to be written down")

    def test_toasts_stay_on_the_output_they_appeared_on(self):
        self.assertIs(False, self.notification["follow_focused_output"])
        self.assertEqual([], self.notification["monitors"])

    def test_the_stack_is_capped_and_history_is_kept_for_a_week(self):
        self.assertIs(True, self.notification["collapse_on_dismiss"])
        self.assertIs(True, self.notification["keep_dismissed_in_history"])
        self.assertEqual(4, self.notification["max_visible"])
        self.assertEqual(168, self.notification["history_retention_hours"])
        for key in ("max_visible", "history_retention_hours"):
            with self.subTest(setting=key):
                low, high = self.keys[key]["range"][:2]
                self.assertLessEqual(low, self.notification[key])
                self.assertLessEqual(self.notification[key], high)

    def test_the_corner_it_sits_in_and_the_layer_it_sits_on(self):
        self.assertEqual("top_right", self.notification["position"])
        self.assertEqual("top", self.notification["layer"])
        self.assertIs(True, self.notification["enable_daemon"],
                      "the shell's own daemon is the only one iArch allows")

    def test_the_recorded_position_values_are_the_documented_six(self):
        note = self.keys["position"]["note"]
        for value in ("top_right", "top_left", "top_center",
                      "bottom_right", "bottom_left", "bottom_center"):
            with self.subTest(position=value):
                self.assertIn(value, note)
        # It is a plain string field upstream, so the record must not claim an
        # enum that notificationSchema() does not enforce.
        self.assertNotIn("enum", self.keys["position"])
        self.assertNotIn("enum", self.keys["layer"])

    def test_every_combination_keeps_the_toast_settings_inside_their_bounds(self):
        for preset_id, intensity in COMBINATIONS:
            with self.subTest(preset=preset_id, intensity=intensity):
                doc = render(preset_id, intensity)
                problems = [line for line in noctalia.validate(doc, SURFACE)
                            if line.startswith("notification")]
                self.assertEqual([], problems)


class ControlCenterPanel(unittest.TestCase):
    """The Super+I panel: what it can hold, and what it cannot.

    Noctalia's control centre is a fixed set of tabs and a row of at most six
    shortcut buttons drawn from a closed vocabulary. There is no custom tile and no
    custom slider in v5.4.1, so the honest work is to fill the six slots with the
    types that really exist, to refuse a type that would render no button at all,
    and to record the one place a config file *can* add a button that runs a
    command of ours -- ``[[shell.session.actions]]`` -- without emitting a command
    line this project has no business inventing.
    """

    # config_schema.cpp:551-569 controlCenterSchema(), in declaration order.
    UPSTREAM_KEYS = [
        "sidebar", "sidebar_section", "width", "show_shortcut_labels",
        "show_session_button", "circular_avatar", "show_avatar_border",
        "hidden_tabs", "calendar", "media", "shortcuts",
    ]

    # config_schema.cpp:1772-1784 shellSessionSchema() and :1674-1746
    # sessionActionSchema(), cross-checked against docs/user/configuration/shell.mdx.
    SESSION_KEYS = ["grid", "grid_columns", "show_shortcuts", "actions", "power"]
    ACTION_KEYS = ["action", "enabled", "command", "label", "glyph", "shortcut",
                   "lockscreen_shortcut", "countdown_seconds", "variant"]

    def setUp(self):
        self.keys = SURFACE["sections"]["control_center"]["keys"]
        self.session = SURFACE["sections"]["shell"]["keys"]["session"]
        self.doc = render(noctalia.DEFAULT_PRESET, TOKENS["default_intensity"])
        self.panel = self.doc["control_center"]

    def test_the_record_covers_every_setting_upstream_declares(self):
        self.assertEqual(sorted(self.UPSTREAM_KEYS), sorted(self.keys))

    def test_the_session_panel_command_hook_is_recorded(self):
        self.assertEqual("shellSessionSchema", self.session["table"])
        self.assertEqual(sorted(self.SESSION_KEYS), sorted(self.session["keys"]))
        actions = self.session["keys"]["actions"]
        self.assertEqual("sessionActionSchema", actions["table"])
        self.assertEqual(sorted(self.ACTION_KEYS), sorted(actions["keys"]))
        self.assertIn("/bin/sh -c", actions["keys"]["command"]["note"])
        self.assertEqual("array", actions["type"], "it is [[shell.session.actions]]")

    def test_the_variant_enum_carries_six_values_and_says_the_docs_list_five(self):
        variant = self.session["keys"]["actions"]["keys"]["variant"]
        self.assertEqual(6, len(variant["enum"]))
        self.assertEqual("kSessionActionButtonVariants", variant["enum_constant"])
        self.assertIn("ghost", variant["enum_note"])

    def test_no_session_action_is_emitted_because_no_command_is_ours_to_invent(self):
        self.assertNotIn("session", self.doc["shell"])
        self.assertIn("no business inventing", self.session["keys"]["power"]["note"])

    def test_the_shortcut_row_fills_the_six_slots_the_home_tab_shows(self):
        types = [entry["type"] for entry in self.panel["shortcuts"]]
        self.assertEqual(6, len(types), "Home shows at most six")
        self.assertEqual(len(types), len(set(types)), "a repeated tile wastes a slot")
        allowed = self.keys["shortcuts"]["keys"]["type"]["enum"]
        for name in types:
            with self.subTest(shortcut=name):
                self.assertIn(name, allowed)

    def test_the_tiles_the_brief_asks_for_and_upstream_has_are_present(self):
        types = [entry["type"] for entry in self.panel["shortcuts"]]
        for wanted in ("wifi", "bluetooth", "notification", "nightlight"):
            with self.subTest(shortcut=wanted):
                self.assertIn(wanted, types)

    def test_no_tile_is_emitted_for_something_that_would_render_nothing(self):
        types = [entry["type"] for entry in self.panel["shortcuts"]]
        # Airplane mode, game mode, focus mode and a screenshot button have no
        # type at all; screen_recorder exists but stays disabled without the
        # official plugin, which is a dead button by another name.
        for absent in ("airplane", "game", "focus", "screenshot", "screen_recorder"):
            with self.subTest(shortcut=absent):
                self.assertNotIn(absent, types)

    def test_an_invented_tile_is_refused_rather_than_shipped_as_a_dead_button(self):
        doc = render(noctalia.DEFAULT_PRESET, TOKENS["default_intensity"])
        doc["control_center"]["shortcuts"] = [{"type": "airplane"}]
        problems = noctalia.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("airplane", problems[0])
        self.assertIn("is not one of", problems[0])

    def test_a_shortcut_entry_carries_the_one_field_it_has(self):
        doc = render(noctalia.DEFAULT_PRESET, TOKENS["default_intensity"])
        doc["control_center"]["shortcuts"] = [{"type": "wifi", "label": "Wireless"}]
        problems = noctalia.validate(doc, SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("no such setting", problems[0])

    def test_the_visualizer_follows_the_motion_switch_and_actually_varies(self):
        seen = set()
        for intensity in INTENSITIES:
            with self.subTest(intensity=intensity):
                doc = render(noctalia.DEFAULT_PRESET, intensity)
                expected = bool(TOKENS["intensities"][intensity]["motion"]["enabled"])
                self.assertEqual(expected, doc["control_center"]["media"]["show_visualizer"])
                seen.add(expected)
        self.assertEqual({True, False}, seen,
                         "a key that never changes is a key that does nothing")

    def test_the_calendar_card_shows_what_is_next_not_what_already_happened(self):
        calendar = self.panel["calendar"]
        self.assertIs(True, calendar["show_events_card"])
        self.assertIs(True, calendar["hide_past_events"])
        threshold = calendar["past_events_threshold_minutes"]
        low, high, step = self.keys["calendar"]["keys"]["past_events_threshold_minutes"]["range"]
        self.assertLessEqual(low, threshold)
        self.assertLessEqual(threshold, high)
        self.assertEqual(0, threshold % step)
        self.assertGreater(threshold, 0, "zero would hide an event that just started")

    def test_the_panel_is_wide_enough_and_every_tab_stays_reachable(self):
        low, high, step = self.keys["width"]["range"]
        width = self.panel["width"]
        self.assertLessEqual(low, width)
        self.assertLessEqual(width, high)
        self.assertEqual(0, (width - low) % step)
        self.assertEqual([], self.panel["hidden_tabs"])
        self.assertEqual("full", self.panel["sidebar"])
        self.assertEqual("compact", self.panel["sidebar_section"])

    def test_an_array_of_tables_renders_as_repeated_double_bracket_blocks(self):
        text = noctalia.emit_toml(self.doc, "# header")
        self.assertEqual(6, text.count("[[control_center.shortcuts]]"))
        self.assertIn('type = "wifi"', text)
        # An empty list is a setting of its own upstream, so it stays inline
        # rather than becoming a table with no entries.
        self.assertIn("hidden_tabs = []", text)
        self.assertNotIn("[[control_center.hidden_tabs]]", text)

    def test_a_plain_array_and_a_table_array_are_not_confused(self):
        self.assertTrue(noctalia.is_table_array([{"type": "wifi"}]))
        self.assertFalse(noctalia.is_table_array([]))
        self.assertFalse(noctalia.is_table_array(["monitor"]))
        self.assertFalse(noctalia.is_table_array([{"a": 1}, "b"]))


if __name__ == "__main__":
    unittest.main()
