#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Display page's contract with the compositor's monitor record.

``data/design/monitors.json`` records two directions and they are not the same list.
The read side is what ``hyprctl -j monitors`` answers: 38 fields. The write side is what
``hl.monitor`` accepts: 23 fields, of which **six** are written by this project --
``output``, ``mode``, ``position``, ``scale``, ``transform`` and ``disabled``. The other
seventeen are things a monitor reports about itself, and writing one would be writing a
claim about hardware.

The Display page is the one place in this application where a wrong answer can leave a
person without a usable screen, so three properties get their own assertions:

* a field the page writes is a field the record marks ``written_by_this_project``, so a
  capability the compositor does not have cannot be offered as a control;
* ``scale`` is a **string**, because that is what the rule parser takes, and a page that
  wrote a number would be relying on the compositor to coerce it;
* the revert window is recorded and is the reason the change is applied and then confirmed
  rather than confirmed and then applied -- a confirmation dialog drawn over a session that
  is already running an unreadable mode is a confirmation the person cannot read.

The list builders in ``services/control.py`` are asserted here too, because they are where
a half-typed path becomes a monitor: an index that names no monitor is refused, and a new
monitor is accepted only as a whole entry. A builder that answered
``display.monitors.0.scale`` on an empty list by appending ``{"output": "1.5"}`` would
create a monitor whose *output* is a scale factor, and the later refusal would blame the
entry rather than the request.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.pages import build as build_page  # noqa: E402
from iarch_settings.pages import plan as plan_module  # noqa: E402
from iarch_settings.services import control  # noqa: E402

RECORD = json.loads((ROOT / "data" / "design" / "monitors.json").read_text(encoding="utf-8"))
WRITE_FIELDS: List[Dict[str, Any]] = RECORD["write"]["fields"]
READ_FIELDS: List[Dict[str, Any]] = RECORD["read"]["fields"]
WRITTEN = [field["name"] for field in WRITE_FIELDS if field.get("written_by_this_project")]
NOT_WRITTEN = [field["name"] for field in WRITE_FIELDS
               if not field.get("written_by_this_project")]
SAFETY = RECORD["safety"]
PAYLOAD = RECORD["payload"]

CONTEXT = plan_module.default_context()
PLAN = build_page("display", CONTEXT)


def plan_text() -> str:
    """Every string the Display page draws, so a claim can be looked for in it."""
    parts = [PLAN.title, PLAN.description or ""]
    for row in PLAN.walk():
        parts += [row.title, row.subtitle or "", row.confirm or "", row.confirm_body or ""]
        parts += [str(choice) for choice in row.choices or ()]
    for banner in PLAN.banners:
        parts.append(banner.text)
    return " ".join(part for part in parts if part)


class TestTheRecordSplitsReadFromWrite(unittest.TestCase):
    """Two lists, and the difference between them is the point."""

    def test_six_fields_are_written_and_seventeen_are_not(self):
        self.assertEqual(23, len(WRITE_FIELDS))
        self.assertEqual(6, len(WRITTEN))
        self.assertEqual(17, len(NOT_WRITTEN))
        self.assertEqual({"output", "mode", "position", "scale", "transform", "disabled"},
                         set(WRITTEN))

    def test_the_read_side_is_larger_than_the_write_side(self):
        self.assertGreater(len(READ_FIELDS), len(WRITE_FIELDS),
                           "a monitor reports more about itself than the compositor accepts "
                           "back, and a record that says otherwise has conflated the two")

    def test_the_service_writes_exactly_the_six_the_record_marks(self):
        self.assertEqual(sorted(WRITTEN), sorted(control._monitor_fields()),
                         "the fields control.py will accept and the fields the record marks "
                         "written_by_this_project are two copies of one decision")

    def test_every_written_field_carries_an_evidence_line_and_a_way_to_render_it(self):
        """The record gives each field the shape its parser has, and each shape is renderable."""
        for field in WRITE_FIELDS:
            with self.subTest(field=field["name"]):
                self.assertTrue(str(field.get("evidence") or "").strip())
                self.assertTrue(str(field.get("type") or "").strip())
                if field.get("written_by_this_project"):
                    has_choices = bool(field.get("accepted"))
                    has_bounds = "minimum" in field and "maximum" in field
                    self.assertTrue(has_choices or has_bounds or
                                    str(field.get("note") or "").strip(),
                                    "a field this project writes carries no note, no accepted "
                                    "list and no range, so the page has nothing to render from")

    def test_a_field_marked_not_written_says_why_in_the_refusal_block(self):
        refused = " ".join(str(entry.get("field") or "")
                           for entry in RECORD["refused_by_this_project"])
        for name in ("reserved", "mirror", "bitdepth", "icc", "vrr"):
            with self.subTest(field=name):
                self.assertIn(name, NOT_WRITTEN)
                self.assertIn(name, refused,
                              f"{name} is not written and the record does not say why, so a "
                              f"person asking for it gets a shrug")

    def test_a_refusal_carries_a_reason_a_person_can_read(self):
        for entry in RECORD["refused_by_this_project"]:
            with self.subTest(field=entry.get("field")):
                self.assertGreater(len(str(entry.get("why") or "").split()), 10,
                                   "a refusal whose reason is one clause is a citation, not "
                                   "an explanation")


