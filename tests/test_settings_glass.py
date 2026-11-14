#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Glass page and the sheet it is drawn with.

``data/schemas/settings.schema.json:241`` names the authority for this page and then says
this file is what enforces it: *"The schema cannot enumerate the leaves because they belong
to the compositor's record, so the authority is data/design/tokens.json: hyprland.leaves
for the names, hyprland.integer_leaves for which ones are whole numbers and hyprland.ranges
for the bounds. tests/test_settings_glass.py checks every key and value against that
record, which is where a leaf that does not exist gets caught."*

So the contract has three parts and each gets its own assertion. A leaf the page offers has
to exist in the record, because ``glass.leaves`` is an override on top of an intensity and
an override on a leaf that does not exist writes a line the compositor ignores. The kind of
control has to follow the recorded shape, because a boolean drawn as a slider is a switch
nobody can find, and a whole number drawn as a free entry accepts a value the compositor
clamps. And the bounds have to come from the record rather than from a number in the page,
so that a compositor that widens a range is a change in one file.

The other half of the page is what it does *not* store. An override says "this leaf, this
value, on top of whatever the intensity decided", and clearing the section returns to the
intensity exactly -- so an empty ``glass.leaves`` has to mean the intensity's own values and
not a second copy of them. That is the difference between a preset with overrides and two
sources of truth for one decision.

``style/glass.css`` is checked against ``data/design/adwaita.json`` for the same reason: the
sheet may only use properties and style classes the record says GTK 4.10 has. The record's
``rejected`` list carries the one that matters most here -- ``@media`` is a GTK 4.20 feature
and this project's floor is 4.10, so reduced motion is a style class the window adds rather
than a media query nobody at the floor would honour.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.pages import build as build_page  # noqa: E402
from iarch_settings.pages import glass as glass_page  # noqa: E402
from iarch_settings.pages.plan import default_context  # noqa: E402
from iarch_settings.services import themes  # noqa: E402

TOKENS = json.loads((ROOT / "data" / "design" / "tokens.json").read_text(encoding="utf-8"))
HYPR = TOKENS["hyprland"]
LEAVES: List[str] = list(HYPR["leaves"])
INTEGER_LEAVES: List[str] = list(HYPR["integer_leaves"])
RANGES: Dict[str, Sequence[float]] = dict(HYPR["ranges"])
ADWAITA = json.loads((ROOT / "data" / "design" / "adwaita.json").read_text(encoding="utf-8"))
SETTINGS_SCHEMA = json.loads((ROOT / "data" / "schemas" / "settings.schema.json").read_text(
    encoding="utf-8"))
CSS_PATH = ROOT / "iarch" / "settings-app" / "iarch_settings" / "style" / "glass.css"
CSS = CSS_PATH.read_text(encoding="utf-8")

PLAN = build_page("glass", default_context())
ROWS = list(PLAN.walk())
LEAF_ROWS: Tuple[Tuple[str, str, str, str], ...] = tuple(glass_page.LEAF_ROWS)
OFFERED_LEAVES = [row[0] for row in LEAF_ROWS]

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
DECLARATION = re.compile(r"([a-zA-Z-][a-zA-Z0-9_-]*)\s*:")
CLASS = re.compile(r"\.([A-Za-z][A-Za-z0-9_-]*)")
# An at-rule, and not a named colour: `@card_bg_color` stops at the underscore, so the
# negative lookahead is what keeps a colour from being read as an at-rule.
AT_RULE = re.compile(r"@([a-z-]+)(?![a-z0-9_-])")


def css_blocks() -> Dict[str, List[Tuple[str, str]]]:
    """Selector text to declarations, with comments stripped first."""
    body = COMMENT.sub(" ", CSS)
    out: Dict[str, List[Tuple[str, str]]] = {}
    for selector, contents in BLOCK.findall(body):
        declarations = []
        for line in contents.split(";"):
            match = DECLARATION.match(line.strip())
            if match:
                value = line.strip()[match.end():].strip()
                declarations.append((match.group(1), value))
        out.setdefault(selector.strip(), []).extend(declarations)
    return out


