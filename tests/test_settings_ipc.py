#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the shell's IPC record, and for the code that is only allowed to send what it lists.

``data/design/noctalia-ipc.json`` is a closed record of 39 commands, each with the
arguments it takes and the line of the pinned release it was read from. The schema's own
description states the rule this test enforces: the settings application, the two mode
switches, the doctor and the control-centre helper may only send a verb listed there.

That matters more here than in most records because of what the shell does with a command
it does not know. An unregistered verb does not fail: the record's own note says the shell
answers ``ok`` to some commands that did nothing, and hyprctl-style binaries exit 0 for a
command they never registered. So a typo in this codebase would not be an error a person
sees -- it would be a switch that appears to work and changes nothing, which is the worst
failure a settings application has available to it.

Three things are checked:

* every verb the code sends is in the record, found by reading the module's own string
  literals rather than by listing them again in the test, so a new call site is covered
  without anybody remembering to update a list here;
* every verb in the record carries the arguments and the evidence line it was read from,
  and the ones this project deliberately does not send are recorded as not sent rather
  than simply absent;
* the pre-send checks refuse what the shell would silently accept -- an unknown path, an
  out-of-range number, an unrecognised enum spelling -- because ``config-set`` clamps a
  number and reports success, and answers an unknown key with a warning nobody reads.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.services import noctalia, runner  # noqa: E402

RECORD = json.loads((ROOT / "data" / "design" / "noctalia-ipc.json").read_text(
    encoding="utf-8"))
VERBS: List[Dict[str, Any]] = RECORD["verbs"]
VERB_NAMES: Set[str] = {str(entry["verb"]) for entry in VERBS}
BY_NAME: Dict[str, Dict[str, Any]] = {str(entry["verb"]): entry for entry in VERBS}

MODULE_PATH = ROOT / "iarch" / "settings-app" / "iarch_settings" / "services" / "noctalia.py"
SOURCE = MODULE_PATH.read_text(encoding="utf-8")


def string_literals(text: str = SOURCE) -> Set[str]:
    """Every string literal in the module, so a verb cannot hide in a new call site."""
    tree = ast.parse(text, filename=str(MODULE_PATH))
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def verbs_sent_by_code() -> Set[str]:
    """The literals that look like a verb this module sends.

    Shaped like the record's verbs -- lowercase words joined by hyphens -- and present in
    the record, which is the assertion: a hyphenated literal that is *not* in the record is
    either a verb nobody verified or a string that happens to look like one, and the test
    below tells the two apart by checking the call sites rather than the literals alone.
    """
    return {literal for literal in string_literals()
            if re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)+", literal)}


