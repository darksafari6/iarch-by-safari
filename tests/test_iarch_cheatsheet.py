# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The ``Super+H`` overlay: what it draws, and where it decides to draw it.

Two things are tested here that a screenshot never could.

The first is that the overlay reads the *same* map the compositor gets. It merges
the record with your override through ``iarch_keybinds.merge``, and the tests drive
that for real against a temporary ``HOME``: rebind something, and the overlay shows
the rebind, not the default. A cheatsheet that disagrees with the session is worse
than no cheatsheet, because it is believed.

The second is the fallback decision. The bind fires with no terminal attached, so
``draw_plan`` has to answer where an overlay can appear on a machine that may have
no terminal, no notification daemon and no display. Every branch is testable
without any of them, by injecting the probe -- which is the only way to prove the
behaviour on a machine with nothing installed rather than assume it.

The colours are checked the same way: every role the overlay paints has to resolve
to a value the shipped ``midnight-glass`` preset actually defines, so no hex value
can be invented in the renderer and the overlay cannot drift to a different blue
from the session it floats over.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "cli"))

import iarch_cheatsheet as sheet  # noqa: E402
from iarch.cli import iarch_keybinds as kb  # noqa: E402

RECORD = ROOT / "data" / "keybinds.default.json"
PRESET = ROOT / "data" / "design" / "presets" / f"{sheet.PRESET}.json"
KEYBIND_LUA = ROOT / ".config" / "hypr" / "keybind.lua"

#: A combination the shipped map does not hold, for the fixtures that write an override.
#: All twenty-six letters of the Super layer are bound now and every cell of the three
#: layers the A to Z table allocates is decided, so a fixture that rebinds something onto
#: a bare letter is a fixture that collides with the map it is testing against. It would
#: still pass -- `overlay_rows` reads and does not validate -- and a fixture that only
#: works because nothing checks it is one that stops meaning what it says the day
#: something does. Super+Shift+Ctrl is the layer the record uses for the four window swaps
#: on the arrows and the table does not allocate it, so its letters are free.
FREE_MODS = ["SUPER", "SHIFT", "CTRL"]


def bindings() -> List[Dict[str, Any]]:
    return json.loads(RECORD.read_text(encoding="utf-8"))["bindings"]


