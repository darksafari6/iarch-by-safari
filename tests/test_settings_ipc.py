#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the shell's IPC: what may be sent, and what a machine without it must say.

``data/design/noctalia-ipc.json`` records 39 verbs read out of one header in the shell's
own tree, and every one of them is accounted for in one of three ways: sent, by something
named in ``used_by``; recorded and refused, with a ``not_used_note`` or a note on the
argument that explains what this project does instead; or listed in ``not_used``. A verb in
none of the three is a gap nobody can see, which is why the first test class here counts
them rather than spot-checking a few.

The distinction that the tests keep pulling on is between **not answering** and
**answering no**. On this machine the shell binary is absent, so every read comes back
``unverified`` with the sentence "noctalia is not installed" and ``exit_code`` still
``None`` -- the command never ran, so there is no exit code to have. A page that drew
``None`` as "off" would show a person a switch that is not off, on a machine where nobody
knows. That is the whole reason ``runner`` has three verdicts instead of a boolean, and the
reason ``available()`` is a sentence and not a flag.

The refusals are verdicts too, and never exceptions. ``send()`` given a verb the record
does not have answers ``failed`` with the record's name in the sentence; ``session()`` given
``shutdown`` answers ``failed`` and explains that a panel able to end a session turns one
mis-click into lost work. Nothing here raises, because the callers are rows on a page, and
an exception in a click handler is a window that stops responding rather than a message.

Two things are *not* refused locally, and the tests say so on purpose: ``panel()`` and
``power_profile()`` pass their argument through, because the record enumerates neither the
panel ids nor the profile names -- refusing an id this project has not read would be
inventing a list, and the honest answer is to let the shell refuse it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings import pages  # noqa: E402
from iarch_settings.pages.plan import default_context  # noqa: E402
from iarch_settings.services import noctalia, runner  # noqa: E402

RECORD = json.loads((ROOT / "data" / "design" / "noctalia-ipc.json").read_text(
    encoding="utf-8"))
VERBS: List[Dict[str, Any]] = RECORD["verbs"]
VERB_NAMES = [verb["verb"] for verb in VERBS]
NOT_USED: List[Dict[str, Any]] = RECORD["not_used"]
NOT_COMMANDS: List[Dict[str, Any]] = RECORD["not_commands"]

#: Every noctalia action any page in this application can send.
PAGE_ACTIONS = ("noctalia.caffeine", "noctalia.lock_now", "noctalia.nightlight",
                "noctalia.open_control_center", "noctalia.open_shell_settings",
                "noctalia.screen_off", "noctalia.screen_on", "noctalia.screenshot_region",
                "noctalia.screenshot_window", "noctalia.set_dnd", "noctalia.suspend_now",
                "noctalia.toggle_bluetooth", "noctalia.toggle_network",
                "noctalia.toggle_wifi", "noctalia.volume_osd")


def outcome(verdict: str, *, stdout: str = "", reason: str = "",
            exit_code: Optional[int] = None) -> runner.Outcome:
    return runner.Outcome(["noctalia", "msg", "config-get", "theme.mode"], verdict,
                          exit_code=exit_code, stdout=stdout, reason=reason)


