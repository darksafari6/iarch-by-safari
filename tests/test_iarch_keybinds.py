# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The generator's own logic: the render, the merge, and every validation rule.

``tests/test_keybinds_data.py`` asks whether the *shipped* record is sound and
its renderings are current. This file asks whether ``iarch/cli/iarch_keybinds.py``
is correct -- the part that turns a record into Lua and refuses a record that
would render cleanly and then resolve to nothing at run time.

The centrepiece is a golden file. ``tests/fixtures/keybinds.golden.json`` is a
small fixed record with one of every action type the renderer handles, and
``tests/fixtures/keybinds.golden.lua`` is the exact Lua it must produce. Pinning
the bytes rather than re-deriving them is the point: a change to how a command is
quoted, a description escaped, or a workspace rendered shows up as a diff a
person has to accept on purpose, instead of silently reaching a generated file
the session reads. The same fixture is then parsed as Lua and validated, so the
golden output is not just stable but correct.

Everything here runs as a normal user with no compositor, no display and no Lua
toolchain: the render and the rules are pure functions of the record, and the one
check that needs a Lua parser (``luac -p`` in production, ``luaparser`` here)
skips when neither is installed rather than failing a machine for what it has.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import iarch_keybinds as kb  # noqa: E402
from iarch.lib import configstore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN_RECORD = FIXTURES / "keybinds.golden.json"
GOLDEN_LUA = FIXTURES / "keybinds.golden.lua"


def make_binding(**over: Any) -> Dict[str, Any]:
    """A minimal valid v2 binding, with any field overridden for one rule test."""
    base: Dict[str, Any] = {
        "id": "test.binding",
        "mods": ["SUPER"],
        "key": "T",
        "action": {"type": "exec", "command": ["true"]},
        "description": "A test binding",
        "category": "Test",
        "enabled": True,
        "locked": False,
    }
    base.update(over)
    return base


def list_json() -> List[Dict[str, Any]]:
    """The real ``list --json`` payload, with no override file in the way.

    ``cmd_list`` reads the environment itself, so the override directory is pointed
    at an empty temporary one: a test that merges whatever happens to be in the
    developer's ``~/.config/iarch`` passes on one machine and fails on another.
    """
    with tempfile.TemporaryDirectory() as empty:
        previous = os.environ.get("IARCH_CONFIG_DIR")
        os.environ["IARCH_CONFIG_DIR"] = empty
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = kb.cmd_list(argparse.Namespace(json=True, category=None))
        finally:
            if previous is None:
                os.environ.pop("IARCH_CONFIG_DIR", None)
            else:
                os.environ["IARCH_CONFIG_DIR"] = previous
    if code != 0:
        raise AssertionError(f"list --json exited {code}")
    return json.loads(buffer.getvalue())