class TheModel(unittest.TestCase):
    """The rows, and the proof they are the session's rows."""

    def setUp(self) -> None:
        self.rows = sheet.overlay_rows({"HOME": str(ROOT / "does-not-exist")})

    def test_it_shows_every_enabled_binding_in_the_record(self):
        expected = {b["id"] for b in bindings() if b.get("enabled")}
        shown = {row["id"] for row in self.rows if row["bound"]}
        self.assertEqual(expected, shown)

    def test_a_reserved_key_is_carried_but_not_shown_as_bound(self):
        reserved = next(b for b in bindings() if b.get("reserved"))
        row = next(r for r in self.rows if r["id"] == reserved["id"])
        self.assertFalse(row["bound"])
        self.assertTrue(row["reserved"])

    def test_a_disabled_binding_is_not_offered_as_a_shortcut(self):
        disabled = [b for b in bindings() if not b.get("enabled")]
        self.assertTrue(disabled, "the record has no disabled entry to test against")
        for entry in disabled:
            row = next(r for r in self.rows if r["id"] == entry["id"])
            self.assertFalse(row["bound"])

    def test_the_static_recovery_bind_is_shown_because_it_is_a_real_key(self):
        """It is not rendered into the generated Lua, but it does exist and does fire,
        so an overlay that hid it would hide the one key that repairs the map."""
        row = next(r for r in self.rows if r["id"] == "recovery.reapply-defaults")
        self.assertTrue(row["bound"])
        self.assertTrue(row["static"])

    def test_every_row_has_a_description_and_a_readable_key(self):
        for row in self.rows:
            with self.subTest(row=row["id"]):
                self.assertTrue(row["description"].strip())
                self.assertTrue(row["keys"].strip())

    def test_a_persons_override_changes_what_the_overlay_shows(self):
        """The whole point: one map, read by the compositor and by the overlay."""
        tmp = Path(tempfile.mkdtemp(prefix="iarch-sheet-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".config" / "iarch").mkdir(parents=True)
        (tmp / ".config" / "iarch" / "keybinds.json").write_text(json.dumps(
            {"bindings": [{"id": "applications.browser", "mods": FREE_MODS, "key": "G",
                          "description": "My browser"}]}), encoding="utf-8")

        rows = sheet.overlay_rows({"HOME": str(tmp)})
        row = next(r for r in rows if r["id"] == "applications.browser")
        self.assertEqual("SUPER + SHIFT + CTRL + G", row["keys"])
        self.assertEqual("My browser", row["description"])

    def test_a_disabled_override_takes_the_row_out_of_the_bound_groups(self):
        tmp = Path(tempfile.mkdtemp(prefix="iarch-sheet-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".config" / "iarch").mkdir(parents=True)
        (tmp / ".config" / "iarch" / "keybinds.json").write_text(json.dumps(
            {"bindings": [{"id": "applications.code-editor", "enabled": False}]}),
            encoding="utf-8")
        rows = sheet.overlay_rows({"HOME": str(tmp)})
        row = next(r for r in rows if r["id"] == "applications.code-editor")
        self.assertFalse(row["bound"], "an override the compositor honours is one the "
                                       "overlay has to honour too")


class Grouping(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = sheet.overlay_rows({"HOME": str(ROOT / "does-not-exist")})
        self.groups = sheet.grouped(self.rows)

    def test_the_categories_are_the_records_own_in_its_own_order(self):
        order = kb.categories_in_order(bindings())
        named = [g["category"] for g in self.groups if g["category"] != sheet.HELD]
        self.assertEqual([c for c in order if c in named], named)

    def test_held_keys_get_their_own_group_and_it_is_last(self):
        self.assertEqual(sheet.HELD, self.groups[-1]["category"])
        self.assertTrue(all(not r["bound"] for r in self.groups[-1]["rows"]))

    def test_no_group_is_empty_and_no_row_is_in_two_groups(self):
        seen: List[str] = []
        for group in self.groups:
            self.assertTrue(group["rows"], f"{group['category']} is an empty heading")
            for row in group["rows"]:
                self.assertNotIn(row["id"], seen, f"{row['id']} is listed twice")
                seen.append(row["id"])
        self.assertEqual(len(self.rows), len(seen), "a row went missing in the grouping")

    def test_the_group_a_row_lands_in_is_its_own_category(self):
        for group in self.groups:
            if group["category"] == sheet.HELD:
                continue
            for row in group["rows"]:
                self.assertEqual(group["category"], row["category"])


class Filtering(unittest.TestCase):
    def setUp(self) -> None:
        rows = sheet.overlay_rows({"HOME": str(ROOT / "does-not-exist")})
        self.groups = sheet.grouped(rows)
        self.count = sum(len(g["rows"]) for g in self.groups)

    def shown(self, query: str) -> List[Dict[str, Any]]:
        return [row for g in sheet.filter_groups(self.groups, query) for row in g["rows"]]

    def test_no_query_shows_everything(self):
        self.assertEqual(self.count, len(self.shown("")))
        self.assertEqual(self.count, len(self.shown("   ")))

    def test_a_word_narrows_to_the_rows_that_say_it(self):
        rows = self.shown("screenshot")
        self.assertTrue(rows)
        self.assertTrue(all("screenshot" in (r["description"] + r["category"]
                                             + r["id"]).casefold() for r in rows))
        self.assertLess(len(rows), self.count)

    def test_terms_are_anded_not_ored(self):
        self.assertLessEqual(len(self.shown("workspace move")),
                             len(self.shown("workspace")))
        self.assertTrue(all("workspace" in r["category"].casefold()
                            or "workspace" in r["description"].casefold()
                            for r in self.shown("workspace move")))

    def test_matching_ignores_case(self):
        self.assertEqual(self.shown("LOCK"), self.shown("lock"))

    def test_a_single_character_has_to_be_a_key_not_a_letter(self):
        """The rule that makes `super t` answer with the rows that key instead of most
        of the map: on an overlay of shortcuts a lone character names a key.

        Compared as a set rather than a list because what the rule guarantees is which
        rows answer, not the order the categories happen to render in.
        """
        rows = self.shown("super t")
        self.assertEqual({"applications.settings", "appearance.theme-mode"},
                         {r["id"] for r in rows},
                         "Super+T and Super+Ctrl+T are the two combinations that are both "
                         "`super` and `t`; a row whose description merely contains the "
                         "letter is not one of them")
        for row in rows:
            self.assertIn("t", sheet.key_tokens(row["keys"]))

    def test_a_single_character_still_finds_every_key_that_uses_it(self):
        rows = self.shown("h")
        ids = {r["id"] for r in rows}
        self.assertIn("overlay.cheatsheet", ids)
        self.assertTrue(all("h" in sheet.key_tokens(r["keys"]) for r in rows),
                        "a letter matched a description instead of a key")

    def test_a_query_that_matches_nothing_shows_nothing(self):
        self.assertEqual([], self.shown("zzzz"))

    def test_an_empty_category_disappears_rather_than_heading_nothing(self):
        groups = sheet.filter_groups(self.groups, "screenshot")
        self.assertTrue(all(g["rows"] for g in groups))

    def test_filtering_does_not_mutate_the_groups_it_was_given(self):
        before = json.dumps(self.groups, sort_keys=True)
        sheet.filter_groups(self.groups, "lock")
        self.assertEqual(before, json.dumps(self.groups, sort_keys=True))


class ThePalette(unittest.TestCase):
    """Colours are read out of the shipped preset, so none can be invented here."""

    def setUp(self) -> None:
        self.paint = sheet.palette()
        self.preset = json.loads(PRESET.read_text(encoding="utf-8"))["palette"]

    def test_every_role_the_renderer_paints_resolves(self):
        for role in sheet.COLOR_ROLES:
            with self.subTest(role=role):
                self.assertIn(role, self.paint)
                self.assertRegex(self.paint[role], r"^#[0-9a-fA-F]{6}$")

    def test_every_colour_is_one_the_preset_defines(self):
        flat = json.dumps(self.preset)
        for role, value in self.paint.items():
            with self.subTest(role=role):
                self.assertIn(value, flat,
                              f"{role} is {value}, which the {sheet.PRESET} preset does "
                              "not define, so it was invented in the renderer")

    def test_the_accent_is_the_neon_blue_the_rest_of_the_session_uses(self):
        self.assertEqual(self.preset["accent"]["primary"], self.paint["accent"])

    def test_a_role_the_preset_cannot_answer_is_an_error_not_a_guess(self):
        empty = Path(tempfile.mkdtemp(prefix="iarch-preset-"))
        self.addCleanup(shutil.rmtree, empty, True)
        (empty / "data" / "design" / "presets").mkdir(parents=True)
        (empty / "data" / "design" / "presets" / f"{sheet.PRESET}.json").write_text(
            json.dumps({"palette": {"background": "#000000"}}), encoding="utf-8")
        with self.assertRaises(KeyError) as caught:
            sheet.palette(root=empty)
        self.assertIn("accent", str(caught.exception))
        self.assertIn(sheet.PRESET, str(caught.exception))


class TheTextOverlay(unittest.TestCase):
    def setUp(self) -> None:
        rows = sheet.overlay_rows({"HOME": str(ROOT / "does-not-exist")})
        self.groups = sheet.grouped(rows)

    def test_plain_text_carries_no_escape_at_all(self):
        text = sheet.render_text(self.groups, colors=False)
        self.assertNotIn("\x1b", text)

    def test_the_coloured_overlay_paints_with_the_presets_own_values(self):
        paint = sheet.palette()
        text = sheet.render_text(self.groups, colors=True, paint=paint)
        red, green, blue = sheet.rgb(paint["accent"])
        self.assertIn(f"\x1b[38;2;{red};{green};{blue}m", text,
                      "the accent the preset defines is not the accent drawn")
        self.assertIn("\x1b[0m", text, "a colour that is never reset bleeds into the "
                                      "rest of the terminal")

    def test_every_category_is_a_heading_and_every_key_is_on_a_line(self):
        text = sheet.render_text(self.groups, colors=False)
        for group in self.groups:
            self.assertIn(group["category"].upper(), text)
        for group in self.groups:
            for row in group["rows"]:
                with self.subTest(keys=row["keys"]):
                    self.assertIn(row["keys"], text)
                    self.assertIn(row["description"], text)

    def test_a_locked_key_says_it_is_locked(self):
        text = sheet.render_text(self.groups, colors=False)
        line = next(l for l in text.splitlines() if "SUPER + H" in l)
        self.assertIn("locked", line,
                      "the overlay is the place a person learns a key cannot be removed")

    def test_the_query_it_narrowed_to_is_shown_in_the_header(self):
        text = sheet.render_text(sheet.filter_groups(self.groups, "lock"),
                                 colors=False, query="lock")
        self.assertIn("filter: lock", text)
        self.assertNotIn("filter: none", text)

    def test_nothing_matching_says_so_and_does_not_invent_a_count(self):
        text = sheet.render_text([], colors=False, query="zzzz")
        self.assertIn("Nothing matches 'zzzz'", text)
        self.assertNotIn("0 rows", text)

    def test_the_header_counts_what_is_actually_shown(self):
        groups = sheet.filter_groups(self.groups, "workspace")
        total = sum(len(g["rows"]) for g in groups)
        text = sheet.render_text(groups, colors=False, query="workspace")
        self.assertIn(f"{total} shown", text)


class TheJsonOverlay(unittest.TestCase):
    def test_it_round_trips_and_names_where_it_came_from(self):
        rows = sheet.overlay_rows({"HOME": str(ROOT / "does-not-exist")})
        groups = sheet.grouped(rows)
        document = json.loads(sheet.render_json(groups, "lock"))
        self.assertEqual(sum(len(g["rows"]) for g in groups), document["count"])
        self.assertEqual(["lock"], document["terms"])
        self.assertIn("keybinds.default.json", document["source"])
        self.assertEqual([g["category"] for g in groups],
                         [c["category"] for c in document["categories"]])


class WhereItDraws(unittest.TestCase):
    """The fallback chain, on machines that have nothing."""

    def plan(self, *, is_tty: bool, have: tuple = ()) -> List[str]:
        probe = lambda name: f"/usr/bin/{name}" if name in have else None  # noqa: E731
        return [kind for kind, _ in sheet.draw_plan(is_tty=is_tty, probe=probe)]

    def test_with_a_terminal_already_attached_it_draws_here_first(self):
        self.assertEqual("here", self.plan(is_tty=True, have=("kitty",))[0])

    def test_without_one_it_opens_the_first_terminal_installed(self):
        kinds = self.plan(is_tty=False, have=("foot", "xterm"))
        self.assertEqual("terminal:foot", kinds[0],
                         "the order is the compositor's own, so a session with both "
                         "installed should get the same choice from either fallback")

    def test_with_no_terminal_at_all_it_falls_back_to_a_notification(self):
        kinds = self.plan(is_tty=False, have=("notify-send",))
        self.assertEqual("notify", kinds[0])

    def test_stderr_is_always_the_last_resort_and_never_the_only_silent_one(self):
        for have in ((), ("kitty",), ("notify-send",)):
            with self.subTest(have=have):
                kinds = self.plan(is_tty=False, have=have)
                self.assertEqual("stderr", kinds[-1],
                                 "a chain that can end in silence is how a key dies "
                                 "without anybody knowing")

    def test_no_notification_daemon_means_no_notification_step(self):
        self.assertNotIn("notify", self.plan(is_tty=False, have=("kitty",)))

    def test_the_terminal_order_agrees_with_the_static_binds_own_probe(self):
        """Two fallbacks a session has should not disagree about which terminal to open."""
        lua = KEYBIND_LUA.read_text(encoding="utf-8")
        block = re.search(r'for _, candidate in ipairs\(\{(.*?)\}\)', lua, re.S)
        self.assertTrue(block, "keybind.lua no longer probes for a terminal in order")
        in_lua = re.findall(r'"([a-z0-9-]+)"', block.group(1))
        self.assertEqual(tuple(in_lua), sheet.TERMINALS)

    def test_the_terminal_command_is_an_argument_list_not_a_shell_string(self):
        """A query with a quote or a space in it must not become shell syntax."""
        command = sheet.terminal_command("kitty", ["python3", "x.py", "--query",
                                                   "a; rm -rf ~"])
        self.assertEqual("kitty", command[0])
        self.assertIn("a; rm -rf ~", command)
        self.assertNotIn("-c", command, "a shell would parse the query")

    def test_closing_answers_are_the_ones_a_person_reaches_for(self):
        for reply in ("q", "Q", "", "  ", "quit", "\x1b"):
            with self.subTest(reply=repr(reply)):
                self.assertTrue(sheet.closing(reply))
        for reply in ("lock", "t", "n"):
            with self.subTest(reply=reply):
                self.assertFalse(sheet.closing(reply),
                                 "a filter typed at the prompt would close the overlay")


class TheCommandLine(unittest.TestCase):
    """main() end to end, with a HOME that has nothing in it."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="iarch-sheet-cli-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        (self.home / ".config" / "iarch").mkdir(parents=True)

    def run_main(self, *argv: str) -> tuple:
        environment = {"HOME": str(self.home)}
        saved = {k: os.environ.get(k) for k in environment}
        os.environ.update(environment)
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                code = sheet.main(list(argv))
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return code, buffer.getvalue()

    def test_json_is_machine_readable_and_carries_the_filter(self):
        code, out = self.run_main("--json", "--query", "workspace")
        self.assertEqual(0, code)
        document = json.loads(out)
        self.assertEqual(["workspace"], document["terms"])
        self.assertTrue(document["count"])

    def test_text_with_no_wait_prints_and_exits_clean(self):
        code, out = self.run_main("--text", "--no-wait", "--no-color")
        self.assertEqual(0, code)
        self.assertIn("iArch shortcuts", out)

    def test_the_plan_is_printed_and_nothing_is_drawn(self):
        code, out = self.run_main("--plan")
        self.assertEqual(0, code)
        self.assertIn("stderr", out)
        self.assertNotIn("iArch shortcuts", out)

    def test_a_query_that_matches_nothing_is_not_an_error(self):
        code, out = self.run_main("--text", "--no-wait", "--no-color", "--query", "zzz")
        self.assertEqual(0, code, "an empty result is an answer, not a failure")
        self.assertIn("Nothing matches", out)

    def test_an_unknown_option_is_refused_with_status_2(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_main("--nonsense")
        self.assertEqual(2, caught.exception.code)


class TheNameItIsCalledBy(unittest.TestCase):
    """A bind that names a program nothing provides is a key that does nothing."""

    def test_every_iarch_command_a_binding_execs_is_one_the_linker_provides(self):
        link_script = (ROOT / "scripts" / "iarch-link-cli.sh").read_text(encoding="utf-8")
        block = re.search(r"^COMMANDS=\(\n(.*?)^\)", link_script, re.S | re.M)
        self.assertTrue(block, "scripts/iarch-link-cli.sh no longer declares COMMANDS")
        provided = set(re.findall(r'"([A-Za-z0-9._-]+):', block.group(1)))

        wanted = set()
        for entry in bindings():
            action = entry.get("action") or {}
            if action.get("type") not in ("exec", "shell"):
                continue
            command = action.get("command") or []
            if command and str(command[0]).startswith("iarch-"):
                wanted.add(str(command[0]).rsplit("/", 1)[-1])
        self.assertTrue(wanted, "no binding execs an iarch-* command, so this test "
                                "has nothing to protect")
        for name in sorted(wanted):
            with self.subTest(command=name):
                self.assertIn(name, provided,
                              f"a bind execs {name} and nothing puts it on PATH")

    def test_the_overlay_bind_is_the_only_thing_on_its_key(self):
        """The overlay must not arrive by taking a key somebody else had."""
        bound = [b for b in bindings()
                 if b.get("enabled") and kb.key_string(b) == "SUPER + H"]
        self.assertEqual(["overlay.cheatsheet"], [b["id"] for b in bound])

    def test_the_overlay_adds_no_binding_of_its_own(self):
        """It is drawn from the record; it does not write to it."""
        before = RECORD.read_bytes()
        subprocess.run([sys.executable, str(ROOT / "iarch" / "cli" / "iarch_cheatsheet.py"),
                        "--json"], capture_output=True, timeout=120,
                       env={"HOME": str(ROOT / "does-not-exist"), "PATH": "/usr/bin:/bin"})
        self.assertEqual(before, RECORD.read_bytes())


if __name__ == "__main__":
    unittest.main()
