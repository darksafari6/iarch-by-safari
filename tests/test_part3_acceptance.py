# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Part 3 acceptance, proven mechanically.

Part 3 was accepted on four rules that apply to every surface it touched -- the
motion presets and their CLI, the notification and control-centre records, the
launcher and window switcher, the two lock screens and the idle fallback, the
login screen, the two mode switches, the startup module and the wallpaper:

1. every emitted key exists in the pinned upstream release's surface record;
2. generated files are committed *and* checked in CI, so a payload cannot drift
   from the record that justifies it;
3. a missing binary is *unverified* -- never a failure and never a pass;
4. documentation states what a surface cannot do as plainly as what it can.

Each suite proves its own surface in detail: ``test_animations_lua.py`` the leaves
and curves, ``test_noctalia.py`` the shell's keys, ``test_hyprlock.py`` the two
lock files, ``test_greeter.py`` the login screen, ``test_gamemode.py`` and
``test_focus.py`` the modes, ``test_startup_lua.py`` the module that starts the
session. This file proves the four claims *across* all of them, so a future change
that unpins a release, drops a CI check, turns a missing binary into a verdict, or
deletes the sentence that says what a surface cannot do fails here rather than
quietly eroding the acceptance.

It needs no third-party package and no compositor: the report subcommands it runs
are the ones that only ask, and it runs them with nothing on ``PATH`` at all, which
is exactly the condition criterion 3 is about.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402

DESIGN = ROOT / "data" / "design"
WORKFLOW = ROOT / ".github" / "workflows" / "iarch-checks.yml"
UNVERIFIED = ROOT / "docs" / "UNVERIFIED.md"

# The two releases Part 3 read out of upstream, and the records that came from each.
# tokens.json is the design's own source rather than an upstream surface, but the
# compositor half of it is a record of Hyprland's leaves and carries the same pin.
HYPRLAND_RELEASE = "v0.57.2"
SHELL_RELEASE = "v5.4.1"
COMPOSITOR_RECORDS = ("animations.json", "startup.json")
SHELL_RECORDS = ("noctalia.json",)

# Records pinned to something other than a release tag, each for a recorded reason:
# the greeter's main branch and its newest tag disagree, so a tag is pinned; hyprlock
# has no release-tagged manual, so the wiki's main branch is cited with the fetch date
# (LOCK-04 says what that costs).
OTHER_PINS = {
    "greeter.json": "v1.7.0",
    "hyprlock.json": "hyprland-wiki main",
}

# Every payload file this repository ships rendered, and the record that justifies
# its keys. The GTK sheets are not in the map: their header is one line and their
# provenance lives in render_gtk_css.py and docs/GTK-NOTES.md, so the test below
# only asks them for the GENERATED sentence.
PAYLOAD_RECORDS = {
    ".config/hypr/generated/glass.lua": "data/design/tokens.json",
    ".config/hypr/generated/animations.lua": "data/design/animations.json",
    ".config/hypr/startup.lua": "data/design/startup.json",
    ".config/hypr/hyprlock.conf": "data/design/hyprlock.json",
    ".config/hypr/hypridle.conf": "data/design/hyprlock.json",
    ".config/noctalia/config.toml": "data/design/noctalia.json",
    ".config/Kvantum/kvantum.kvconfig": "data/design/kvantum.json",
    ".config/fontconfig/fonts.conf": "data/design/fontconfig.json",
}

GENERATED_PAYLOADS = tuple(PAYLOAD_RECORDS) + (
    ".config/gtk-4.0/gtk.css",
    ".config/gtk-3.0/gtk.css",
    ".config/Kvantum/iarch/iarch.kvconfig",
)

# Report subcommands: the ones that only ask, so running them with an empty PATH
# changes nothing and proves what a missing binary is reported as.
REPORT_COMMANDS = (
    ("iarch/cli/iarch_gamemode.py", "status", "--json"),
    ("iarch/cli/iarch_focus.py", "status", "--json"),
    ("iarch/cli/iarch_anim.py", "current", "--live"),
    ("iarch/cli/theme.py", "current"),
    ("iarch/cli/iarch_doctor.py", "dnd", "status"),
)