def severities(problems: List[kb.Problem]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for problem in problems:
        out[problem.severity] = out.get(problem.severity, 0) + 1
    return out


class GoldenRender(unittest.TestCase):
    """The generated Lua is pinned byte-for-byte against a fixed fixture."""

    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(GOLDEN_RECORD.read_text(encoding="utf-8"))
        cls.bindings = cls.record["bindings"]
        cls.lua = kb.render_lua(cls.bindings, kb.ROOT)

    def test_the_render_matches_the_golden_file(self):
        expected = GOLDEN_LUA.read_text(encoding="utf-8")
        self.assertEqual(expected, self.lua,
                         "the generated Lua drifted from tests/fixtures/keybinds.golden.lua; "
                         "if the change is intended, re-render the golden file and read the diff")

    def test_the_golden_record_is_the_shape_the_renderer_expects(self):
        self.assertEqual(2, self.record["version"])
        # One of every action type the renderer handles, so the golden file is a
        # map of the whole rendering surface and not of whichever types happened
        # to be in the record when it was written.
        types = {b["action"]["type"] for b in self.bindings}
        self.assertEqual({"exec", "shell", "dispatch", "lua", "noctalia", "iarch", "none"},
                         types, "the fixture no longer exercises every action type")

    def test_the_golden_record_validates_against_the_v2_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads((ROOT / "data" / "schemas" / "keybinds.schema.json")
                            .read_text(encoding="utf-8"))
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(self.record))
        self.assertEqual([], [e.message for e in errors],
                         "the golden fixture must be a valid v2 record, or the golden "
                         "Lua is pinned against something the schema would refuse")

    def test_the_render_is_valid_lua(self):
        """``luac -p`` in production; ``luaparser`` where there is no toolchain.

        A generated file that does not parse leaves the registry empty and trips
        the compositor's emergency binds, which is the failure the whole validate
        -then-render order exists to prevent. So the golden output is parsed, not
        just compared.
        """
        try:
            from luaparser import ast as lua_ast  # type: ignore
        except ImportError:
            self.skipTest("no Lua parser available (luac is not installed either)")
        lua_ast.parse(self.lua)  # raises on a syntax error

    def test_the_fixture_validates_clean_apart_from_the_one_carried_wheel_bind(self):
        problems = kb.validate(self.bindings, kb.ROOT)
        counts = severities(problems)
        self.assertEqual(0, counts.get(kb.ERROR, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.CONFLICT, 0), [str(p) for p in problems])
        # The single warning is the mouse_down wheel bind, carried from v1 and
        # recorded as unverified rather than silently kept or silently changed.
        self.assertEqual(1, counts.get(kb.WARNING, 0), [str(p) for p in problems])
        self.assertIn("mouse_down", problems[0].message)

    def test_disabled_and_reserved_bindings_render_to_nothing(self):
        reserved = next(b for b in self.bindings if b.get("reserved"))
        self.assertFalse(reserved["enabled"])
        self.assertNotIn(kb.key_string(reserved), self.lua,
                         "a reserved key must not reach the generated file")
        self.assertNotIn("commented", self.lua.lower())

    def test_the_two_meanings_of_locked_reach_the_file_differently(self):
        """Upstream's locked is an hl.bind option; this project's locked is not.

        The media bind carries ``flags.locked`` and must render ``locked = true``
        into its options. The terminal bind carries entry-level ``locked`` (it may
        be rebound but not deleted) and must render no such option, because there
        is no hl.bind option for it -- emitting one would tell the compositor the
        terminal works on the lock screen, which is a different claim.
        """
        media = next(b for b in self.bindings if b["id"] == "media.mute")
        terminal = next(b for b in self.bindings if b["id"] == "app.terminal")
        self.assertTrue((media.get("flags") or {}).get("locked"))
        self.assertTrue(terminal["locked"])
        media_line = next(l for l in self.lua.splitlines() if "XF86AudioMute" in l)
        terminal_line = next(l for l in self.lua.splitlines() if "SUPER + Return" in l)
        self.assertIn("locked = true", media_line)
        self.assertNotIn("locked = true", terminal_line)


class Rendering(unittest.TestCase):
    """The small pure functions the golden file is built from."""

    def test_lua_string_escapes_the_four_characters_that_break_a_lua_string(self):
        self.assertEqual(r'"a\\b"', kb.lua_string("a\\b"))
        self.assertEqual(r'"say \"hi\""', kb.lua_string('say "hi"'))
        self.assertEqual(r'"line\nbreak"', kb.lua_string("line\nbreak"))
        self.assertEqual(r'"carriage\rreturn"', kb.lua_string("carriage\rreturn"))

    def test_lua_string_does_not_escape_a_tab_a_shell_command_may_carry(self):
        # json.dumps would turn a literal tab into \\t and change the command; the
        # renderer escapes by hand precisely so it does not.
        self.assertEqual('"a\tb"', kb.lua_string("a\tb"))

    def test_render_command_quotes_each_argument_for_one_sh_c_string(self):
        # Upstream has no argv exec: the list is joined and every argument quoted,
        # so a path with a space survives and an apostrophe is quoted the POSIX way.
        self.assertEqual("kitty", kb.render_command(["kitty"]))
        self.assertEqual("'a path with spaces'", kb.render_command(["a path with spaces"]))
        self.assertEqual("""'it'"'"'s here'""", kb.render_command(["it's here"]))

    def test_key_string_joins_modifiers_then_the_key(self):
        self.assertEqual("SUPER + SHIFT + P",
                         kb.key_string({"mods": ["SUPER", "SHIFT"], "key": "P"}))
        self.assertEqual("XF86AudioMute", kb.key_string({"mods": [], "key": "XF86AudioMute"}))

    def test_handler_for_returns_none_for_an_action_that_renders_to_no_bind(self):
        self.assertIsNone(kb.handler_for(make_binding(action={"type": "none"})))

    def test_handler_for_maps_a_workspace_number_and_a_workspace_word_differently(self):
        numeric = kb.handler_for(make_binding(
            action={"type": "dispatch", "dispatcher": "hl.dsp.focus", "workspace": "1"}))
        word = kb.handler_for(make_binding(
            action={"type": "dispatch", "dispatcher": "hl.dsp.focus", "workspace": "empty"}))
        self.assertEqual("hl.dsp.focus({ workspace = 1 })", numeric)
        self.assertEqual('hl.dsp.focus({ workspace = "empty" })', word)

    def test_options_for_always_carries_the_description(self):
        options = kb.options_for(make_binding(description="Close window"))
        self.assertIn('description = "Close window"', options)

    def test_options_for_emits_the_mouse_flag(self):
        options = kb.options_for(make_binding(flags={"mouse": True}, description="Drag"))
        self.assertIn("mouse = true", options)