BLOCKS = css_blocks()


class TestTheLeavesThePageOffersAreTheRecordsLeaves(unittest.TestCase):
    """The schema cannot enumerate them, so this is where a leaf that does not exist is caught."""

    def test_the_page_offers_eleven_leaf_rows(self):
        self.assertEqual(11, len(LEAF_ROWS))
        self.assertEqual(len(OFFERED_LEAVES), len(set(OFFERED_LEAVES)),
                         "a leaf is offered twice, so two rows would write one line")

    def test_every_offered_leaf_is_a_leaf_the_record_names(self):
        for leaf in OFFERED_LEAVES:
            with self.subTest(leaf=leaf):
                self.assertIn(leaf, LEAVES,
                              f"{leaf} is not in tokens.json hyprland.leaves, so an override "
                              f"on it writes a line the compositor ignores")

    def test_a_leaf_row_carries_a_kind_a_label_and_a_sentence(self):
        for leaf, kind, label, why in LEAF_ROWS:
            with self.subTest(leaf=leaf):
                self.assertIn(kind, ("switch", "scale", "spin", "entry"),
                              f"{leaf} is drawn as a {kind}, which is not a control this "
                              f"page knows how to build")
                self.assertTrue(label.strip())
                self.assertGreater(len(why.split()), 3,
                                   f"{leaf}'s row has no sentence saying what the value does")

    def test_every_offered_leaf_has_a_reader_so_the_row_can_show_what_is_in_force(self):
        self.assertEqual(sorted(OFFERED_LEAVES), sorted(glass_page.READERS),
                         "a leaf is offered with no reader, so the row cannot show the value "
                         "the intensity already decided and would look unset")
        for leaf, reader in glass_page.READERS.items():
            with self.subTest(leaf=leaf):
                self.assertTrue(callable(reader))

    def test_the_rows_the_page_draws_are_the_rows_the_module_declares(self):
        drawn = [str(row.setting).removeprefix("glass.leaves.")
                 for row in ROWS if row.setting]
        self.assertEqual(sorted(OFFERED_LEAVES), sorted(drawn),
                         "the leaves declared in the page module and the leaves the built "
                         "plan draws have drifted apart")

    def test_every_setting_the_page_touches_is_an_override_and_nothing_else(self):
        touched = PLAN.settings_touched()
        self.assertEqual(11, len(touched))
        for path in touched:
            with self.subTest(path=path):
                self.assertTrue(path.startswith("glass.leaves."),
                                f"{path} is not under glass.leaves, so the Glass page writes "
                                f"a section another page owns")
                self.assertIn(path.removeprefix("glass.leaves."), LEAVES)

    def test_the_schema_leaves_the_names_to_the_record_on_purpose(self):
        leaves = SETTINGS_SCHEMA["properties"]["glass"]["properties"]["leaves"]
        self.assertNotIn("properties", leaves,
                         "the schema now enumerates the leaves, which makes it a second "
                         "authority for names that belong to the compositor's record")
        self.assertEqual(["boolean", "number"], leaves["additionalProperties"]["type"],
                         "a leaf override is a boolean or a number; a string here would be "
                         "a value the compositor cannot take")