class TestScaleIsAStringAndTheOtherShapesAreTheirs(unittest.TestCase):
    """The shapes the rule parser takes, which are not the shapes a page would guess."""

    def test_scale_is_a_string_because_that_is_what_the_parser_takes(self):
        field = next(item for item in WRITE_FIELDS if item["name"] == "scale")
        self.assertEqual("string", field["type"],
                         "a page that wrote a number for scale would be relying on the "
                         "compositor to coerce it")

    def test_transform_is_a_whole_number_in_the_range_the_parser_declares(self):
        field = next(item for item in WRITE_FIELDS if item["name"] == "transform")
        self.assertEqual("integer", field["type"])
        self.assertEqual((0, 7), (field["minimum"], field["maximum"]),
                         "the parser declares CLuaConfigInt(0, 0, 7), and a page that "
                         "offered an eighth rotation would be offering one the compositor "
                         "rejects at parse time")
        self.assertIn("wl_output_transform", str(field.get("note") or ""),
                      "the note has to name the enumeration, or 0-7 is seven arbitrary "
                      "numbers")

    def test_mode_accepts_the_named_spellings_and_a_resolution(self):
        field = next(item for item in WRITE_FIELDS if item["name"] == "mode")
        accepted = " ".join(field["accepted"])
        for spelling in ("preferred", "highrr", "highres", "maxwidth"):
            with self.subTest(spelling=spelling):
                self.assertIn(spelling, accepted,
                              f"{spelling} is a mode spelling the parser takes and the "
                              f"record does not list it")
        self.assertIn("WxH@RR.RRHz", accepted,
                      "an explicit refresh rate is the one mode spelling the read side "
                      "cannot be relied on to reproduce")
        self.assertIn("invalid resolution", str(field["refused"]),
                      "the record has to carry the parser's own refusal text, because that "
                      "is what appears in the log when a value is wrong")

    def test_position_accepts_the_auto_spellings_the_parser_takes(self):
        field = next(item for item in WRITE_FIELDS if item["name"] == "position")
        accepted = field["accepted"]
        autos = [item for item in accepted if item.startswith("auto")]
        self.assertEqual(9, len(autos),
                         f"`auto` plus the eight directions is what the parser takes: {autos}")
        self.assertIn("XxY", accepted, "an explicit offset has to be listed too")
        self.assertIn("invalid auto direction", str(field["refused"]))

    def test_output_is_required_and_is_never_written_as_auto(self):
        field = next(item for item in WRITE_FIELDS if item["name"] == "output")
        self.assertTrue(field.get("required"))
        self.assertIn("real name", str(field.get("note") or ""),
                      "the parser accepts `auto` and a description-based selector, and the "
                      "page must not use either, because a rule that matches by description "
                      "stops matching when a monitor is renamed")