class TestTheRecordItself(unittest.TestCase):
    """A closed record has to be complete before it can close anything."""

    def test_there_are_thirty_nine_verbs_and_no_duplicate(self):
        self.assertEqual(39, len(VERBS), "the record's verb count changed, which means a "
                                        "release was re-read and this test has not been")
        self.assertEqual(len(VERB_NAMES), len(VERBS), "a verb is listed twice")

    def test_every_verb_carries_a_description_arguments_and_an_evidence_line(self):
        for entry in VERBS:
            with self.subTest(verb=entry.get("verb")):
                self.assertTrue(str(entry.get("description") or "").strip())
                self.assertIsInstance(entry.get("arguments"), list)
                self.assertTrue(str(entry.get("evidence") or "").strip(),
                                "a verb with no evidence line was not read out of source")

    def test_the_evidence_names_a_file_and_a_line_of_the_pinned_release(self):
        pattern = re.compile(r"\.(h|c|cpp|hpp|md)(:\d+(-\d+)?)?")
        for entry in VERBS:
            with self.subTest(verb=entry["verb"]):
                self.assertTrue(pattern.search(str(entry["evidence"])),
                                f"{entry['verb']}'s evidence names no source location")

    def test_every_argument_says_whether_it_is_required(self):
        for entry in VERBS:
            for argument in entry["arguments"]:
                with self.subTest(verb=entry["verb"], argument=argument.get("name")):
                    self.assertTrue(str(argument.get("name") or "").strip())
                    self.assertIn("required", argument,
                                  "an argument whose requiredness is unstated is one a "
                                  "caller has to guess at")
                    self.assertIsInstance(argument["required"], bool)

    def test_a_verb_this_project_sends_says_what_sends_it(self):
        """`used_by` is the record's answer to "who reaches for this", and an empty list is
        not an answer. Only the verbs the code actually names are held to it: the record
        describes the shell's whole surface, and a verb nobody sends has no sender to name.
        """
        sent = verbs_sent_by_code() & VERB_NAMES
        self.assertGreater(len(sent), 20, "the scan found almost no verb, so it is not "
                                          "scanning what it thinks it is")
        for name in sorted(sent):
            with self.subTest(verb=name):
                self.assertTrue(BY_NAME[name].get("used_by"),
                                f"{name} is sent by this project and the record does not say "
                                f"which page or tool sends it")

    def test_the_verbs_deliberately_not_sent_are_recorded_as_not_sent(self):
        """A refused verb lives in the record's ``not_used`` block, not in ``verbs``.

        That split is the point: ``verbs`` is what may be sent, so a verb this project
        refuses has to be somewhere a reader can find the reason without being somewhere a
        caller can reach for it.
        """
        for name in noctalia.NOT_USED:
            with self.subTest(verb=name):
                self.assertNotIn(name, VERB_NAMES,
                                 f"{name} is refused by the code and also listed as "
                                 f"sendable, which is how a refusal gets undone by accident")
        recorded = {str(entry.get("verb") or "") for entry in RECORD["not_used"]}
        for name in noctalia.NOT_USED:
            with self.subTest(verb=name):
                self.assertIn(name, recorded,
                              f"{name} is refused by the code and the record's not_used "
                              f"block does not carry it, so the refusal has no written "
                              f"reason behind it")
        for entry in RECORD["not_used"]:
            with self.subTest(entry=entry.get("verb")):
                self.assertTrue(str(entry.get("why") or "").strip(),
                                "a refusal with no reason is a policy nobody can read")

    def test_the_record_says_what_is_not_a_command_at_all(self):
        self.assertTrue(RECORD.get("not_commands"),
                        "the record does not distinguish a verb from a string that looks "
                        "like one, so a reader cannot tell why a hyphenated word is absent")