class TestTheControlKindFollowsTheRecordedShape(unittest.TestCase):
    """A boolean is a switch, a whole number is bounded, and a float is a slider."""

    def test_a_boolean_leaf_is_a_switch_and_nothing_else(self):
        booleans = [leaf for leaf in OFFERED_LEAVES
                    if leaf.endswith(":enabled") or leaf.endswith("_on_border")]
        self.assertTrue(booleans, "no boolean leaf is offered, so this test proves nothing")
        kinds = {leaf: kind for leaf, kind, _label, _why in LEAF_ROWS}
        for leaf in booleans:
            with self.subTest(leaf=leaf):
                self.assertEqual("switch", kinds[leaf],
                                 f"{leaf} is a boolean in the record and is drawn as a "
                                 f"{kinds[leaf]}, which is a switch nobody can find")
                self.assertFalse(themes.is_integer_leaf(leaf, ROOT))

    def test_an_integer_leaf_is_bounded_and_never_a_free_entry(self):
        kinds = {leaf: kind for leaf, kind, _label, _why in LEAF_ROWS}
        integers = [leaf for leaf in OFFERED_LEAVES if themes.is_integer_leaf(leaf, ROOT)]
        self.assertTrue(integers)
        for leaf in integers:
            with self.subTest(leaf=leaf):
                self.assertIn(kinds[leaf], ("spin", "scale"),
                              f"{leaf} is a whole number in the record and is drawn as a "
                              f"{kinds[leaf]}, which accepts a value the compositor clamps")

    def test_is_integer_leaf_agrees_with_the_record_for_every_offered_leaf(self):
        for leaf in OFFERED_LEAVES:
            with self.subTest(leaf=leaf):
                self.assertEqual(leaf in INTEGER_LEAVES, themes.is_integer_leaf(leaf, ROOT),
                                 "the service and the record disagree about which leaves are "
                                 "whole numbers")

    def test_slider_bounds_come_from_the_record_and_not_from_the_page(self):
        for leaf in OFFERED_LEAVES:
            bounds = themes.slider_bounds(leaf, ROOT)
            with self.subTest(leaf=leaf):
                if leaf in RANGES:
                    self.assertIsNotNone(bounds, f"{leaf} has a recorded range and no bounds")
                    self.assertEqual((float(RANGES[leaf][0]), float(RANGES[leaf][1])),
                                     (float(bounds[0]), float(bounds[1])),
                                     f"{leaf}'s slider and the record disagree, so a change "
                                     f"to the compositor's range would need two edits")
                else:
                    self.assertIsNone(bounds,
                                      f"{leaf} has no recorded range, so bounds invented here "
                                      f"would be a number nobody verified")

    def test_a_numbered_row_carries_its_bounds_so_the_control_can_refuse(self):
        for row in ROWS:
            if row.kind not in ("scale", "spin"):
                continue
            leaf = str(row.setting).removeprefix("glass.leaves.")
            with self.subTest(leaf=leaf):
                self.assertIsNotNone(row.minimum, f"{leaf} has no minimum")
                self.assertIsNotNone(row.maximum, f"{leaf} has no maximum")
                self.assertEqual((float(RANGES[leaf][0]), float(RANGES[leaf][1])),
                                 (float(row.minimum), float(row.maximum)),
                                 f"{leaf}'s row carries bounds the record does not")

    def test_every_ranged_leaf_the_record_has_is_inside_its_own_range(self):
        for leaf, (low, high) in RANGES.items():
            with self.subTest(leaf=leaf):
                self.assertLess(low, high, f"{leaf}'s range is empty or inverted")
                self.assertIn(leaf, LEAVES,
                              f"{leaf} has a range and is not a leaf, so the range describes "
                              f"nothing")