class TestThePageWritesOnlyWhatTheRecordMarks(unittest.TestCase):
    """The schema's rule: the page may write a listed field marked written, and nothing else."""

    def test_no_row_offers_a_write_field_the_record_does_not_mark(self):
        text = plan_text()
        for name in NOT_WRITTEN:
            with self.subTest(field=name):
                self.assertNotIn(f"display.monitors.0.{name}", text,
                                 f"the Display page offers {name}, which the record does not "
                                 f"mark as written by this project")

    def test_a_refused_field_reaches_the_page_only_as_a_refusal_and_never_as_a_control(self):
        """The page's refusal vocabulary and the record's refusal list are the same list."""
        refused_actions = {}
        controls = []
        # walk() reaches into an expander's children, which is where the refusal rows live;
        # iterating group.rows would see only the three expander headings.
        for row in PLAN.walk():
            # A read-only row carries its action in `source`; only a row with an `action`
            # slot is one a person can press. Strip the whole `display.refused_` prefix:
            # the field names themselves contain underscores (sdr_max_luminance).
            source = str(getattr(row, "source", "") or "")
            if source.startswith("display.refused_"):
                refused_actions[source[len("display.refused_"):]] = row
            if row.setting or row.kind in ("switch", "combo", "spin", "scale", "entry"):
                controls.append(row)
        self.assertTrue(refused_actions, "the Display page offers no refusal rows at all, so "
                                         "a field it will not write is simply missing")
        for name in sorted(set(refused_actions)):
            row = refused_actions[name]
            with self.subTest(field=name):
                self.assertIn(name, NOT_WRITTEN,
                              f"display.refused_{name} explains a field the record marks as "
                              f"written by this project -- the two have drifted apart")
                self.assertEqual(name, str(row.title),
                                 "a refusal row is titled with the field name itself, which "
                                 "is the one place this application shows a key spelling; the "
                                 "row's body has to carry the reason")
                self.assertTrue(str(row.subtitle or "").strip(),
                                f"{name} is refused and the row gives no reason")
        self.assertEqual(0, len(controls),
                         "the Display page draws a writable control; a monitor change has to "
                         "go through the list builder in services/control.py, which is where "
                         "the revert window and the duplicate-output check live")
        for name, row in sorted(refused_actions.items()):
            with self.subTest(field=name):
                self.assertIsNone(row.action,
                                  f"the refusal row for {name} is pressable, so a person can "
                                  f"ask for a field this project refuses to write")

    def test_the_page_says_what_it_refuses_rather_than_omitting_it(self):
        text = plan_text().lower()
        for word in ("reserved", "mirror"):
            with self.subTest(field=word):
                self.assertIn(word, text,
                              f"the Display page never mentions {word}, so a person looking "
                              f"for it finds no control and no explanation")

    def test_the_page_carries_the_revert_window_the_record_states(self):
        text = plan_text()
        self.assertEqual(15, SAFETY["revert_seconds"])
        self.assertIn(str(SAFETY["revert_seconds"]), text,
                      "the countdown the record states is not on the page, so a person "
                      "cannot know how long they have to answer")

    def test_the_change_is_confirmed_after_it_is_applied_and_the_page_says_why(self):
        text = plan_text().lower()
        self.assertIn("applied", text,
                      "the record's reason for the order -- a dialog drawn over a session "
                      "already running the new mode -- has to reach the page, or the order "
                      "looks like a mistake to the next reader")


class TestThePayloadIsTheRecordedOne(unittest.TestCase):
    """Where the change lands, and what has to be true of it afterwards."""

    def test_the_payload_path_is_the_file_the_session_requires(self):
        self.assertEqual(".config/hypr/monitors.lua", PAYLOAD["path"])
        self.assertTrue(PAYLOAD["generated"], "a generated file that is not marked generated "
                                              "gets no header and can be edited by hand")
        self.assertIn("hyprland.lua", PAYLOAD["required_by"],
                      "the record has to say which file requires the payload, or nobody can "
                      "tell whether writing it does anything")

    def test_the_verification_is_two_checks_and_not_one(self):
        verify = json.dumps(SAFETY.get("verify") or SAFETY.get("verification") or SAFETY)
        self.assertIn("configerrors", verify,
                      "the compositor's own error report is the check that a rule parsed")
        self.assertIn("monitors", verify,
                      "a rule that parsed can still have switched off the only output, so "
                      "the second check is that the monitor is still there")

    def test_the_shipped_file_is_the_identity_rule(self):
        shipped = ROOT / PAYLOAD["path"]
        self.assertTrue(shipped.is_file(), f"{PAYLOAD['path']} is recorded as shipped and is "
                                           f"not in the repository")
        text = shipped.read_text(encoding="utf-8")
        self.assertIn("preferred", text)
        self.assertIn("auto", text)