class TestEveryVerbIsAccountedFor(unittest.TestCase):
    """Sent, refused with a reason, or listed -- the fourth state is a gap nobody sees."""

    def test_the_record_carries_thirty_nine_verbs_and_the_module_sees_the_same_thirty_nine(self):
        self.assertEqual(39, len(VERBS))
        self.assertEqual(39, len(noctalia.verb_names()))
        self.assertEqual(sorted(VERB_NAMES), sorted(noctalia.verb_names()),
                         "the module's verb list and the record's are two copies of one "
                         "decision, and they have drifted")

    def test_verbs_is_a_dictionary_keyed_by_the_verb_itself(self):
        verbs = noctalia.verbs()
        self.assertIsInstance(verbs, dict)
        for name, entry in verbs.items():
            with self.subTest(verb=name):
                self.assertEqual(name, entry["verb"],
                                 "a verb is filed under a key that is not its own spelling, "
                                 "so a lookup can succeed for the wrong verb")

    def test_no_verb_is_both_used_and_refused(self):
        for verb in VERBS:
            with self.subTest(verb=verb["verb"]):
                self.assertFalse(verb.get("used_by") and verb.get("not_used_note"),
                                 f"{verb['verb']} is named as sent and explained as not sent")

    def test_a_verb_with_no_used_by_carries_an_explanation_somewhere(self):
        """The rule the empty `used_by` lists broke: silence is not a reason."""
        unexplained = []
        for verb in VERBS:
            if verb.get("used_by"):
                continue
            explained = bool(verb.get("note")) or bool(verb.get("not_used_note")) or any(
                str(argument.get("note") or "").strip()
                for argument in verb.get("arguments") or [])
            listed = any(verb["verb"] in str(entry.get("verb") or "")
                         for entry in NOT_USED)
            if not explained and not listed:
                unexplained.append(verb["verb"])
        self.assertEqual([], unexplained,
                         "these verbs are recorded and nothing says why they are not sent, "
                         "so the next reader cannot tell a deliberate refusal from an "
                         "unfinished one")

    def test_a_used_by_sentence_points_at_something_somebody_can_open(self):
        """The record's entries run from a file and a function to a whole sentence; what
        every one of them has in common is that they name a place to go and look."""
        for verb in VERBS:
            for sentence in verb.get("used_by") or ():
                with self.subTest(verb=verb["verb"]):
                    self.assertTrue("/" in sentence or ":" in sentence or
                                    "page" in sentence.lower(),
                                    f"the sentence does not point at anything: {sentence}")
                    self.assertNotEqual("iarch/settings-app", sentence.strip(),
                                        "a `used_by` entry that names only the project says "
                                        "somebody uses this verb without saying who")

    def test_every_verb_carries_a_line_cite_from_the_pinned_release(self):
        for verb in VERBS:
            with self.subTest(verb=verb["verb"]):
                self.assertTrue(str(verb["evidence"]).startswith("src/cli/schema_msg.h:"),
                                f"{verb['verb']}'s evidence does not name the header and a "
                                f"line, so nobody can check that the verb exists")
                self.assertTrue(str(verb.get("description") or "").strip())

    def test_the_record_says_how_it_was_checked(self):
        self.assertTrue(str(RECORD.get("verified_against") or "").strip(),
                        "the record does not say which release of the shell it was read "
                        "from, so a verb added upstream looks like a mistake here")

    def test_the_not_used_entries_are_refusals_with_consequences_not_preferences(self):
        self.assertTrue(NOT_USED)
        for entry in NOT_USED:
            with self.subTest(verb=str(entry["verb"])[:28]):
                self.assertGreater(len(entry["why"].split()), 14,
                                   "a refusal whose reason is one clause is a citation")
                self.assertTrue(str(entry["evidence"]).strip())

    def test_the_session_verbs_that_can_lose_work_are_refused_together(self):
        entry = next(item for item in NOT_USED
                     if "logout" in str(item["verb"]))
        for action in ("logout", "reboot", "shutdown"):
            with self.subTest(action=action):
                self.assertIn(action, entry["verb"])
        self.assertIn("mis-click", entry["why"],
                      "the reason has to say what goes wrong, and 'lost work' is what goes "
                      "wrong")

    def test_the_module_refuses_the_same_session_actions_the_record_does(self):
        self.assertEqual(("lock", "suspend", "lock-and-suspend"), noctalia.SESSION_ACTIONS)
        self.assertEqual(("greeter-sync", "effects-profile-set"), noctalia.NOT_USED)
        refused_in_record = " ".join(str(entry.get("verb") or "") for entry in NOT_USED)
        for name in noctalia.NOT_USED:
            with self.subTest(verb=name):
                # These two are in the record's `not_used` block and not in its `verbs`
                # array: the array is what may be sent, the block is what may not.
                self.assertIn(name, refused_in_record,
                              f"{name} is refused by the module and the record's not_used "
                              f"block does not name it, so the refusal is unverifiable")
                self.assertNotIn(name, VERB_NAMES,
                                 f"{name} is refused by the module and listed as a verb, so "
                                 f"the record offers what the code will not send")