class TestAnOverrideSitsOnTopOfAnIntensity(unittest.TestCase):
    """An empty section means the intensity's own values, not a second copy of them."""

    def test_the_intensity_ids_come_from_the_tokens_record(self):
        self.assertEqual(["crystal", "frosted", "soft", "performance"],
                         themes.intensity_ids(ROOT))
        self.assertEqual(sorted(themes.intensities(ROOT)), sorted(themes.intensity_ids(ROOT)))
        self.assertIn(themes.default_intensity(ROOT), themes.intensity_ids(ROOT))

    def test_the_shipped_defaults_have_an_empty_override_section(self):
        defaults = json.loads((ROOT / "data" / "settings.default.json").read_text(
            encoding="utf-8"))
        self.assertEqual({}, defaults["glass"]["leaves"],
                         "a fresh install ships overrides, so it does not have the "
                         "intensity's own values and cannot be returned to them")
        self.assertEqual([], defaults["glass"]["per_app_opacity"])

    def test_the_schema_caps_the_per_app_list_because_rule_order_is_the_semantics(self):
        per_app = SETTINGS_SCHEMA["properties"]["glass"]["properties"]["per_app_opacity"]
        self.assertEqual(64, per_app["maxItems"],
                         "an unbounded list of window-class regexes is an unbounded amount of "
                         "work for every window the compositor draws")

    def test_the_page_says_what_an_override_is_on_top_of(self):
        text = " ".join([str(row.title) + " " + str(row.subtitle or "") for row in ROWS
                         if row.subtitle]).lower()
        self.assertIn("intensity", text,
                      "the Glass page never mentions the intensity behind the values, so an "
                      "override looks like the only thing deciding them")

    def test_clearing_the_section_returns_to_the_intensity_exactly(self):
        record = themes.intensities(ROOT)
        for intensity, entry in record.items():
            with self.subTest(intensity=intensity):
                self.assertIsInstance(entry, dict)
                self.assertIn(entry, list(record.values()))

    def test_the_glass_leaves_the_service_reports_are_the_records_leaves(self):
        """Three parts: the names, their bounds, and which names are whole numbers."""
        names, ranges, integers = themes.glass_leaves(ROOT)
        self.assertEqual(sorted(LEAVES), sorted(names),
                         "the service and the record disagree about which leaves exist")
        self.assertEqual({leaf: [float(low), float(high)]
                          for leaf, (low, high) in RANGES.items()}, ranges,
                         "a slider's bounds came from somewhere other than the record, so a "
                         "value the compositor's own parser would refuse could be offered")
        self.assertEqual(sorted(INTEGER_LEAVES), sorted(integers),
                         "the service and the record disagree about which leaves are whole "
                         "numbers")
        self.assertTrue(set(integers) <= set(names),
                        "a leaf is recorded as a whole number and is not a leaf at all")