class TestTheCodeSendsOnlyWhatTheRecordLists(unittest.TestCase):
    """The schema's rule: a verb in the code that is not in the record fails the build."""

    def test_every_hyphenated_literal_that_is_a_verb_is_in_the_record(self):
        unknown = sorted(name for name in verbs_sent_by_code()
                         if name not in VERB_NAMES and not _is_explained(name))
        # The explanation list has to stay honest: an entry for a literal the module no
        # longer carries is a rule that has stopped being checked.
        stale = sorted(name for name in NOT_A_VERB if name not in string_literals())
        self.assertEqual([], stale, f"NOT_A_VERB explains literals the module no longer has: "
                                    f"{stale}")
        self.assertEqual([], unknown,
                         "noctalia.py carries a hyphenated literal that is not a verb in "
                         "data/design/noctalia-ipc.json and is not explained:\n"
                         + "\n".join(unknown))

    def test_the_service_exposes_only_recorded_verbs(self):
        for name in sorted(noctalia.verbs()):
            with self.subTest(verb=name):
                self.assertIn(name, VERB_NAMES)

    def test_every_page_verb_is_a_zero_argument_call_to_a_recorded_verb(self):
        """A button's action takes nothing, so each verb is spelled out as its own function."""
        self.assertTrue(noctalia.PAGE_VERBS)
        for name in noctalia.PAGE_VERBS:
            function = getattr(noctalia, name, None)
            with self.subTest(function=name):
                self.assertTrue(callable(function), f"noctalia.{name} does not exist")
                import inspect

                signature = inspect.signature(function)
                required = [parameter for parameter in signature.parameters.values()
                            if parameter.default is inspect.Parameter.empty
                            and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                                         inspect.Parameter.VAR_KEYWORD)]
                self.assertEqual([], required,
                                   f"noctalia.{name} needs an argument, so a button row "
                                   f"cannot call it: a button's action is the whole request")

    def test_the_zero_argument_verbs_really_are_zero_argument_in_the_record(self):
        for name in noctalia.PAGE_VERBS:
            verb = _verb_for_function(name)
            if verb is None:
                continue
            with self.subTest(function=name, verb=verb):
                required = [argument for argument in BY_NAME[verb]["arguments"]
                            if argument.get("required")]
                self.assertEqual([], required,
                                   f"noctalia.{name} sends {verb} with nothing, but the "
                                   f"record says {verb} requires an argument")

    def test_the_session_actions_this_project_sends_are_the_safe_three(self):
        """The record lists seven; a panel that can reboot is one mis-click from lost work."""
        self.assertEqual(("lock", "suspend", "lock-and-suspend"), noctalia.SESSION_ACTIONS)
        self.assertIn("session", VERB_NAMES)
        refused = " ".join(str(entry.get("verb") or "") for entry in RECORD["not_used"])
        for action in ("logout", "reboot", "shutdown"):
            with self.subTest(action=action):
                self.assertIn(action, refused,
                              f"the code refuses session {action} and the record does not "
                              f"say so, which makes the refusal look like an omission")

    def test_sending_a_refused_session_action_is_refused_in_send_not_only_in_the_helper(self):
        """No caller can reach the four actions by going round ``session()``."""
        for action in ("logout", "reboot", "reboot-uefi", "shutdown"):
            with self.subTest(action=action):
                outcome = noctalia.send("session", [action])
                self.assertNotEqual(runner.OK, outcome.verdict)
                self.assertIn(action, outcome.reason)

    def test_config_verbs_are_the_three_the_record_describes(self):
        for verb in ("config-get", "config-set", "config-reload"):
            with self.subTest(verb=verb):
                self.assertIn(verb, VERB_NAMES)
        self.assertEqual(1, len(BY_NAME["config-get"]["arguments"]),
                         "config-get takes a path and nothing else")
        self.assertEqual(2, len(BY_NAME["config-set"]["arguments"]),
                         "config-set takes a path and a TOML value, and the second one is "
                         "TOML rather than a bare string, which is the detail that makes an "
                         "integer and a string different to the shell")


#: Hyphenated literals in the module that are not verbs, each with what it actually is.
#: Written down rather than pattern-matched, because a rule that explains any hyphenated
#: string explains the typo this test exists to catch.
NOT_A_VERB = {
    "control-center": "a panel id, from the record's own examples",
    "lock-and-suspend": "an argument of the session verb, not a verb",
    "utf-8": "a codec name",
    "greeter-sync": "in NOT_USED: recorded, and refused rather than sent",
    "effects-profile-set": "in NOT_USED: recorded, and refused rather than sent",
}


def _is_explained(literal: str) -> bool:
    """Whether a hyphenated literal that is not a verb is nonetheless accounted for."""
    if literal in NOT_A_VERB:
        return True
    if literal in noctalia.NOT_USED or literal in noctalia.SESSION_ACTIONS:
        return True
    recorded_not_commands = " ".join(str(entry.get("spelling") or "")
                                     for entry in RECORD.get("not_commands") or [])
    return literal in recorded_not_commands


def _verb_for_function(name: str) -> Optional[str]:
    """The verb a zero-argument page function sends, read out of the module's source."""
    pattern = re.compile(rf"def {re.escape(name)}\([^)]*\).*?(?:\n\s+.{{0,200}})*?", re.S)
    match = re.search(rf"def {re.escape(name)}\(", SOURCE)
    if not match:
        return None
    tail = SOURCE[match.end():match.end() + 400]
    for verb in sorted(VERB_NAMES, key=len, reverse=True):
        if f'"{verb}"' in tail or f"'{verb}'" in tail:
            return verb
    return None