class TestTheListBuilderRefusesAHalfEntry(unittest.TestCase):
    """Where a dotted path becomes a monitor, and the four ways it can go wrong."""

    def _change(self, dotted: str, value: Any, monitors: Optional[List[Any]] = None):
        settings = {"display": {"monitors": list(monitors or [])}}
        return control.change_for(dotted, value, settings=settings,
                                  config_home=Path("/tmp/display-test"))

    def test_a_wildcard_index_is_refused(self):
        with self.assertRaises(control.ControlError) as caught:
            self._change("display.monitors.*.scale", "1.5")
        self.assertIn("*", str(caught.exception))

    def test_a_non_numeric_index_is_refused_and_names_the_position(self):
        with self.assertRaises(control.ControlError) as caught:
            self._change("display.monitors.first.scale", "1.5")
        message = str(caught.exception)
        self.assertIn("first", message)
        self.assertTrue("position" in message or "monitor" in message,
                        f"the refusal has to say what was wrong with the index: {message}")

    def test_an_index_past_the_end_is_refused_with_the_count_in_the_sentence(self):
        with self.assertRaises(control.ControlError) as caught:
            self._change("display.monitors.1.scale", "1.5", monitors=[{"output": "DP-1"}])
        message = str(caught.exception)
        self.assertIn("1", message)
        self.assertTrue("1 monitor" in message or "one monitor" in message or "count" in
                        message or "has 1" in message,
                        f"the refusal has to say how many monitors there are: {message}")

    def test_a_field_on_an_existing_monitor_writes_the_whole_list(self):
        change = self._change("display.monitors.0.scale", "1.5",
                              monitors=[{"output": "DP-1", "scale": "1"}])
        self.assertTrue(change.settings, "no settings change was produced")
        for path in change.settings:
            with self.subTest(path=path):
                self.assertNotRegex(path, r"\.\d+\.",
                                    f"{path} indexes into a list, and the store's setter "
                                    f"walks mappings only, so an indexed path is silently "
                                    f"unwritable")

    def test_a_new_monitor_is_accepted_only_as_a_whole_entry(self):
        change = self._change("display.monitors.0", {"output": "HDMI-A-1", "scale": "1.5"})
        self.assertTrue(change.settings)
        self.assertEqual(1, len(change.settings),
                         "adding a monitor is one write of the whole list, and a second path "
                         "in the change means the builder wrote through an index")
        path, written = next(iter(change.settings.items()))
        self.assertEqual([{"output": "HDMI-A-1", "scale": "1.5"}], written)
        self.assertNotRegex(path, r"\.\d+",
                            f"{path} indexes into a list, and the store's setter walks "
                            f"mappings only, so an indexed path is silently unwritable")

    def test_a_scale_on_an_empty_list_does_not_become_a_monitor_named_after_it(self):
        """The failure this test exists for: a monitor whose output is '1.5'."""
        with self.assertRaises(control.ControlError):
            self._change("display.monitors.0.scale", "1.5", monitors=[])

    def test_a_field_outside_the_six_is_refused(self):
        with self.assertRaises(control.ControlError) as caught:
            self._change("display.monitors.0.mirror", "DP-1",
                         monitors=[{"output": "DP-1"}])
        self.assertIn("mirror", str(caught.exception))

    def test_two_monitors_cannot_share_an_output_name(self):
        problems = control._monitor_problems(
            [{"output": "DP-1", "scale": "1"}, {"output": "DP-1", "scale": "2"}])
        self.assertTrue(problems, "two rules for one output is a rule applied twice, which "
                                  "is a silent visual bug")

    def test_an_empty_output_name_is_refused(self):
        self.assertTrue(control._monitor_problems([{"output": "", "scale": "1"}]))

    def test_more_monitors_than_the_compositor_takes_is_refused(self):
        many = [{"output": f"DP-{index}", "scale": "1"} for index in range(17)]
        self.assertTrue(control._monitor_problems(many))
        self.assertEqual([], control._monitor_problems(many[:16]))

    def test_the_targets_are_one_file_and_not_a_directory(self):
        change = self._change("display.monitors.0.scale", "1.5",
                              monitors=[{"output": "DP-1", "scale": "1"}])
        self.assertTrue(change.targets, "a change with no target writes nothing")
        for target in change.targets:
            with self.subTest(target=str(target)):
                self.assertTrue(str(target).endswith(".lua"),
                                "a directory cannot be a change target, and a payload that "
                                "is not the recorded file is a file nothing requires")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