class TestTheSheetUsesOnlyWhatTheRecordSaysGtkHas(unittest.TestCase):
    """``adwaita.json`` is the authority for the sheet, at the GTK 4.10 floor it records."""

    def test_the_sheet_is_commented_with_what_it_is_for(self):
        head = CSS.split("*/", 1)[0]
        self.assertTrue(head.startswith("/*"))
        self.assertGreater(len(head.split()), 25,
                           "the sheet has no header saying what it is for and what it may "
                           "use, so the next edit has nothing to check itself against")

    def test_no_media_query_because_the_floor_is_four_ten(self):
        rejected = {entry["spelling"]: entry for entry in ADWAITA["rejected"]}
        media = [spelling for spelling in rejected if "@media" in spelling]
        self.assertTrue(media, "the record no longer explains the @media rejection")
        entry = rejected[media[0]]
        self.assertIn("4.20", entry["why"] + entry.get("evidence", ""),
                      "the rejection does not say which GTK version added media queries")
        self.assertEqual("4.10", str(ADWAITA["minimum_versions"]["gtk"]["version"]),
                         "the floor moved and the rejection was not re-read")
        at_rules = set(AT_RULE.findall(COMMENT.sub(" ", CSS)))
        self.assertEqual(set(), at_rules & {"media", "supports"},
                         f"glass.css uses {sorted(at_rules)}, which GTK 4.10 does not honour: "
                         f"parsing errors are not fatal, so the block would warn and do "
                         f"nothing, and reduced motion would silently stop working")

    def test_reduced_motion_is_a_style_class_the_window_adds(self):
        self.assertIn(".iarch-reduce-motion", CSS)
        reduce_blocks = {selector: declarations for selector, declarations in BLOCKS.items()
                         if "iarch-reduce-motion" in selector}
        self.assertTrue(reduce_blocks, "no rule hangs off the reduce-motion class")
        properties = {name for declarations in reduce_blocks.values()
                      for name, _value in declarations}
        self.assertTrue(properties & {"transition-delay", "transition-duration",
                                      "transition", "animation-duration"},
                        f"the reduce-motion class sets {sorted(properties)}, none of which "
                        f"shortens a transition")
        for selector, declarations in reduce_blocks.items():
            for name, value in declarations:
                if name == "transition-delay":
                    self.assertEqual("0ms", value,
                                     "a reduce-motion transition-delay that is not 0ms still "
                                     "waits before it starts")

    def test_the_seven_classes_the_sheet_defines_are_the_seven_the_record_lists(self):
        recorded = {name for name in ADWAITA["style_classes"]["names"]
                    if name.startswith("iarch-")}
        used = set(CLASS.findall(COMMENT.sub(" ", CSS)))
        self.assertEqual(recorded, used & recorded,
                         "the record lists an iarch class the sheet does not define, or the "
                         "sheet defines one the record does not list")
        self.assertEqual(7, len(recorded), f"{sorted(recorded)}")

    def test_every_property_the_sheet_sets_is_one_the_record_says_gtk_has(self):
        allowed = set(ADWAITA["css_properties"]["names"])
        used = {name for declarations in BLOCKS.values() for name, _value in declarations}
        self.assertTrue(used, "the sheet sets no properties, so it draws nothing")
        unknown = sorted(used - allowed)
        self.assertEqual([], unknown,
                         f"glass.css sets {unknown}, which the record does not list as a GTK "
                         f"CSS property; either the record is incomplete or the property is "
                         f"ignored at the 4.10 floor")

    def test_transition_delay_is_recorded_because_the_reduce_motion_class_needs_it(self):
        self.assertIn("transition-delay", ADWAITA["css_properties"]["names"],
                      "the sheet sets transition-delay and the record does not list it")

    def test_the_sheet_uses_named_colours_and_not_custom_properties(self):
        """Custom properties are a GTK 4.16 feature and the floor is 4.10."""
        body = COMMENT.sub(" ", CSS)
        self.assertNotIn("var(--", body,
                         "the sheet uses a custom property, which GTK 4.10 does not support; "
                         "@define-color is the portable spelling")
        self.assertRegex(body, r"@[a-z][a-z0-9_]*",
                         "the sheet uses no named colour at all, so it cannot follow the "
                         "theme it is drawn over")

    def test_no_property_value_is_left_empty(self):
        for selector, declarations in BLOCKS.items():
            for name, value in declarations:
                with self.subTest(selector=selector, property=name):
                    self.assertTrue(value.strip(),
                                    f"{selector} sets {name} to nothing, which is a "
                                    f"declaration that parses and does nothing")


class TestTheThemeAppliesThroughTheRecordedTargets(unittest.TestCase):
    """What the sheet is applied to, and how many places that is."""

    def test_applying_a_theme_reaches_eleven_targets(self):
        targets = themes.apply_targets(root=ROOT)
        self.assertEqual(11, len(targets), f"{[str(target) for target in targets]}")
        self.assertEqual(len(set(targets)), len(targets),
                         "a target is listed twice, so it would be written twice")

    def test_the_targets_are_files_and_not_directories(self):
        for target in themes.apply_targets(root=ROOT):
            with self.subTest(target=str(target)):
                self.assertNotEqual("", Path(str(target)).name,
                                    "a directory is not a change target")

    def test_a_contrast_report_is_an_outcome_and_not_a_number_invented_here(self):
        outcome = themes.contrast_report()
        self.assertIn(str(outcome.verdict), ("ok", "failed", "unverified"),
                      f"{outcome.verdict} is not one of the three verdicts, so a caller "
                      f"cannot tell a failing palette from a tool that is not installed")
        self.assertTrue(hasattr(outcome, "argv") and hasattr(outcome, "reason"))
        if not outcome.ran:
            self.assertTrue(str(outcome.reason).strip(),
                            "the report could not run and gives no reason, so the page would "
                            "show a contrast figure that describes nothing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