class TestThePreSendChecks(unittest.TestCase):
    """What the shell would silently accept, refused here instead."""

    def test_an_unknown_config_path_is_refused_before_it_is_sent(self):
        problems = noctalia.check_path("bar.default.nonsense")
        self.assertTrue(problems)
        self.assertIn("bar.default.nonsense", " ".join(problems))

    def test_an_unknown_path_names_the_record_and_offers_a_sibling(self):
        problems = noctalia.check_path("dock.nonsense")
        joined = " ".join(problems)
        self.assertIn("noctalia.json", joined,
                      "a refusal has to say which record was consulted, or it reads as a "
                      "guess")
        self.assertTrue(any(word in joined for word in ("position", "icon_size", "dock")),
                        f"a refusal that lists no sibling is not much help: {joined}")

    def test_a_table_is_not_a_key_so_it_has_no_value_to_write(self):
        for path in noctalia.table_paths():
            with self.subTest(table=path):
                self.assertTrue(noctalia.check_path(path),
                                f"{path} is a table, and config_set would have nothing to "
                                f"write to it")

    def test_a_recorded_leaf_path_is_accepted(self):
        for path in ("bar.default.thickness", "dock.icon_size", "theme.mode",
                     "audio.sound_volume", "idle.pre_action_fade_seconds"):
            with self.subTest(path=path):
                self.assertEqual([], noctalia.check_path(path),
                                 f"{path} is in the record and was refused")

    def test_a_number_outside_the_recorded_range_is_refused_before_it_is_sent(self):
        """``config-set`` clamps and reports success, so the check has to be ours."""
        problems = noctalia.check_value("bar.default.thickness", 9999)
        self.assertTrue(problems)
        joined = " ".join(problems)
        self.assertIn("9999", joined)
        self.assertTrue(re.search(r"\b10\b", joined) and re.search(r"\b300\b", joined),
                        f"the refusal has to carry the range it was checked against: "
                        f"{joined}")

    def test_a_number_inside_the_recorded_range_is_accepted(self):
        self.assertEqual([], noctalia.check_value("bar.default.thickness", 40))

    def test_an_unrecognised_enum_spelling_is_refused_rather_than_sent(self):
        problems = noctalia.check_value("dock.position", "middle")
        self.assertTrue(problems)
        joined = " ".join(problems)
        for spelling in ("top", "bottom", "left", "right"):
            self.assertIn(spelling, joined,
                          "an enum refusal has to list the spellings the shell does take, "
                          "because the shell answers an unknown one with a warning nobody "
                          "reads")

    def test_a_recorded_enum_spelling_is_accepted(self):
        for spelling in ("top", "bottom", "left", "right"):
            with self.subTest(spelling=spelling):
                self.assertEqual([], noctalia.check_value("dock.position", spelling))

    def test_a_wrong_type_is_refused(self):
        self.assertTrue(noctalia.check_value("bar.default.thickness", "thick"))
        self.assertTrue(noctalia.check_value("dock.magnification", None))

    def test_a_key_with_no_recorded_range_accepts_a_number_and_refuses_a_word(self):
        """The record declares some numbers without bounds, and the page must not invent any."""
        specs = noctalia.key_specs()
        unbounded = [path for path, spec in specs.items()
                     if str(spec.get("type") or "") in ("integer", "float")
                     and not spec.get("range")]
        self.assertTrue(unbounded, "no unbounded number key exists, so this test is not "
                                   "testing the case it was written for")
        for path in unbounded[:5]:
            with self.subTest(path=path):
                self.assertEqual([], noctalia.check_value(path, 4))
                self.assertTrue(noctalia.check_value(path, "four"))