class TestTheTwoTrapsTheHeaderSets(unittest.TestCase):
    """204 quoted strings in one header, of which the verbs are a subset."""

    def test_a_positional_argument_name_is_not_a_verb(self):
        self.assertTrue(NOT_COMMANDS)
        first = NOT_COMMANDS[0]
        self.assertEqual("monitor-selector", first["spelling"])
        self.assertNotIn("monitor-selector", VERB_NAMES,
                         "monitor-selector was extracted as a verb, and sending it would be "
                         "refused by the shell's own lookup and only at runtime")
        self.assertIn("positional", first["what_it_really_is"].lower())

    def test_the_module_agrees_with_the_record_about_what_is_not_a_command(self):
        recorded = {entry["spelling"] for entry in NOT_COMMANDS}
        module = set(noctalia.not_commands())
        self.assertTrue(module, "the module publishes no not-commands, so a caller cannot "
                                "tell an argument name from a verb")
        for spelling in module:
            with self.subTest(spelling=spelling[:30]):
                self.assertNotIn(spelling, VERB_NAMES)
        self.assertTrue(recorded & module or all(any(part in " ".join(recorded)
                                                     for part in spelling.split(", "))
                                                 for spelling in module),
                        "the module's not-commands and the record's are two lists of one "
                        "decision")

    def test_a_verb_nobody_thought_of_is_refused_before_it_is_sent(self):
        result = noctalia.send("made-up-verb")
        self.assertEqual(runner.FAILED, result.verdict,
                         "an unrecorded verb reached the command line, so the record is not "
                         "the list of what may be sent")
        self.assertIn("made-up-verb", result.reason)
        self.assertIn("noctalia-ipc.json", result.reason,
                      "the refusal does not name the record, so a person cannot go and look")
        self.assertIsNone(result.exit_code,
                          "the refusal says the verb was not sent and then produced an exit "
                          "status, so it reached the command line")


class TestNotAnsweringIsNotAnsweringNo(unittest.TestCase):
    """Three verdicts, and the reason a boolean would be a bug on this machine."""

    def test_an_absent_binary_is_unverified_and_never_failed(self):
        result = runner.run(runner.NOCTALIA_BIN, ["msg", "config-get", "theme.mode"])
        self.assertIsNone(runner.which(runner.NOCTALIA_BIN),
                          "this sandbox has the shell installed, so the tests below are not "
                          "testing what they claim to test")
        self.assertEqual(runner.UNVERIFIED, result.verdict)
        self.assertFalse(result.ran)
        self.assertFalse(result.ok)

    def test_a_command_that_never_ran_has_no_exit_code(self):
        result = runner.run(runner.NOCTALIA_BIN, ["msg", "lock-now"])
        self.assertIsNone(result.exit_code,
                          "a command that never ran was given an exit code, and 0 is the "
                          "code a caller reads as success")
        self.assertIn("not installed", result.reason)

    def test_the_argv_is_recorded_even_when_the_command_never_ran(self):
        result = runner.run(runner.NOCTALIA_BIN, ["msg", "lock-now"])
        self.assertEqual(["noctalia", "msg", "lock-now"], list(result.argv),
                         "the page has to be able to show the command it could not run")

    def test_available_is_a_sentence_that_says_unverified_rather_than_off(self):
        sentence = noctalia.available()
        self.assertIsInstance(sentence, str)
        self.assertIn("PATH", sentence)
        self.assertIn("unverified", sentence,
                      "the sentence does not say unverified, so a page drawing it would "
                      "read as 'the shell is off'")
        self.assertIn("not", sentence)

    def test_presence_answers_for_every_binary_the_module_knows(self):
        presence = runner.presence()
        self.assertEqual(set(runner.BINARIES), set(presence),
                         "presence() and BINARIES disagree, so a caller checking one name "
                         "gets a KeyError instead of an answer")
        self.assertEqual(7, len(runner.BINARIES))
        for name, present in presence.items():
            with self.subTest(binary=name):
                self.assertIsInstance(present, bool)
                self.assertEqual(present, runner.which(name) is not None)

    def test_a_read_of_a_shell_key_comes_back_unverified_and_not_none_as_a_value(self):
        value, verdict, reason = noctalia.read("audio.sound_volume")
        self.assertIsNone(value)
        self.assertEqual(runner.UNVERIFIED, verdict,
                         "an absent shell was reported as a failure, and a page drawing that "
                         "shows an error for a machine that is simply not running the shell")
        self.assertIn("not installed", reason)

    def test_the_three_verdicts_are_three_different_strings(self):
        self.assertEqual({"ok", "failed", "unverified"},
                         {runner.OK, runner.FAILED, runner.UNVERIFIED})

    def test_a_timeout_is_a_verdict_and_not_an_exception(self):
        """A shell that is installed but not answering is still a machine that has one."""
        result = runner.run("sleep", ["30"], timeout=0.05)
        self.assertEqual(runner.FAILED, result.verdict)
        self.assertFalse(result.ok)
        self.assertTrue(result.reason, "a timed-out command gave no reason, so the page "
                                       "cannot tell a hang from a refusal")