MODE_REPORTS = (
    ("iarch/cli/iarch_gamemode.py", "status", "--json"),
    ("iarch/cli/iarch_focus.py", "status", "--json"),
)

# The unverified items Part 3 opened or inherited, by prefix. Each one has to have
# at least a row: a limitation that is only in a commit message is not recorded.
PART3_PREFIXES = ("MOT", "NOT", "LOCK", "GRE", "SES", "UI", "PERF", "MODE", "START", "WAL")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def records() -> Dict[str, Any]:
    return {path.name: read_json(path) for path in sorted(DESIGN.glob("*.json"))}


def unverified_rows() -> List[List[str]]:
    """Every table row of docs/UNVERIFIED.md, as four cells."""
    rows = []
    for line in UNVERIFIED.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("Id", "") or set(cells[0]) <= {"-", " "}:
            continue
        rows.append(cells)
    return rows


class Criterion1EveryKeyComesFromARecord(unittest.TestCase):
    def test_every_surface_record_names_a_release_or_a_pinned_source(self):
        surfaces = {name: doc for name, doc in records().items()
                    if name not in ("tokens.json", "glass.tokens.json")}
        self.assertTrue(surfaces)
        for name, doc in sorted(surfaces.items()):
            with self.subTest(record=name):
                self.assertIn("verified_against", doc, "a surface with no pin")
                self.assertIn("source", doc, "a surface with no upstream source cited")
                pinned = json.dumps(doc["verified_against"])
                # A release tag, or -- where upstream publishes no tagged manual --
                # the branch and the date it was fetched, which is what hyprlock.json
                # cites and what LOCK-04 records as a limitation in itself.
                self.assertRegex(pinned, r"(v?\d+\.\d+|fetched \d{4}-\d{2}-\d{2})",
                                 f"{name} pins {pinned}, which names no version and no fetch")

    def test_the_compositor_records_all_pin_the_same_release(self):
        for name in COMPOSITOR_RECORDS:
            with self.subTest(record=name):
                self.assertEqual(HYPRLAND_RELEASE, records()[name]["verified_against"])
        self.assertEqual(HYPRLAND_RELEASE,
                         records()["tokens.json"]["hyprland"]["verified_against"])

    def test_the_shell_record_pins_the_release_the_renderer_refuses_to_write_past(self):
        self.assertEqual(SHELL_RELEASE, records()["noctalia.json"]["verified_against"])

    def test_the_records_that_pin_something_else_say_what_they_pin(self):
        for name, needle in sorted(OTHER_PINS.items()):
            with self.subTest(record=name):
                self.assertIn(needle, json.dumps(records()[name]["verified_against"]))

    def test_every_rendered_payload_names_the_record_its_keys_come_from(self):
        for relative, record in sorted(PAYLOAD_RECORDS.items()):
            with self.subTest(payload=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file(), f"{relative} does not ship")
                head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:4])
                self.assertIn(record, head,
                              f"{relative} does not name {record} in its header")
                self.assertTrue((ROOT / record).is_file(), f"{record} is missing")

    def test_every_payload_is_rendered_rather_than_hand_written(self):
        for relative in GENERATED_PAYLOADS:
            with self.subTest(payload=relative):
                first = (ROOT / relative).read_text(encoding="utf-8").splitlines()[0]
                self.assertTrue(configstore.is_header_line(first),
                                f"{relative} line 1 is not a GENERATED header: {first!r}")

    def test_the_part_3_surfaces_record_what_they_do_not_emit(self):
        # A record that only lists what is allowed cannot stop a renderer from
        # emitting a key upstream declares but this project refuses, so each surface
        # carries its refusals too.
        expectations = {
            "noctalia.json": ("withheld", "Not emitted"),
            "startup.json": ("not_shipped", "removed"),
            "greeter.json": ("not_shipped",),
            "hyprlock.json": ("not_in_hyprlock",),
        }
        for name, needles in sorted(expectations.items()):
            text = (DESIGN / name).read_text(encoding="utf-8")
            for needle in needles:
                with self.subTest(record=name, needle=needle):
                    self.assertIn(needle, text)