class TestTheSendingIsCheckedNotTrusted(unittest.TestCase):
    """An exit code is not a verdict, so the reply is read."""

    def test_the_binary_name_lives_in_one_place(self):
        self.assertTrue(runner.NOCTALIA_BIN)
        self.assertNotIn("noctalia\"", SOURCE.split("runner.NOCTALIA_BIN")[0][-200:]
                         if "runner.NOCTALIA_BIN" in SOURCE else "",
                         "a binary name hardcoded in the service is a second place to "
                         "change it")

    def test_a_reply_is_classified_out_of_its_text_and_not_its_exit_code(self):
        """An unreachable socket and a handler that said no are both non-zero exits."""
        answered = runner.Outcome(["noctalia"], runner.OK, stdout='{"mode": "dark"}')
        said_no = runner.Outcome(["noctalia"], runner.FAILED, stdout="error: unknown command")
        unreachable = runner.Outcome(["noctalia"], runner.FAILED,
                                     reason="noctalia is not installed")
        self.assertFalse(noctalia.refused(answered))
        self.assertTrue(noctalia.refused(said_no), "a reply that begins with the shell's own "
                                                   "error prefix was not read as a refusal")
        self.assertFalse(noctalia.refused(unreachable),
                         "a binary that never ran is not the shell refusing: the two need "
                         "different sentences, and only one of them is about a verb")

    def test_an_answer_is_none_when_the_shell_never_answered(self):
        never_ran = runner.Outcome(["noctalia"], runner.UNVERIFIED, reason="not installed")
        self.assertIsNone(noctalia.answered(never_ran))
        empty = runner.Outcome(["noctalia"], runner.OK, stdout="")
        self.assertIsNone(noctalia.answered(empty),
                          "an empty reply is not an answer, and a page that drew it as one "
                          "would show a blank where a value belongs")

    def test_an_unregistered_verb_is_never_sent_at_all(self):
        """The shell exits 0 for a command it never registered, so the check is ours."""
        outcome = noctalia.send("not-a-verb", [])
        self.assertEqual(runner.FAILED, outcome.verdict)
        self.assertIn("not-a-verb", outcome.reason)
        self.assertIn("noctalia-ipc.json", outcome.reason,
                      "the refusal has to name the record that was consulted")

    def test_check_arguments_refuses_the_wrong_number_of_arguments(self):
        entry = BY_NAME["config-get"]
        self.assertTrue(noctalia.check_arguments(entry, []), "config-get needs a path")
        self.assertTrue(noctalia.check_arguments(entry, ["a", "b", "c"]),
                        "config-get takes one path and nothing else")
        self.assertEqual([], noctalia.check_arguments(entry, ["bar.default.thickness"]))

    def test_a_zero_argument_verb_refuses_an_argument_it_was_not_recorded_with(self):
        entry = BY_NAME["nightlight-toggle"]
        self.assertEqual([], entry["arguments"])
        self.assertTrue(noctalia.check_arguments(entry, ["on"]),
                        "a verb recorded as taking nothing accepted something")

    def test_sending_without_the_binary_is_a_refusal_not_an_exception(self):
        if runner.which(runner.NOCTALIA_BIN) is not None:
            self.skipTest("the shell's binary is installed here, so the absent branch "
                          "cannot be reached")
        outcome = noctalia.send("config-get", ["theme.mode"])
        self.assertNotEqual(runner.OK, outcome.verdict)
        self.assertTrue(outcome.reason, "a refusal with no reason cannot be shown to "
                                        "anybody")

    def test_a_read_that_cannot_be_made_says_so_instead_of_guessing(self):
        if runner.which(runner.NOCTALIA_BIN) is not None:
            self.skipTest("the shell's binary is installed here")
        value, verdict, reason = noctalia.read("theme.mode")
        self.assertIsNone(value, "a value that could not be read has to be None, never a "
                                 "default, because a page shows it")
        self.assertNotEqual(runner.OK, verdict)
        self.assertTrue(str(reason).strip(),
                        "the three-part answer exists so that 'could not be asked' and 'the "
                        "shell said no' are different sentences on a screen")

    def test_a_read_of_a_path_the_record_does_not_have_is_refused_before_it_is_sent(self):
        value, verdict, reason = noctalia.read("theme.nonsense")
        self.assertIsNone(value)
        self.assertEqual(runner.FAILED, verdict)
        self.assertIn("theme.nonsense", reason)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