class TestRefusalsAreVerdictsAndNotExceptions(unittest.TestCase):
    """The callers are rows on a page, so nothing here may raise."""

    def test_a_session_action_that_can_end_a_session_is_refused_with_its_consequence(self):
        for action in ("shutdown", "reboot", "logout", "reboot-uefi"):
            result = noctalia.session(action)
            with self.subTest(action=action):
                self.assertEqual(runner.FAILED, result.verdict)
                self.assertIsNone(result.exit_code,
                                  "a locally refused verb produced an exit status, so it "
                                  "reached the command line")
                self.assertEqual("", result.stdout,
                                 "a refusal has no reply to read, and a page that reads one "
                                 "would show the shell answering something it was never asked")
                self.assertIn(action, result.reason)
                self.assertIn("lock", result.reason,
                              "the refusal has to say what this application offers instead")

    def test_ran_means_not_unverified_and_verdict_is_the_only_field_to_branch_on(self):
        """A local refusal answers ``failed``, so ``ran`` is True for a command that never
        ran; the class docstring says ``verdict`` is the only field a caller branches on."""
        refused = noctalia.session("shutdown")
        absent = runner.run(runner.NOCTALIA_BIN, ["msg", "session", "lock"])
        self.assertTrue(refused.ran, "`ran` is defined as verdict != unverified")
        self.assertFalse(absent.ran)
        self.assertNotEqual(refused.verdict, absent.verdict,
                            "a refusal and an absent program give the same verdict, so a "
                            "page cannot tell 'we will not' from 'we could not'")
        self.assertEqual(runner.FAILED, refused.verdict)
        self.assertEqual(runner.UNVERIFIED, absent.verdict)

    def test_a_session_action_that_is_offered_is_built_and_sent(self):
        for action in noctalia.SESSION_ACTIONS:
            result = noctalia.session(action)
            with self.subTest(action=action):
                self.assertNotEqual(runner.FAILED, result.verdict,
                                    f"{action} is offered by SESSION_ACTIONS and refused")
                self.assertEqual(["noctalia", "msg", "session", action], list(result.argv))

    def test_the_lock_and_suspend_helpers_send_the_recorded_verbs(self):
        self.assertEqual(["session", "lock"], list(noctalia.lock_now().argv[2:]))
        self.assertEqual(["session", "suspend"], list(noctalia.suspend_now().argv[2:]))

    def test_a_screenshot_kind_the_record_does_not_have_is_refused(self):
        result = noctalia.screenshot("bogus")
        self.assertEqual(runner.FAILED, result.verdict)
        self.assertIn("bogus", result.reason)
        self.assertEqual(["screenshot-region"], list(noctalia.screenshot_region().argv[2:]))
        self.assertEqual(["screenshot-window"], list(noctalia.screenshot_window().argv[2:]))

    def test_a_toggle_with_no_verb_behind_it_is_refused(self):
        result = noctalia.toggle("bogus")
        self.assertEqual(runner.FAILED, result.verdict)
        self.assertIn("bogus", result.reason)
        for kind, verb in (("wifi", "wifi-toggle"), ("bluetooth", "bluetooth-toggle"),
                           ("network", "network-toggle")):
            with self.subTest(kind=kind):
                self.assertEqual([verb], list(noctalia.toggle(kind).argv[2:]))

    def test_a_screen_action_is_off_or_on_and_nothing_else(self):
        result = noctalia.screen("bogus")
        self.assertEqual(runner.FAILED, result.verdict)
        self.assertIn("off", result.reason)
        self.assertEqual(["dpms-off"], list(noctalia.screen_off().argv[2:]))
        self.assertEqual(["dpms-on"], list(noctalia.screen_on().argv[2:]))

    def test_a_theme_mode_outside_the_three_is_refused_by_name(self):
        result = noctalia.set_theme_mode("bogus")
        self.assertEqual(runner.FAILED, result.verdict)
        for mode in ("dark", "light", "auto"):
            with self.subTest(mode=mode):
                self.assertIn(mode, result.reason)
        self.assertEqual(["theme-mode-set", "dark"],
                         list(noctalia.set_theme_mode("dark").argv[2:]))

    def test_a_panel_id_is_passed_through_because_the_record_does_not_enumerate_them(self):
        """Refusing an id this project has not read would be inventing a list."""
        result = noctalia.panel("not-a-panel")
        self.assertNotEqual(runner.FAILED, result.verdict,
                            "a panel id was refused locally, and the record enumerates no "
                            "panel ids, so the list it was checked against was invented")
        self.assertEqual(["panel-open", "not-a-panel"], list(result.argv[2:]))
        self.assertEqual(["panel-open", noctalia.PANEL_CONTROL_CENTER],
                         list(noctalia.open_control_center().argv[2:]))
        self.assertEqual(["panel-open", noctalia.PANEL_LAUNCHER],
                         list(noctalia.open_launcher().argv[2:]))

    def test_a_panel_can_be_opened_with_a_context_and_the_context_reaches_the_argv(self):
        self.assertEqual(["panel-open", "control-center", "audio"],
                         list(noctalia.panel("control-center", "audio").argv[2:]))

    def test_a_power_profile_is_passed_through_for_the_same_reason(self):
        result = noctalia.power_profile("not-a-profile")
        self.assertNotEqual(runner.FAILED, result.verdict)
        self.assertEqual(["power-set", "not-a-profile"], list(result.argv[2:]))