class Criterion2GeneratedAndChecked(unittest.TestCase):
    def workflow(self) -> str:
        return WORKFLOW.read_text(encoding="utf-8")

    def tools_that_can_check_themselves(self) -> List[str]:
        found = []
        for directory in ("iarch/cli", "tools"):
            for path in sorted((ROOT / directory).glob("*.py")):
                if '"--check"' in path.read_text(encoding="utf-8"):
                    found.append(path.relative_to(ROOT).as_posix())
        return found

    def test_every_tool_that_can_check_itself_is_checked_in_ci(self):
        tools = self.tools_that_can_check_themselves()
        self.assertTrue(tools, "no tool offers --check, which would make this test vacuous")
        workflow = self.workflow()
        missing = [tool for tool in tools if f"python {tool} --check" not in workflow]
        self.assertEqual([], missing,
                         "a payload can drift from the record that justifies it without "
                         "anything noticing")

    def test_the_part_3_renderers_are_among_them(self):
        tools = set(self.tools_that_can_check_themselves())
        for tool in ("iarch/cli/gen_startup_lua.py", "iarch/cli/render_hyprlock.py",
                     "iarch/cli/render_noctalia.py", "iarch/cli/gen_animations_lua.py"):
            with self.subTest(tool=tool):
                self.assertIn(tool, tools)

    def test_every_generated_payload_is_committed(self):
        listed = subprocess.run(["git", "ls-files", ".config"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.split()
        for relative in GENERATED_PAYLOADS:
            with self.subTest(payload=relative):
                self.assertIn(relative, listed,
                              "a generated file that is not committed is a file every "
                              "install renders differently")

    def test_the_workflow_smoke_runs_both_mode_switches_without_writing(self):
        workflow = self.workflow()
        for command in ("iarch_gamemode.py on --dry-run", "iarch_focus.py on --dry-run"):
            with self.subTest(command=command):
                self.assertIn(command, workflow)

    def test_the_workflow_validates_every_data_file_including_the_new_one(self):
        workflow = self.workflow()
        for pair in ("data/design/startup.json", "data/schemas/startup.schema.json"):
            with self.subTest(path=pair):
                self.assertIn(pair, workflow)
        self.assertIn('"data/design/startup.json": "data/schemas/startup.schema.json"',
                      workflow)


class Criterion3AMissingBinaryIsUnverified(unittest.TestCase):
    """Run every report subcommand with nothing on PATH and see what it claims."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "empty").mkdir()
        (self.root / "home").mkdir()

    def run_report(self, argv: List[str]) -> subprocess.CompletedProcess:
        env = {
            "PATH": str(self.root / "empty"),
            "HOME": str(self.root / "home"),
            "IARCH_CONFIG_DIR": str(self.root / "home" / ".config" / "iarch"),
            "IARCH_STATE_DIR": str(self.root / "home" / ".local" / "state" / "iarch"),
        }
        return subprocess.run([sys.executable, str(ROOT / argv[0]), *argv[1:]],
                              cwd=ROOT, capture_output=True, text=True, env=env)

    def test_no_report_subcommand_fails_because_a_binary_is_missing(self):
        for argv in REPORT_COMMANDS:
            with self.subTest(command=" ".join(argv)):
                result = self.run_report(list(argv))
                self.assertEqual(0, result.returncode,
                                 f"{argv[0]} treated a missing binary as a failure:\n"
                                 f"{result.stdout}\n{result.stderr}")

    def test_no_report_subcommand_claims_a_state_it_could_not_read(self):
        for argv in REPORT_COMMANDS:
            with self.subTest(command=" ".join(argv)):
                out = self.run_report(list(argv)).stdout
                self.assertNotIn("matches the session", out)
                self.assertNotRegex(out, r"\bverdict:\s*matches\b")

    def test_both_mode_reports_say_unverified_and_name_the_missing_binary(self):
        for argv in MODE_REPORTS:
            with self.subTest(command=argv[0]):
                result = self.run_report(list(argv))
                report = json.loads(result.stdout)
                self.assertEqual("unverified", report["verdict"])
                self.assertNotEqual("matches", report["verdict"])
                self.assertTrue(report["checks"], "a report with no checks proves nothing")
                for check in report["checks"]:
                    name = check.get("leaf") or check.get("check")
                    with self.subTest(check=name):
                        self.assertIsNone(check["actual"],
                                          "a value was reported that nothing answered")
                        self.assertEqual("unverified", check["verdict"])
                        self.assertIn("not on PATH", check["detail"])

    def test_the_doctor_answers_unknown_rather_than_guessing(self):
        result = self.run_report(["iarch/cli/iarch_doctor.py", "dnd", "status"])
        out = result.stdout + result.stderr
        self.assertIn("unknown", out)
        self.assertIn("not installed", out)
        self.assertNotRegex(out, r"Do Not Disturb is (on|off)")

    def test_a_missing_binary_is_not_recorded_as_a_state_change(self):
        # Nothing may be written by a report that could not read anything: the
        # settings file has to stay absent, so a later `off` cannot restore a value
        # that was never read.
        self.run_report(["iarch/cli/iarch_gamemode.py", "status", "--json"])
        settings = self.root / "home" / ".config" / "iarch" / "settings.json"
        self.assertFalse(settings.exists(), f"{settings} was written by a report")


class Criterion4WhatASurfaceCannotDo(unittest.TestCase):
    def test_every_unverified_row_says_what_the_gap_blocks(self):
        rows = unverified_rows()
        self.assertGreater(len(rows), 50, "the register has lost most of its rows")
        for identifier, item, why, blocking in rows:
            with self.subTest(item=identifier):
                self.assertRegex(identifier, r"^[A-Z]{2,5}-\d{2}$")
                for cell, what in ((item, "the item"), (why, "the evidence"),
                                   (blocking, "what the gap blocks")):
                    self.assertGreaterEqual(len(cell), 10,
                                            f"{identifier} does not say {what}")
                    self.assertNotIn(cell, ("-", "--", "—", "n/a", "none", "None"),
                                     f"{identifier} fills {what} with a placeholder")

    def test_every_part_3_limitation_has_a_row(self):
        prefixes = {row[0].split("-")[0] for row in unverified_rows()}
        for prefix in PART3_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, prefixes)

    def test_the_documents_say_what_a_reader_would_otherwise_get_wrong(self):
        claims = {
            "docs/MOTION.md": "wallpaper.cpp:1516-1518",
            "docs/WALLPAPERS.md": "not repository state",
            "docs/glass-experience.md": "a command in this repository rather than an installed binary",
            "SECURITY.md": "silent by construction",
            "README.md": "no key is bound",
            "iarch/cli/README.md": "unverified",
        }
        for relative, needle in sorted(claims.items()):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(needle, text,
                              f"{relative} no longer states the limit {needle!r} names")

    def test_the_motion_document_says_which_switch_does_not_reach_the_wallpaper(self):
        text = (ROOT / "docs" / "MOTION.md").read_text(encoding="utf-8")
        self.assertIn("[shell.animation] enabled = false", text)
        self.assertIn("transition = []", text)

    def test_the_wallpaper_document_does_not_send_a_reader_to_a_directory_that_is_not_scanned(self):
        text = (ROOT / "docs" / "WALLPAPERS.md").read_text(encoding="utf-8")
        self.assertIn("file_utils.h", text)
        self.assertNotIn("That directory is what Noctalia's wallpaper picker reads", text)

    def test_the_startup_record_requires_a_reason_for_every_command(self):
        record = records()["startup.json"]
        self.assertTrue(record["exec_once"])
        for entry in record["exec_once"] + record["env"]:
            with self.subTest(entry=entry.get("command") or entry["name"]):
                self.assertGreater(len(entry["why"]), 40,
                                   "a command or variable with no reason is one nobody "
                                   "can tell from a mistake")
        self.assertTrue(record["not_shipped"])

    def test_the_schema_refuses_a_command_without_a_reason(self):
        # The requirement above is enforced by the schema, not by the test alone:
        # data/schemas/startup.schema.json makes `why` required and long.
        schema = read_json(ROOT / "data" / "schemas" / "startup.schema.json")
        entry = schema["definitions"]["exec_entry"]
        self.assertIn("why", entry["required"])
        self.assertEqual(40, entry["properties"]["why"]["minLength"])
        self.assertIn("why", schema["definitions"]["env_entry"]["required"])


if __name__ == "__main__":
    unittest.main()