class Validation(unittest.TestCase):
    """The rules that stop a clean-rendering bind resolving to nothing."""

    def validate(self, *bindings: Dict[str, Any], i_know: bool = False) -> List[kb.Problem]:
        return kb.validate(list(bindings), kb.ROOT, i_know=i_know)

    def test_a_plain_ctrl_letter_is_refused(self):
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"))
        errors = [p for p in problems if p.severity == kb.ERROR]
        self.assertTrue(any("plain Ctrl+C" in p.message for p in errors),
                        [str(p) for p in problems])

    def test_i_know_downgrades_the_plain_ctrl_refusal_to_a_warning(self):
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"),
                                 i_know=True)
        self.assertEqual(0, len([p for p in problems if p.severity == kb.ERROR]),
                         [str(p) for p in problems])
        self.assertTrue(any("plain Ctrl+C" in p.message and p.severity == kb.WARNING
                            for p in problems))

    def test_super_ctrl_letters_are_allowed(self):
        problems = self.validate(make_binding(id="ok", mods=["SUPER", "CTRL"], key="c"))
        self.assertEqual(0, len([p for p in problems
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in problems])

    def test_ctrl_alt_letters_belong_to_the_system_layer_only(self):
        """Ctrl+Alt used to be offered as the remedy for a plain Ctrl+letter.

        It is not any more: the layer rule reserves it for recovery and system
        actions, so a checker that still suggested it would send the person into
        its own next refusal. Both halves are asserted, because the interesting
        failure is a rule whose remedy the following rule rejects.
        """
        refused = self.validate(make_binding(id="app", mods=["CTRL", "ALT"], key="c"))
        self.assertTrue(any(p.severity == kb.ERROR and "recovery and system layer"
                            in p.message for p in refused),
                        [str(p) for p in refused])

        allowed = self.validate(make_binding(id="sys", mods=["CTRL", "ALT"], key="c",
                                             category="System"))
        self.assertEqual(0, len([p for p in allowed
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in allowed])

    def test_the_plain_ctrl_remedy_is_one_the_checker_would_accept(self):
        """The message must not recommend a layer the layer rule then refuses."""
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"))
        message = next(p.message for p in problems if "plain Ctrl+C" in p.message)
        self.assertNotIn("Ctrl+Alt", message,
                         "the refusal recommends Ctrl+Alt, which the layer rule "
                         "reserves for recovery -- a remedy this checker rejects")
        for offered, mods in (("Super+Ctrl", ["SUPER", "CTRL"]),
                              ("Super+Shift", ["SUPER", "SHIFT"])):
            self.assertIn(offered, message)
            follow_up = self.validate(make_binding(id="remedy", mods=mods, key="c"))
            self.assertEqual(0, len([p for p in follow_up
                                     if p.severity in (kb.ERROR, kb.CONFLICT)]),
                             f"{offered}+C is recommended and then refused: "
                             f"{[str(p) for p in follow_up]}")

    def test_two_binds_on_one_combination_are_a_conflict(self):
        problems = self.validate(
            make_binding(id="first", mods=["SUPER"], key="T"),
            make_binding(id="second", mods=["SUPER"], key="T"),
        )
        conflicts = [p for p in problems if p.severity == kb.CONFLICT]
        self.assertEqual(1, len(conflicts), [str(p) for p in problems])
        self.assertIn("first", conflicts[0].message)

    def test_the_same_key_under_a_different_modifier_is_not_a_conflict(self):
        problems = self.validate(
            make_binding(id="a", mods=["SUPER"], key="T"),
            make_binding(id="b", mods=["SUPER", "SHIFT"], key="T"),
        )
        self.assertEqual(0, len([p for p in problems if p.severity == kb.CONFLICT]))

    def test_a_key_that_is_not_a_keysym_is_an_error(self):
        problems = self.validate(make_binding(id="bad.key", mods=["SUPER"], key="NotAKeysym"))
        self.assertTrue(any(p.severity == kb.ERROR and "not a keysym" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_full_stop_is_refused_because_the_keysym_is_called_period(self):
        # '.' is not a keysym; the name is 'period'. A wrong name and a key the
        # keyboard cannot produce both answer 'key not found', so the record uses
        # the real name and the validator refuses the punctuation.
        problems = self.validate(make_binding(id="bad.dot", mods=["SUPER"], key="."))
        self.assertTrue(any(p.severity == kb.ERROR for p in problems))
        self.assertEqual(0, len([p for p in self.validate(
            make_binding(id="ok.period", mods=["SUPER"], key="period"))
            if p.severity == kb.ERROR]))

    def test_a_mouse_button_code_and_a_keycode_are_accepted(self):
        for key in ("mouse:272", "code:30", "10"):
            with self.subTest(key=key):
                problems = self.validate(make_binding(id="ok", mods=["SUPER"], key=key))
                self.assertEqual(0, len([p for p in problems
                                         if p.severity in (kb.ERROR, kb.CONFLICT)]),
                                 [str(p) for p in problems])

    def test_an_unknown_modifier_is_an_error(self):
        problems = self.validate(make_binding(id="bad.mod", mods=["HYPER"], key="T"))
        self.assertTrue(any(p.severity == kb.ERROR and "unknown modifier" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_repeated_modifier_is_an_error(self):
        problems = self.validate(make_binding(id="bad.rep", mods=["SUPER", "SUPER"], key="T"))
        self.assertTrue(any(p.severity == kb.ERROR and "repeated" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_binding_with_no_description_is_an_error(self):
        problems = self.validate(make_binding(id="bad.desc", description="   "))
        self.assertTrue(any(p.severity == kb.ERROR and "no description" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_an_exec_action_with_no_argv_is_an_error(self):
        problems = self.validate(make_binding(id="bad.exec", action={"type": "exec", "command": []}))
        self.assertTrue(any(p.severity == kb.ERROR and "no argv" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_dispatcher_outside_the_verified_tree_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.dsp", action={"type": "dispatch", "dispatcher": "hl.dsp.window.nope"}))
        self.assertTrue(any(p.severity == kb.ERROR and "not in the verified" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_noctalia_verb_outside_the_record_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.verb", action={"type": "noctalia", "verb": "not-a-verb"}))
        self.assertTrue(any(p.severity == kb.ERROR and "noctalia verb" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_shell_action_with_no_reason_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.shell", action={"type": "shell", "script": "a | b"}))
        self.assertTrue(any(p.severity == kb.ERROR and "no reason" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_duplicate_id_is_an_error(self):
        problems = self.validate(
            make_binding(id="same", mods=["SUPER"], key="T"),
            make_binding(id="same", mods=["SUPER"], key="Y"),
        )
        self.assertTrue(any(p.severity == kb.ERROR and "appears 2 times" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_disabled_binding_is_not_held_to_the_keysym_check(self):
        # A reserved key renders to nothing, so its key is never resolved; the
        # other two reserved keys are deliberately not keysyms anyone would bind.
        problems = self.validate(make_binding(
            id="reserved", mods=["SUPER", "SHIFT"], key="H", enabled=False,
            action={"type": "none"}, reserved=True))
        self.assertEqual(0, len([p for p in problems if p.severity == kb.ERROR]),
                         [str(p) for p in problems])


class Merge(unittest.TestCase):
    """Defaults plus a person's differences, by id."""

    def setUp(self):
        self.defaults = {"bindings": [
            make_binding(id="app.terminal", mods=["SUPER"], key="Return",
                         description="Terminal", locked=True),
            make_binding(id="app.browser", mods=["SUPER"], key="B", description="Browser"),
        ]}

    def test_a_rebind_carries_only_the_difference_and_keeps_the_rest(self):
        overrides = {"bindings": [{"id": "app.terminal", "mods": ["SUPER", "ALT"], "key": "T"}]}
        merged = {b["id"]: b for b in kb.merge(self.defaults, overrides)}
        terminal = merged["app.terminal"]
        self.assertEqual(["SUPER", "ALT"], terminal["mods"])
        self.assertEqual("T", terminal["key"])
        self.assertEqual("Terminal", terminal["description"], "the description is from the default")
        self.assertTrue(terminal["locked"], "a field the override did not mention survives")

    def test_a_binding_the_defaults_do_not_have_is_appended(self):
        overrides = {"bindings": [{"id": "user.custom", "mods": ["SUPER", "ALT"], "key": "X",
                                   "action": {"type": "exec", "command": ["true"]},
                                   "description": "Mine", "category": "Custom",
                                   "enabled": True, "locked": False}]}
        merged = kb.merge(self.defaults, overrides)
        self.assertEqual(["app.terminal", "app.browser", "user.custom"],
                         [b["id"] for b in merged])

    def test_the_default_order_is_preserved(self):
        merged = kb.merge(self.defaults, {"bindings": [{"id": "app.browser", "key": "W"}]})
        self.assertEqual(["app.terminal", "app.browser"], [b["id"] for b in merged])

    def test_no_override_file_means_the_defaults_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": str(Path(tmp) / "cfg"), "HOME": tmp}
            self.assertEqual({}, kb.user_overrides(env))
            merged = kb.merge(self.defaults, kb.user_overrides(env))
            self.assertEqual([b["id"] for b in self.defaults["bindings"]],
                             [b["id"] for b in merged])

    def test_a_broken_override_file_does_not_break_the_session(self):
        """The recovery behaviour: a stray comma falls back to defaults, not a crash."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            cfg.mkdir(parents=True)
            (cfg / "keybinds.json").write_text("{ this is not json ,,, }", encoding="utf-8")
            env = {"IARCH_CONFIG_DIR": str(cfg), "HOME": tmp}
            self.assertEqual({}, kb.user_overrides(env),
                             "a broken user file must yield empty overrides, not raise")
            merged = kb.merge(self.defaults, kb.user_overrides(env))
            self.assertEqual(2, len(merged), "the session still has its defaults")

    def test_the_override_path_is_keybinds_json_and_not_a_double_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": str(Path(tmp) / "cfg"), "HOME": tmp}
            self.assertEqual("keybinds.json", kb.user_override_path(env).name)


class ShippedRecord(unittest.TestCase):
    """The acceptance criterion: the shipped defaults are clean."""

    @classmethod
    def setUpClass(cls):
        cls.record = kb.default_record(kb.ROOT)
        cls.bindings = kb.merge(cls.record, {})

    def test_check_reports_zero_conflicts_and_zero_errors_on_the_defaults(self):
        problems = kb.validate(self.bindings, kb.ROOT)
        counts = severities(problems)
        self.assertEqual(0, counts.get(kb.CONFLICT, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.ERROR, 0), [str(p) for p in problems])

    def test_no_plain_ctrl_letter_is_bound_in_the_defaults(self):
        for binding in self.bindings:
            if not binding.get("enabled"):
                continue
            with self.subTest(id=binding["id"]):
                self.assertFalse(binding["mods"] == ["CTRL"] and len(binding["key"]) == 1
                                 and binding["key"].isalpha())

    def test_the_list_json_feed_carries_what_a_cheat_sheet_needs(self):
        """The overlay reads `list --json`; this pins the shape it will read.

        Taken from the real command rather than rebuilt here, because a hand-copy of
        the payload is a second opinion that drifts the first time a field is added --
        and the overlay is exactly the consumer that would then render blanks.
        """
        payload = list_json()
        self.assertTrue(payload)
        for entry in payload:
            for field in ("id", "keys", "description", "category", "enabled", "action",
                          "locked", "static", "reserved"):
                self.assertIn(field, entry)
        # A cheat sheet groups by category and shows the combination and the description.
        terminal = next(e for e in payload if e["id"] == "applications.terminal")
        self.assertEqual("SUPER + RETURN", terminal["keys"])
        self.assertTrue(terminal["description"])

    def test_the_json_feed_marks_the_static_and_reserved_bindings(self):
        """The overlay has to tell a hand-written bind from a rendered one.

        A cheat sheet that lists Ctrl+Alt+R as an ordinary bind is not wrong about
        the key, but it cannot say that the bind lives in a different file and calls
        a command the installer has not shipped yet -- which is the part a person
        troubleshooting a dead shortcut needs.
        """
        payload = {e["id"]: e for e in list_json()}
        recovery = payload["recovery.reapply-defaults"]
        self.assertTrue(recovery["static"])
        self.assertTrue(recovery["enabled"])
        self.assertFalse(payload["reserved.ctrl-alt-backspace"]["enabled"])
        self.assertTrue(payload["reserved.ctrl-alt-backspace"]["reserved"])
        self.assertFalse(payload["applications.terminal"]["static"])


class ConfirmationRule(unittest.TestCase):
    """Nothing that ends a session or the machine goes on a key without a menu.

    A key that logs out is a key that logs out by accident: a mistyped combination,
    a child, a cat. The rule is not "never bind these" but "bind the confirmation",
    and the shell already draws one, so both halves are asserted -- the refusal and
    the thing that is allowed instead.
    """

    def errors(self, action: Dict[str, Any]) -> List[kb.Problem]:
        problems = kb.validate(
            [make_binding(id="destructive", mods=["SUPER", "SHIFT"], key="E",
                          action=action)], kb.ROOT)
        return [p for p in problems if p.severity == kb.ERROR]

    def test_the_compositor_exit_dispatcher_is_refused(self):
        errors = self.errors({"type": "dispatch", "dispatcher": "exit"})
        self.assertTrue(any("hl.dsp.exit" in p.message for p in errors),
                        [str(p) for p in errors])

    def test_every_spelling_of_a_destructive_session_action_is_refused(self):
        """The same mistake is reachable three ways, so all three are covered."""
        for action in (
            {"type": "noctalia", "verb": "session", "args": ["logout"]},
            {"type": "noctalia", "verb": "session", "args": ["shutdown"]},
            {"type": "noctalia", "verb": "session", "args": ["reboot"]},
            {"type": "exec", "command": ["noctalia", "msg", "session", "logout"]},
            {"type": "exec", "command": ["systemctl", "poweroff", "-i"]},
            {"type": "exec", "command": ["loginctl", "terminate-session"]},
            {"type": "exec", "command": ["hyprctl", "dispatch", "exit"]},
            {"type": "exec", "command": ["/usr/bin/reboot"]},
        ):
            with self.subTest(action=action):
                errors = self.errors(action)
                self.assertTrue(any("the moment the key goes down" in p.message
                                    for p in errors),
                                f"not refused: {[str(p) for p in errors]}")

    def test_the_session_menu_is_allowed_because_the_menu_is_the_confirmation(self):
        for action in (
            {"type": "noctalia", "verb": "panel-toggle", "args": ["session"]},
            {"type": "exec", "command": ["noctalia", "msg", "panel-toggle", "session"]},
        ):
            with self.subTest(action=action):
                self.assertEqual([], [str(p) for p in self.errors(action)],
                                 "the menu that asks before ending a session was "
                                 "refused by the rule that exists to make people use it")

    def test_lock_and_suspend_are_not_treated_as_destructive(self):
        """Both are undoable: logging back in, or waking the machine."""
        for action in (
            {"type": "exec", "command": ["noctalia", "msg", "session", "lock"]},
            {"type": "noctalia", "verb": "session", "args": ["suspend"]},
            {"type": "noctalia", "verb": "session", "args": ["lock-and-suspend"]},
        ):
            with self.subTest(action=action):
                self.assertEqual([], [str(p) for p in self.errors(action)])

    def test_the_shipped_record_binds_the_menu_and_not_the_action(self):
        bindings = kb.default_record(kb.ROOT)["bindings"]
        exit_entry = next(b for b in bindings if b["id"] == "session.exit-menu")
        self.assertEqual([], [str(p) for p in self.errors(exit_entry["action"])])
        self.assertEqual(["session"], exit_entry["action"].get("args"),
                         "Super+Shift+E must open the shell's own session panel, which "
                         "is a builtin panel id in noctalia v5.4.1 "
                         "(src/launcher/panel_catalog.cpp), rather than run logout")


class LayerRule(unittest.TestCase):
    """The modifier layers, kept for what each one is for."""

    def problems(self, **over: Any) -> List[kb.Problem]:
        return kb.validate([make_binding(id="layer", key="c", **over)], kb.ROOT)

    def test_super_alt_is_empty_on_purpose(self):
        problems = self.problems(mods=["SUPER", "ALT"], category="Test")
        self.assertTrue(any(p.severity == kb.ERROR and "kept empty on purpose"
                            in p.message for p in problems),
                        [str(p) for p in problems])

    def test_bare_ctrl_alt_outside_the_system_layer_is_an_error(self):
        """An error, not a warning: the recovery combo lives on this exact layer."""
        problems = self.problems(mods=["CTRL", "ALT"], category="Applications")
        self.assertTrue(any(p.severity == kb.ERROR and "safety net" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_bare_ctrl_alt_inside_the_system_layer_is_clean(self):
        problems = self.problems(mods=["CTRL", "ALT"], category="System")
        self.assertEqual(0, len([p for p in problems
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in problems])

    def test_super_ctrl_alt_outside_the_system_layer_is_reported_as_debt(self):
        """A warning that names the two v1 binds, so the debt is printed every run.

        Not an error, because both binds work and every sensible destination key is
        already taken; relocating them belongs with the next laying-out of the map.
        An invisible exception would be worse than a printed one.
        """
        problems = self.problems(mods=["SUPER", "CTRL", "ALT"],
                                 category="Move Window Across Workspaces")
        matching = [p for p in problems if "Super+Ctrl+Alt" in p.message]
        self.assertEqual(1, len(matching), [str(p) for p in problems])
        self.assertEqual(kb.WARNING, matching[0].severity)

    def test_the_shipped_map_has_no_errors_and_only_the_known_layer_debt(self):
        bindings = kb.merge(kb.default_record(kb.ROOT), {})
        problems = kb.validate(bindings, kb.ROOT)
        self.assertEqual(0, len([p for p in problems
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in problems])
        debt = [p for p in problems if "Super+Ctrl+Alt" in p.message]
        self.assertEqual({"move.next", "move.previous"}, {p.binding_id for p in debt},
                         "the layer debt is exactly the two v1 workspace moves; a third "
                         "means something else moved into the recovery layer")

    def test_the_primary_and_secondary_layers_are_ungoverned(self):
        for mods in (["SUPER"], ["SUPER", "SHIFT"], ["SUPER", "CTRL"]):
            with self.subTest(mods=mods):
                problems = self.problems(mods=mods, category="Applications")
                self.assertEqual(0, len([p for p in problems
                                         if p.severity in (kb.ERROR, kb.CONFLICT)]),
                                 [str(p) for p in problems])


class StaticBindings(unittest.TestCase):
    """A bind described in the record and implemented by hand in keybind.lua."""

    def temp_root(self, hand_written: str) -> Path:
        """A root with the files render_lua and the cross-check read."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".config" / "hypr").mkdir(parents=True)
        (tmp / "data" / "design").mkdir(parents=True)
        (tmp / ".config" / "hypr" / "keybind.lua").write_text(hand_written,
                                                              encoding="utf-8")
        (tmp / "data" / "design" / "keybinds.json").write_bytes(
            (kb.ROOT / "data" / "design" / "keybinds.json").read_bytes())
        return tmp

    def binding(self, **over: Any) -> Dict[str, Any]:
        base = make_binding(id="recovery.test", mods=["CTRL", "ALT"], key="R",
                            category="System", static=True,
                            action={"type": "exec",
                                    "command": ["iarch-keybinds", "reset", "--all"]},
                            unverified="Carried as unverified by the test that reads it.")
        base.update(over)
        return base

    def test_the_render_skips_a_static_binding(self):
        rendered = kb.render_lua([self.binding()], kb.ROOT, "test")
        self.assertNotIn('hl.bind("CTRL + ALT + R"', rendered,
                         "a static binding the render also emits is two handlers on "
                         "one key, and which runs depends on require() order")

    def test_the_shipped_record_and_the_static_file_agree(self):
        bindings = kb.merge(kb.default_record(kb.ROOT), {})
        self.assertEqual([], [str(p) for p in kb.static_bindings_agree(bindings, kb.ROOT)])

    def test_a_static_binding_missing_from_the_file_is_an_error(self):
        root = self.temp_root("-- nothing hand-written here\nreturn true\n")
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "has no hl.bind" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_static_binding_running_a_different_command_is_an_error(self):
        """The drift that matters: both files valid, disagreeing about the key."""
        root = self.temp_root('hl.bind("CTRL + ALT + R", function() end)\nreturn true\n')
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "disagree" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_missing_static_file_is_an_error_not_a_silence(self):
        root = self.temp_root("return true\n")
        (root / ".config" / "hypr" / "keybind.lua").unlink()
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "is missing" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_non_static_binding_is_not_held_to_the_static_file(self):
        root = self.temp_root("return true\n")
        plain = self.binding(static=False, unverified=None)
        plain.pop("unverified")
        self.assertEqual([], [str(p) for p in kb.static_bindings_agree([plain], root)])


class Reset(unittest.TestCase):
    """`reset` is what the recovery combo runs, so it is tested as a command."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".config" / "iarch").mkdir(parents=True)
        self.override = self.home / ".config" / "iarch" / "keybinds.json"
        self.session_lua = self.home / ".config" / "hypr" / "generated" / "keybinds.lua"
        self.backups = self.home / ".local" / "state" / "iarch" / "backups"
        self._saved = {k: os.environ.get(k) for k in ("HOME", "IARCH_CONFIG_DIR")}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def write_override(self, payload: Dict[str, Any]) -> None:
        self.override.write_text(json.dumps(payload), encoding="utf-8")

    def run_reset(self, *argv: str) -> int:
        os.environ["HOME"] = str(self.home)
        os.environ.pop("IARCH_CONFIG_DIR", None)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = kb.main(["reset", *argv])
        self.output = buffer.getvalue()
        return code

    def test_reset_all_drops_the_override_and_keeps_a_backup(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "W",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_reset("--all"))
        self.assertFalse(self.override.exists(), "the override survived a reset --all")
        self.assertTrue(self.session_lua.is_file(), "no session file was written")
        self.assertIn('hl.bind("SUPER + Q"', self.session_lua.read_text(encoding="utf-8"),
                      "the shipped default for close-window did not come back")
        self.assertEqual(1, len(list(self.backups.glob("*keybinds.json*.bak"))),
                         "the person's map was deleted with no way back")

    def test_reset_writes_the_session_copy_and_not_the_repository_artifact(self):
        """The file the compositor reads is a copy, so fixing the repo fixes nothing."""
        self.write_override({"bindings": [{"id": "window.close", "key": "W",
                                           "description": "mine"}]})
        before = kb.GENERATED.read_bytes()
        self.assertEqual(0, self.run_reset("--all"))
        self.assertEqual(before, kb.GENERATED.read_bytes(),
                         "reset rewrote the checked-in artifact CI keeps fresh")
        self.assertTrue(self.session_lua.is_file())

    def test_reset_by_id_leaves_the_other_differences_alone(self):
        self.write_override({"bindings": [
            {"id": "window.close", "key": "W", "description": "mine"},
            {"id": "applications.terminal", "key": "Return", "mods": ["SUPER", "CTRL"],
             "description": "also mine"},
        ]})
        self.assertEqual(0, self.run_reset("window.close"))
        kept = [e["id"] for e in json.loads(self.override.read_text(encoding="utf-8"))["bindings"]]
        self.assertEqual(["applications.terminal"], kept,
                         "a targeted reset must drop exactly the named difference")

    def test_an_id_the_shipped_map_does_not_have_is_refused(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "W",
                                           "description": "mine"}]})
        self.assertEqual(2, self.run_reset("not.a.binding"))
        self.assertTrue(self.override.exists(),
                        "an unknown id changed the person's map")

    def test_reset_with_no_target_says_what_it_needs(self):
        self.assertEqual(2, self.run_reset())
        self.assertIn("--all", self.output)

    def test_a_reset_that_would_not_validate_changes_nothing(self):
        """The safety is the ordering: refuse before touching, not undo after."""
        self.write_override({"bindings": [{"id": "window.close", "key": "W",
                                           "description": "mine"}]})
        with unittest.mock.patch.object(kb, "default_record",
                                        return_value=self.broken_record()) as patched:
            self.assertEqual(1, self.run_reset("--all"))
            self.assertTrue(patched.called)
        self.assertTrue(self.override.exists(),
                        "the override was dropped even though the reset was refused")
        self.assertIn("nothing was changed", self.output)
        self.assertFalse(self.session_lua.exists(),
                         "a refused reset still wrote a session file")

    @staticmethod
    def broken_record() -> Dict[str, Any]:
        record = kb.default_record(kb.ROOT)
        record["bindings"][0]["key"] = "NotAKeysym"
        return record


if __name__ == "__main__":
    unittest.main()