class TestTheReplyIsReadRatherThanGuessed(unittest.TestCase):
    """The shell answers on stdout, and a refusal arrives as text, not as an exit code."""

    def test_the_error_prefix_is_the_recorded_one(self):
        self.assertEqual("error:", noctalia.ERROR_PREFIX)

    def test_a_refusal_is_read_out_of_the_reply_text(self):
        self.assertTrue(noctalia.refused(outcome(runner.OK, stdout="error: no such key")))

    def test_the_prefix_is_matched_without_regard_to_case(self):
        self.assertTrue(noctalia.refused(outcome(runner.OK, stdout="Error: no such key")),
                        "a capital E in the shell's own reply was read as success")

    def test_a_reply_that_is_only_text_is_not_a_refusal(self):
        self.assertFalse(noctalia.refused(outcome(runner.OK, stdout="dark")))
        self.assertFalse(noctalia.refused(outcome(runner.OK, stdout="")))

    def test_a_command_that_never_ran_has_no_refusal_to_read(self):
        self.assertFalse(noctalia.refused(outcome(runner.FAILED, reason="not installed")),
                         "a command that never ran was reported as having refused, and the "
                         "two have different sentences on a page")
        self.assertFalse(noctalia.refused(outcome(runner.UNVERIFIED)))

    def test_reply_text_is_the_trimmed_stdout_and_nothing_else(self):
        self.assertEqual("hi", noctalia.reply_text(outcome(runner.OK, stdout="  hi  ")))
        self.assertEqual("", noctalia.reply_text(outcome(runner.FAILED, reason="no")))
        self.assertEqual("", noctalia.reply_text(outcome(runner.UNVERIFIED)))

    def test_answered_has_three_answers_and_not_two(self):
        """`None` means it never ran *or* the reply was empty; the text is the value."""
        self.assertEqual("dark", noctalia.answered(outcome(runner.OK, stdout="dark")))
        self.assertIsNone(noctalia.answered(outcome(runner.OK, stdout="   ")),
                          "an empty reply was returned as a value, so a page would draw "
                          "nothing and call it an answer")
        self.assertIsNone(noctalia.answered(outcome(runner.FAILED)))
        self.assertIsNone(noctalia.answered(outcome(runner.UNVERIFIED)))

    def test_a_key_that_is_not_in_the_shell_record_is_refused_with_the_sections_listed(self):
        value, verdict, reason = noctalia.read("nonsense.key")
        self.assertIsNone(value)
        self.assertEqual(runner.FAILED, verdict)
        self.assertIn("nonsense.key", reason)
        self.assertIn("audio", reason, "the refusal does not name a real section, so a "
                                       "person cannot tell what a key looks like")
        self.assertIn("noctalia.json", reason,
                      "the refusal does not name the record it checked against")

    def test_a_known_key_is_accepted_before_anything_is_sent(self):
        self.assertEqual([], noctalia.check_path("audio.sound_volume"))
        self.assertTrue(noctalia.check_path("nonsense.key"))
        self.assertEqual(230, len(noctalia.known_paths()))

    def test_a_table_key_is_a_prefix_of_leaves_and_not_a_leaf_itself(self):
        """230 leaves and 12 tables: a table is a container, so it is in neither list twice.

        ``known_paths()`` answers leaves only. A table path is therefore *not* in it, and
        the thing that makes it known is that at least one leaf hangs off it -- which is
        also what stops a typo in a table name from looking like a valid container.
        """
        tables = noctalia.table_paths()
        leaves = noctalia.known_paths()
        self.assertEqual(12, len(tables))
        self.assertEqual(230, len(leaves))
        for path in tables:
            with self.subTest(path=path):
                self.assertNotIn(path, leaves,
                                 f"{path} is recorded as a table and as a leaf, so a page "
                                 f"cannot tell whether to draw a control or a container")
                children = [leaf for leaf in leaves if leaf.startswith(path + ".")]
                self.assertTrue(children,
                                f"{path} is a table with no leaf under it, so nothing can "
                                f"read or write it and the entry is a claim about a container "
                                f"that does not exist")

    def test_a_leaf_is_a_path_that_can_be_read_and_a_table_is_not(self):
        """``check_path`` answers for values. A table has no single value to read, so it is
        refused here and drawn as a container by the page instead -- ``table_paths()`` is
        the list a page uses to decide which of the two it is looking at."""
        table = noctalia.table_paths()[0]
        leaf = next(path for path in noctalia.known_paths()
                    if path.startswith(table + "."))
        self.assertEqual([], noctalia.check_path(leaf))
        problems = noctalia.check_path(table)
        self.assertTrue(problems, f"{table} is a container and check_path accepted it, so a "
                                  f"read of it would answer with a whole table where a page "
                                  f"expects one value")
        self.assertIn(table, problems[0])
        self.assertEqual(table, "control_center.calendar",
                         "the first table is no longer the one this test reads its leaf "
                         "from, so the assertion above is testing a different container")

    def test_a_value_is_checked_against_the_keys_own_shape(self):
        self.assertEqual([], noctalia.check_value("theme.mode", "dark"))
        problems = noctalia.check_value("theme.mode", "purple")
        self.assertTrue(problems, "a value the shell's own schema would reject was accepted, "
                                  "so the failure arrives from a socket rather than from "
                                  "this project")
        self.assertTrue(noctalia.check_value("nonsense.key", 1))


class TestTheArgumentListIsBuiltOnce(unittest.TestCase):
    """One spelling, one invocation, and the arguments the header declares."""

    def test_the_invocation_is_the_recorded_spelling(self):
        self.assertEqual("noctalia msg <verb> [argument...]", noctalia.INVOCATION)

    def test_every_argv_starts_with_the_binary_and_the_subcommand(self):
        for result in (noctalia.lock_now(), noctalia.reload(), noctalia.volume_osd(),
                       noctalia.open_shell_settings(), noctalia.toggle_wifi()):
            with self.subTest(argv=str(result.argv)):
                self.assertEqual([runner.NOCTALIA_BIN, "msg"], list(result.argv)[:2],
                                 "a verb was sent without the subcommand the invocation "
                                 "records, so the shell would not find it")

    def test_a_config_set_value_is_rendered_the_way_toml_reads_it(self):
        self.assertEqual(["config-set", "theme.mode", '"dark"'],
                         list(noctalia.config_set("theme.mode", "dark").argv[2:]),
                         "a string reached config-set unquoted, and the shell's TOML parser "
                         "would read it as a bare word")

    def test_toml_renders_each_shape_the_way_the_parser_reads_it(self):
        self.assertEqual("true", noctalia.toml_value(True))
        self.assertEqual("false", noctalia.toml_value(False))
        self.assertEqual("3", noctalia.toml_value(3))
        self.assertEqual('"x"', noctalia.toml_value("x"))
        self.assertEqual("[1, 2]", noctalia.toml_value([1, 2]))

    def test_a_value_toml_cannot_hold_is_refused_rather_than_rendered_as_a_word(self):
        with self.assertRaises(noctalia.NoctaliaError) as caught:
            noctalia.toml_value(None)
        self.assertIn("TOML", str(caught.exception))
        with self.assertRaises(noctalia.NoctaliaError):
            noctalia.toml_value({"a": 1})

    def test_a_verb_is_given_the_arguments_the_header_declares(self):
        verbs = noctalia.verbs()
        self.assertEqual([], noctalia.check_arguments(verbs["config-set"], ["a.b", "1"]))
        problems = noctalia.check_arguments(verbs["config-set"], ["a.b"])
        self.assertEqual(1, len(problems))
        self.assertIn("config-set", problems[0])
        self.assertIn("2", problems[0], "the sentence does not say how many arguments the "
                                        "verb takes, so it cannot be acted on")
        self.assertIn("1", problems[0])

    def test_a_verb_that_takes_no_arguments_is_refused_one(self):
        entry = noctalia.verbs()["config-reload"]
        self.assertEqual([], entry["arguments"])
        problems = noctalia.check_arguments(entry, ["x"])
        self.assertTrue(problems, "a zero-argument verb was given an argument and the check "
                                  "said nothing, so the shell would be the one to refuse it")
        self.assertIn("config-reload", problems[0])

    def test_a_required_argument_missing_is_a_problem_and_an_optional_one_is_not(self):
        entry = noctalia.verbs()["panel-open"]
        self.assertEqual([], noctalia.check_arguments(entry, ["launcher"]))
        self.assertEqual([], noctalia.check_arguments(entry, ["launcher", "emo"]))
        self.assertTrue(noctalia.check_arguments(entry, []))


class TestThePagesSendOnlyRecordedVerbs(unittest.TestCase):
    """The plan is where a page says what it will do, so it is where this is checked."""

    def test_every_noctalia_action_a_page_can_send_is_one_the_module_has(self):
        context = default_context()
        sent = sorted({action for spec in pages.PAGES
                       for action in pages.build(spec.id, context).actions_used()
                       if action.startswith("noctalia.")})
        self.assertEqual(list(PAGE_ACTIONS), sent,
                         "the set of noctalia actions the pages declare has changed, and "
                         "this test's list is now stale in one direction or the other")
        for action in sent:
            name = action.split(".", 1)[1]
            with self.subTest(action=action):
                self.assertTrue(hasattr(noctalia, name),
                                f"a page sends {action} and services/noctalia.py has no such "
                                f"function, so the click would raise")

    def test_every_verb_this_module_can_send_is_recorded_as_used(self):
        """Derived from the code rather than from a list: ask each sender what it would send.

        Nothing here reaches a command line -- the shell binary is absent on this machine,
        so every call answers with the argv it built and a verdict of ``unverified``.
        """
        senders = (noctalia.lock_now, noctalia.suspend_now, noctalia.screen_off,
                   noctalia.screen_on, noctalia.toggle_wifi, noctalia.toggle_bluetooth,
                   noctalia.toggle_network, noctalia.screenshot_region,
                   noctalia.screenshot_window, noctalia.volume_osd, noctalia.caffeine,
                   noctalia.nightlight, noctalia.open_control_center, noctalia.open_launcher,
                   noctalia.open_shell_settings, noctalia.reload)
        sent = {sender().argv[2] for sender in senders}
        sent.add(noctalia.set_dnd(True).argv[2])
        sent.add(noctalia.set_theme_mode("dark").argv[2])
        sent.add(noctalia.config_set("theme.mode", "dark").argv[2])
        sent.add(noctalia.nightlight(True).argv[2])
        self.assertTrue(all(verb in VERB_NAMES for verb in sent),
                        f"a sender built a verb the record does not have: "
                        f"{sorted(sent - set(VERB_NAMES))}")
        for verb in sorted(sent):
            entry = next(item for item in VERBS if item["verb"] == verb)
            with self.subTest(verb=verb):
                self.assertTrue(entry.get("used_by"),
                                f"{verb} is sent by services/noctalia.py and its used_by is "
                                f"empty, so the record claims nobody uses it")
        self.assertIn("keybind.lua",
                      " ".join(s for v in VERBS for s in v.get("used_by") or ()),
                      "the session's own keybinds send panel-toggle and the record does not "
                      "say so, which makes a used verb look unused")

    def test_the_record_keeps_the_config_keys_apart_from_the_verbs(self):
        note = RECORD["_note"]
        self.assertIn("different question", note,
                      "the record does not say why it is a separate file from noctalia.json, "
                      "so the two look like a duplication rather than two answers")

    def test_a_verb_with_no_key_behind_it_is_the_recorded_exception(self):
        self.assertIn("Do Not Disturb", RECORD["_note"],
                      "the one case where a verb exists with no config key at all is the "
                      "reason the two records cannot be merged, and the note has to keep it")
        self.assertEqual(["notification-dnd-set", "on"],
                         list(noctalia.set_dnd(True).argv[2:]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
