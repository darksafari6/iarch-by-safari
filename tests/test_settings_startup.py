#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Startup & Default apps page and the two records behind it.

Two schemas name this file, and both say the same thing in different words: the page may
name only what the record names.

``data/schemas/autostart.schema.json:6`` — "The Startup & Default apps page may write a
key listed here and marked written_by_this_project, and no other". The record carries 26
keys and splits them three ways: keys the session *reads* into a field, keys it recognises
and deliberately ignores, and keys it does not know at all. Only five are written here
(``Name``, ``Exec``, ``Type``, ``Hidden``, ``Comment``), and the split matters because a
key the session ignores is a key a switch could be built on. That is exactly what
``X-GNOME-Autostart-enabled`` is: absent from the generator's table entirely, so writing
it changes nothing while the entry keeps starting. A switch that appears to work and does
nothing is the worst failure this application has available to it.

``data/schemas/xdg-defaults.schema.json:6`` — the page may not name a property, an
operation or a mimetype the record does not. The record's own refusal explains why: there
is no ``xdg-settings`` property for a terminal emulator, so a "default terminal" dropdown
would be a control that runs a command which exits with a failure. The page names the role
and explains it instead.

The Exec line is a *second* parser with its own rules, and two of them decide whether a
program asked to start will start at all, so the writer refuses at the moment the entry is
added rather than at the next login: an unresolvable first word (the session generates no
unit and reports nothing a person would see), a leading ``~`` (expanded against the home
directory, so it is not a literal character), a backslash (the file parser accepts six
escapes and any other one makes the session drop the whole file), a double quote, and a
field code (removed before the unit is written, so the command would run without it).

One refusal was narrower than the record it cites, and this file is what caught it: the
shell-wrapper check matched the exact word ``-c``, so ``bash -lc '…'`` — a login shell
running a script string, the common spelling — passed, and so did ``env bash -c '…'``,
which is the same wrapper with a program in front of it. Both are refused now.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings import pages  # noqa: E402
from iarch_settings.pages.plan import default_context  # noqa: E402
from iarch_settings.services import autostart, defaults, runner  # noqa: E402

AUTOSTART = json.loads((ROOT / "data" / "design" / "autostart.json").read_text(
    encoding="utf-8"))
XDG = json.loads((ROOT / "data" / "design" / "xdg-defaults.json").read_text(encoding="utf-8"))
KEYS: List[Dict[str, Any]] = AUTOSTART["keys"]
RECORDED_WRITTEN = [key["key"] for key in KEYS if key.get("written_by_this_project")]
RECORDED_READ = [key["key"] for key in KEYS if key.get("read")]
RECORDED_IGNORED = [key["key"] for key in KEYS if not key.get("read")]
ROLES: List[Dict[str, Any]] = XDG["roles"]
PROPERTIES = [entry["property"] for entry in XDG["settings_tool"]["properties"]]
AUTOSTART_BY_ID = {entry["id"]: entry for entry in AUTOSTART["rejected"]}

PLAN = pages.build("startup", default_context())


def plan_text() -> str:
    """Every string the Startup page draws, so a claim can be looked for in it."""
    parts = [PLAN.title, PLAN.description or ""]
    for row in PLAN.walk():
        parts += [row.title, row.subtitle or "", row.confirm or "", row.confirm_body or ""]
        parts += [str(choice) for choice in row.choices or ()]
    for banner in PLAN.banners:
        parts.append(banner.text)
    return " ".join(part for part in parts if part)


class TestTheKeyTableSplitsReadFromIgnored(unittest.TestCase):
    """A key the session ignores is a key no switch may be built on."""

    def test_the_record_carries_twenty_six_keys_and_writes_five(self):
        self.assertEqual(26, len(KEYS))
        self.assertEqual(5, len(RECORDED_WRITTEN))
        self.assertEqual({"Name", "Exec", "Type", "Hidden", "Comment"},
                         set(RECORDED_WRITTEN))

    def test_the_writer_writes_exactly_the_keys_the_record_marks(self):
        self.assertEqual(sorted(RECORDED_WRITTEN), sorted(autostart.writable_keys()),
                         "the keys the writer will emit and the keys the record marks "
                         "written_by_this_project are two copies of one decision")

    def test_the_render_order_is_the_writable_keys_in_one_order(self):
        self.assertEqual(("Comment", "Name", "Type", "Exec", "Hidden"),
                         autostart.RENDER_ORDER)
        self.assertEqual(sorted(RECORDED_WRITTEN), sorted(autostart.RENDER_ORDER),
                         "a rendered key nobody may write, or a writable key nobody "
                         "renders, is a file that disagrees with the record")

    def test_a_key_the_session_ignores_is_recorded_as_ignored(self):
        self.assertTrue(RECORDED_IGNORED, "no key is recorded as ignored, so the split this "
                                          "record exists to make is not being made")
        for key in ("Icon", "Terminal", "NoDisplay", "StartupNotify"):
            with self.subTest(key=key):
                self.assertIn(key, RECORDED_IGNORED)
                self.assertNotIn(key, RECORDED_WRITTEN)

    def test_the_key_written_and_not_read_is_the_ownership_marker(self):
        """``Comment`` is written and ignored, which is why a marker can be a comment."""
        self.assertIn("Comment", RECORDED_WRITTEN)
        self.assertNotIn("Comment", RECORDED_READ)
        marker = AUTOSTART["ownership"]["marker"]
        self.assertTrue(marker.startswith("#"), "the marker is not a comment, so the session "
                                                "would try to parse it")
        self.assertEqual(marker, autostart.record()["ownership"]["marker"])

    def test_every_key_carries_a_cite_from_the_pinned_release(self):
        for key in KEYS:
            with self.subTest(key=key["key"]):
                self.assertTrue(str(key["evidence"]).startswith("src/"),
                                f"{key['key']}'s evidence does not name a path in the pinned "
                                f"release, so nobody can check it")

    def test_the_gnome_autostart_enabled_key_is_not_in_the_table_at_all(self):
        """The refusal is about a key the generator has never heard of."""
        self.assertNotIn("X-GNOME-Autostart-enabled", [key["key"] for key in KEYS])
        refusal = autostart.refusals()["gnome-autostart-enabled"]
        self.assertIn("Hidden=true", refusal["message"],
                      "the refusal has to say what to write instead, or a person is left "
                      "with a switch that does not exist")
        self.assertIn("not read", refusal["message"])
        self.assertIn("key table", refusal["why"],
                      "the reasoning has to say the key is in neither half of the generator's "
                      "table, which is a stronger claim than 'it is ignored'")

    def test_a_refusal_message_carries_no_citation_and_a_why_carries_one(self):
        """The schema says so: a citation is not an explanation."""
        for refusal_id, refusal in autostart.refusals().items():
            with self.subTest(refusal=refusal_id):
                self.assertFalse(any(char.isdigit() for char in refusal["message"]),
                                 f"the message for {refusal_id} carries a line number, which "
                                 f"is what a person reads on screen")
                self.assertTrue(any(char.isdigit() for char in refusal["why"]),
                                f"the reasoning for {refusal_id} carries no cite")
                self.assertEqual(refusal["message"],
                                 AUTOSTART_BY_ID[refusal_id]["message"],
                                 "the sentence came out of the code and not out of the "
                                 "record, so the record no longer says what a person reads")

    def test_the_page_shows_both_refusals(self):
        text = plan_text().lower()
        for refusal_id, refusal in autostart.refusals().items():
            with self.subTest(refusal=refusal_id):
                self.assertIn(refusal["spelling"].split(":")[0].strip().lower()[:18], text,
                              f"the Startup page does not show the {refusal_id} refusal, so "
                              f"a person who tries it gets a failure with no explanation")


class TestTheExecLineIsASecondParser(unittest.TestCase):
    """Five refusals, each one a rule the session imposes that the page cannot undo."""

    def test_a_program_that_cannot_be_resolved_is_refused(self):
        problems = autostart.check_command(["/nonexistent/program"])
        self.assertTrue(problems)
        self.assertIn("no such program", problems[0])
        self.assertTrue("never start" in problems[0] or "no unit" in problems[0],
                        f"the refusal has to say what happens instead: {problems[0]}")

    def test_a_leading_tilde_is_refused_because_it_is_not_a_literal(self):
        problems = autostart.check_command(["~/bin/thing"])
        self.assertTrue(problems)
        self.assertIn("home directory", problems[0])

    def test_a_backslash_is_refused_because_the_file_parser_accepts_only_six_escapes(self):
        problems = autostart.check_command(["/usr/bin/true", "a\\b"])
        self.assertTrue(problems)
        self.assertIn("backslash", problems[0])
        self.assertEqual(6, len(autostart.ESCAPES),
                         "the six escapes the file parser accepts are recorded, and the "
                         "writer quotes with double quotes and nothing else")

    def test_a_double_quote_is_refused_because_two_parsers_read_one_string(self):
        self.assertTrue(autostart.check_command(["/usr/bin/true", 'say "hi"']))

    def test_a_field_code_is_refused_because_the_session_removes_it(self):
        for code in autostart.FIELD_CODES:
            with self.subTest(code=code):
                problems = autostart.check_command(["/usr/bin/true", code])
                self.assertTrue(problems, f"{code} is removed before the unit is written, so "
                                          f"a command containing it would run without it")
        self.assertEqual(13, len(autostart.FIELD_CODES))

    def test_a_literal_percent_survives_because_it_is_not_a_field_code(self):
        self.assertEqual([], autostart.check_command(["/usr/bin/true", "100%"]))

    def test_an_argument_with_a_space_is_quoted_and_never_escaped(self):
        quoted = autostart.quote_exec(["/usr/bin/true", "a b"])
        self.assertEqual('/usr/bin/true "a b"', quoted)
        self.assertNotIn("\\", quoted, "the writer emits a backslash escape, and any escape "
                                       "outside the six makes the session drop the file")

    def test_a_control_character_or_a_line_break_is_refused(self):
        self.assertTrue(autostart.check_command(["/usr/bin/true", "a\nb"]))
        self.assertTrue(autostart.check_command(["/usr/bin/true", "a\x00b"]))
        self.assertTrue(autostart.check_command(["/usr/bin/true", "a\x1bb"]))

    def test_an_empty_command_is_refused(self):
        self.assertTrue(autostart.check_command([]))
        self.assertTrue(autostart.check_command(["   "]))


class TestTheShellWrapperRefusalCoversTheCommonSpellings(unittest.TestCase):
    """The gap this file caught: an exact ``-c`` match missed every clustered spelling."""

    SHELL_WRAPPERS: Sequence[Sequence[str]] = (
        ("/bin/sh", "-c", "true"),
        ("bash", "-lc", "hyprctl dispatch exec foo"),
        ("zsh", "-ic", "true"),
        ("fish", "--command", "true"),
        ("bash", "--login", "-c", "true"),
        ("/usr/bin/env", "bash", "-c", "true"),
        ("/usr/bin/env", "-S", "zsh", "-lc", "true"),
        ("konsole", "-e", "bash", "-c", "true"),
    )

    def test_every_shell_wrapper_is_refused_with_the_recorded_sentence(self):
        recorded = AUTOSTART_BY_ID["shell-wrapper"]["message"]
        for argv in self.SHELL_WRAPPERS:
            with self.subTest(argv=" ".join(argv)):
                problems = autostart.check_command(list(argv))
                self.assertTrue(problems, "a shell wrapper was accepted, which turns the "
                                          "check on the program into a check on the shell "
                                          "and puts a string from a user file one step "
                                          "closer to a shell")
                self.assertIn(recorded, problems,
                              "the sentence came out of the code rather than the record")

    def test_a_clustered_short_flag_is_a_script_request_and_a_long_option_is_not(self):
        self.assertTrue(autostart._runs_a_script(["-lc"]))
        self.assertTrue(autostart._runs_a_script(["-c"]))
        self.assertTrue(autostart._runs_a_script(["--command"]))
        self.assertFalse(autostart._runs_a_script(["--config"]),
                         "a long option is not a flag cluster, and refusing --config would "
                         "refuse a program's own ordinary argument")
        self.assertFalse(autostart._runs_a_script(["-c=x"]))
        self.assertFalse(autostart._runs_a_script(["-l"]))

    def test_a_shell_run_on_a_file_is_not_a_wrapper(self):
        """``bash -l script.sh`` runs a file, so the check on the program still means something."""
        self.assertEqual([], autostart.check_command(["bash", "-l", "script.sh"]))

    def test_a_program_that_is_not_a_shell_may_take_a_c_flag(self):
        self.assertEqual([], autostart.check_command(["/usr/bin/true", "-c"]))
        self.assertEqual([], autostart.check_command(["/usr/bin/git", "log", "--format=%c"]))

    def test_the_text_form_is_checked_the_way_the_session_splits_it(self):
        problems = autostart.check_command_text("/bin/sh -c 'true'")
        self.assertTrue(problems)
        self.assertTrue(autostart.check_command_text("/usr/bin/true a\\b"))
        self.assertEqual([], autostart.check_command_text('/usr/bin/true "a b"'))


class TestOwnershipDecidesWhatMayBeTouched(unittest.TestCase):
    """Every other file in the directory is listed and none is changed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_the_prefix_and_the_marker_come_out_of_the_record(self):
        self.assertEqual("iarch-", AUTOSTART["ownership"]["prefix"])
        self.assertEqual(AUTOSTART["ownership"]["prefix"], autostart.ownership_prefix())

    def test_a_new_entry_is_written_with_the_prefix_and_the_marker(self):
        entry = autostart.add("Backup check", ["/usr/bin/true"], config_home=self.tmp)
        self.assertTrue(entry.path.name.startswith("iarch-"),
                        f"{entry.path.name} is not prefixed, so this project could not tell "
                        f"its own file from another program's")
        text = entry.path.read_text(encoding="utf-8")
        self.assertEqual(AUTOSTART["ownership"]["marker"], text.splitlines()[0])
        self.assertIn("[Desktop Entry]", text)
        self.assertEqual("Application", entry.values["Type"])

    def test_an_entry_is_switched_off_with_hidden_and_not_by_deleting_it(self):
        entry = autostart.add("Backup check", ["/usr/bin/true"], config_home=self.tmp)
        autostart.set_enabled(entry, False, config_home=self.tmp)
        text = entry.path.read_text(encoding="utf-8")
        self.assertIn("Hidden=true", text,
                      "an entry is switched off with Hidden=true, which is the key this "
                      "session reads")
        self.assertNotIn("X-GNOME-Autostart-enabled", text)
        self.assertTrue(entry.path.is_file(), "switching an entry off removed the file, so "
                                              "the person's own comment and ordering went "
                                              "with it")

    def isolated_env(self) -> Dict[str, str]:
        """An environment whose system autostart directories are empty and known.

        ``entries()`` reads the user's directory and then every system one, which is
        ``$XDG_CONFIG_DIRS`` or ``/etc/xdg``. A GitHub runner has files in
        ``/etc/xdg/autostart`` and this sandbox has no such directory at all, so a test that
        counts entries without pinning that variable is counting the machine it happens to
        run on: it saw one entry here and three there, and the difference was the runner's
        own package set rather than anything this project did.
        """
        empty = self.tmp / "no-system-entries"
        empty.mkdir(exist_ok=True)
        return {"XDG_CONFIG_DIRS": str(empty), "HOME": str(self.tmp)}

    def test_a_file_this_project_does_not_own_is_listed_and_never_changed(self):
        foreign = self.tmp / "autostart" / "other.desktop"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text("[Desktop Entry]\nName=Other\nExec=/bin/true\n",
                           encoding="utf-8")
        entries = autostart.entries(config_home=self.tmp, env=self.isolated_env())
        self.assertEqual(1, len(entries),
                         f"the user's directory holds one file this project does not own and "
                         f"{len(entries)} entries were listed, so the machine's own system "
                         f"entries leaked into a test about the user's directory")
        self.assertFalse(entries[0].owned)
        self.assertFalse(entries[0].ours)
        self.assertFalse(entries[0].system, "a file in the user's own directory was listed "
                                            "as a system entry, which is the flag that "
                                            "decides whether it may be shadowed")
        before = foreign.read_text(encoding="utf-8")
        with self.assertRaises(autostart.AutostartError) as caught:
            autostart.set_enabled(entries[0], False, config_home=self.tmp)
        self.assertIn("not written by this application", str(caught.exception))
        self.assertEqual(before, foreign.read_text(encoding="utf-8"),
                         "a refusal that changed the file first is not a refusal")

    def test_a_system_directory_is_read_and_marked_as_the_kind_that_may_not_be_written(self):
        """The other half of the isolation above: system entries are read, and say where they are.

        Pinning ``XDG_CONFIG_DIRS`` to an empty directory keeps a test about the user's
        directory honest, and it would hide this behaviour entirely if nothing else covered
        it -- so here it is, with a system directory that exists on purpose.
        """
        system_root = self.tmp / "etc-xdg"
        (system_root / "autostart").mkdir(parents=True)
        vendor = system_root / "autostart" / "vendor.desktop"
        vendor.write_text("[Desktop Entry]\nName=Vendor\nExec=/bin/true\n", encoding="utf-8")
        env = {"XDG_CONFIG_DIRS": str(system_root), "HOME": str(self.tmp)}

        found = autostart.entries(config_home=self.tmp, env=env)
        self.assertEqual([vendor], [entry.path for entry in found],
                         "a system autostart directory on XDG_CONFIG_DIRS was not read, so "
                         "the page would list only what the user added and hide the entries "
                         "the session actually runs")
        self.assertTrue(found[0].system)
        self.assertFalse(found[0].ours)

    def test_a_user_entry_of_the_same_name_masks_the_system_one(self):
        """The generator stops at the first name it sees, and the list has to say so."""
        system_root = self.tmp / "etc-xdg"
        (system_root / "autostart").mkdir(parents=True)
        (system_root / "autostart" / "same.desktop").write_text(
            "[Desktop Entry]\nName=System\nExec=/bin/true\n", encoding="utf-8")
        user_dir = self.tmp / "autostart"
        user_dir.mkdir(parents=True)
        (user_dir / "same.desktop").write_text(
            "[Desktop Entry]\nName=User\nExec=/bin/false\n", encoding="utf-8")
        env = {"XDG_CONFIG_DIRS": str(system_root), "HOME": str(self.tmp)}

        found = autostart.entries(config_home=self.tmp, env=env)
        self.assertEqual(1, len(found), "one name was listed twice, and the session would "
                                        "only ever run the first file it found")
        self.assertEqual("User", found[0].values["Name"], "the system file won a name it "
                                                          "should have lost")
        self.assertFalse(found[0].system)
        self.assertEqual(system_root / "autostart" / "same.desktop", found[0].masked_by,
                         "the entry does not name the file it beat, so a person cannot tell "
                         "why a system entry disappeared from the list")

    def test_a_system_entry_is_shadowed_rather_than_written(self):
        """The record allows one shadow and refuses the other, and says why in both cases."""
        shadowing = AUTOSTART["ownership"]["shadowing"]
        self.assertIn("system", shadowing["allowed_for"])
        self.assertIn("Hidden=true", shadowing["mechanism"])
        self.assertIn("does not own", shadowing["refused_for"])
        self.assertTrue(str(shadowing["evidence"]).startswith("src/"))

    def test_a_duplicate_key_is_read_the_way_the_session_reads_it(self):
        parsed = autostart.parse("[Desktop Entry]\nName=A\nName=B\n")
        self.assertEqual("A", parsed["values"]["Name"], "the session reads the first one")
        self.assertTrue(parsed["notes"], "a duplicated key is worth telling the person "
                                         "about, because the second line looks like it won")

    def test_localized_keys_are_one_parser_with_two_asking_modes(self):
        text = "[Desktop Entry]\nName=Foo\nName[de]=Fuu\nExec=/bin/true\n"
        dropped = autostart.parse(text, keep_localized=False)
        kept = autostart.parse(text, keep_localized=True)
        self.assertEqual({}, dropped["localized"])
        self.assertTrue(dropped["notes"], "a translation the session will not read is worth "
                                          "a note, so the page can say the row is not "
                                          "translated rather than look broken")
        self.assertEqual({"Name": {"de": "Fuu"}}, kept["localized"])
        self.assertEqual([], kept["notes"])
        self.assertEqual(dropped["values"], kept["values"],
                         "the two modes disagree about what the session reads, and there is "
                         "only one session")


class TestTheActivationProbeIsReadOnly(unittest.TestCase):
    """Whether the mechanism ran, and whether this entry was among the units it made."""

    def test_the_probe_is_an_argument_list_and_never_a_string_for_a_shell(self):
        probe = autostart.activation_probe()
        self.assertEqual(AUTOSTART["activation"]["probe"], list(probe))
        self.assertTrue(all(isinstance(word, str) for word in probe))
        self.assertNotIn(";", " ".join(probe))
        self.assertNotIn("|", " ".join(probe))

    def test_the_probe_is_read_only(self):
        recorded = AUTOSTART["activation"]["probe"]
        self.assertEqual("list-units", recorded[2], "a probe that changed state would be a "
                                                    "second mechanism for starting things")
        self.assertTrue(any(word.startswith("app-") for word in recorded),
                        "the probe does not name the units the generator produces, so it "
                        "lists every unit in the session")

    def test_the_unit_name_is_escaped_the_way_the_generator_escapes_it(self):
        self.assertEqual("app-Backup\\x20check@autostart.service",
                         autostart.unit_name("Backup check.desktop"))
        self.assertIn("autostart.service", AUTOSTART["activation"]["unit_name"])

    def test_a_missing_user_manager_is_not_the_same_answer_as_not_listed(self):
        """`systemctl` missing, no user manager, and not listed are three sentences."""
        self.assertIn("Failed to connect to bus", autostart.NO_USER_MANAGER)
        self.assertTrue(autostart.activation_probe())


class TestTheDefaultAppsPageNamesOnlyRecordedThings(unittest.TestCase):
    """``xdg-defaults.schema.json:6``: no property, operation or mimetype off the record."""

    def test_the_page_offers_the_four_roles_the_record_offers(self):
        self.assertEqual(("browser", "file_manager", "editor", "mail"),
                         defaults.role_ids())
        self.assertEqual([role["role"] for role in ROLES], list(defaults.role_ids()))

    def test_the_settings_tool_has_two_properties_and_the_code_names_no_third(self):
        self.assertEqual(["default-web-browser", "default-url-scheme-handler"], PROPERTIES)
        for role_id in defaults.role_ids():
            query = defaults.query_argv(role_id, ROOT)
            with self.subTest(role=role_id):
                self.assertTrue(query, "no query argv was built")
                self.assertTrue(all(isinstance(word, str) for word in query))

    def test_a_role_is_set_in_one_call_so_it_cannot_end_up_half_set(self):
        """The schema says the mimetypes are given to one `xdg-mime default`."""
        for role in ROLES:
            argv = defaults.default_argv(role["role"], "app.desktop", ROOT)
            with self.subTest(role=role["role"]):
                self.assertEqual(["xdg-mime", "default", "app.desktop"], argv[:3])
                self.assertEqual(role["mimetypes"], argv[3:],
                                 "the mimetypes are not all in one call, so a role can end "
                                 "up half set and the page would report success")

    def test_every_role_uses_xdg_mime_and_never_xdg_settings(self):
        for role in ROLES:
            with self.subTest(role=role["role"]):
                self.assertTrue(role["mechanism"].startswith("xdg-mime default "))
                self.assertTrue(role["read"].startswith("xdg-mime query default "))
                self.assertNotIn("xdg-settings", role["mechanism"],
                                 "the settings_tool refusal explains why the generic path "
                                 "exits with a failure")

    def test_a_role_with_no_association_behind_it_is_explained_and_not_offered(self):
        unsettable = [entry["role"] for entry in defaults.unsettable()]
        self.assertIn("terminal", unsettable)
        self.assertNotIn("terminal", defaults.role_ids(),
                         "a terminal role is offered, and there is no property or mimetype "
                         "behind it, so the dropdown would run a command that exits with a "
                         "failure")
        entry = next(item for item in defaults.unsettable() if item["role"] == "terminal")
        self.assertTrue(entry["label"], "an unsettable role has no label, so the page cannot "
                                        "name it in order to explain it")
        self.assertIn("keybind", entry["why"],
                      "the explanation has to say where the decision is actually made")

    def test_the_page_names_the_unsettable_roles_rather_than_omitting_them(self):
        text = plan_text().lower()
        self.assertIn("terminal", text,
                      "the Startup page does not mention the terminal role at all, so a "
                      "person looking for it finds no control and no explanation")

    def test_a_missing_tool_is_unverified_rather_than_a_failure(self):
        """The verdicts are the runner's own, and absence is answered for on both kinds of machine.

        ``xdg-utils`` is in neither installer's package list, so on a machine nobody has set
        up the read cannot run at all and the answer has to be ``unverified``. A CI runner is
        the other kind of machine: it has ``xdg-mime``, the read runs, and the answer is
        ``ok``. Asserting one verdict without saying which machine it needs is how this test
        came to pass in a sandbox with no ``xdg-utils`` and fail on a runner with it, so both
        cases are now stated, and the vocabulary is the runner's constants rather than three
        words invented here -- ``ok``, ``failed`` and ``unverified`` are what a caller gets,
        and a page cannot draw a fourth.
        """
        answer = defaults.current("browser", ROOT)
        self.assertEqual("browser", answer["role"])
        self.assertIn(answer["verdict"], (runner.OK, runner.FAILED, runner.UNVERIFIED),
                      f"{answer['verdict']} is not one of the three verdicts, so a caller "
                      f"cannot tell an absent tool from a tool that said no")
        self.assertEqual(["xdg-mime", "query", "default"], answer["argv"][:3],
                         "the read is a query, and the argv is published so the page can "
                         "show the command it could not run")
        if answer["verdict"] == runner.UNVERIFIED:
            self.assertTrue(str(answer["reason"]).strip(),
                            "the page has to say what it could not read")
            self.assertIn("not installed", answer["reason"])
        if runner.which(defaults.MIME_TOOL) is None:
            self.assertEqual(runner.UNVERIFIED, answer["verdict"],
                             f"{defaults.MIME_TOOL} is not on PATH and the read answered "
                             f"{answer['verdict']}, which is a state nobody reported")
        else:  # pragma: no cover - depends on the machine
            self.assertNotEqual(runner.UNVERIFIED, answer["verdict"],
                                f"{defaults.MIME_TOOL} is installed and the read still called "
                                f"itself unverified, so the page would refuse to show an "
                                f"answer it could have had")
            self.assertTrue(str(answer["reason"]).strip() or answer["desktop_id"],
                            "the tool ran and the answer carries neither a value nor a "
                            "sentence, so the page would draw an empty row")
        unsettable = " ".join(str(entry.get("why") or "")
                              for entry in defaults.unsettable())
        self.assertIn("unverified", unsettable.lower(),
                      "a missing binary is unverified rather than a failure, and the record "
                      "has to say so or the page will show a red error for an absent tool")

    def test_a_desktop_id_that_names_no_file_is_refused(self):
        self.assertTrue(defaults.check_desktop_id("nope"))
        self.assertEqual([], defaults.check_desktop_id("app.desktop"))
        with self.assertRaises(defaults.DefaultsError) as caught:
            defaults.set_role("browser", "missing.desktop", ROOT)
        self.assertIn("not in any application directory", str(caught.exception),
                      "a desktop id that names no file would make every link of this type "
                      "fail to open, and the refusal has to say so")

    def test_the_candidate_filters_are_the_desktops_own_and_each_has_a_cite(self):
        rules = defaults.candidate_rules()
        self.assertGreaterEqual(len(rules["filters"]), 4, "the schema requires four filters")
        for rule in rules["filters"]:
            with self.subTest(key=rule["key"]):
                self.assertTrue(str(rule["why"]).strip())
                self.assertIn(":", str(rule["evidence"]),
                              "a filter with no line cite is an opinion about which programs "
                              "a person may choose")
        self.assertTrue(rules["limitation"]["consequence"],
                        "the list has a limitation and the record does not say what it costs")

    def test_the_read_order_says_the_users_own_file_wins(self):
        order = defaults.read_order()
        self.assertGreaterEqual(len(order["paths"]), 2)
        self.assertIn("user", order["description"].lower(),
                      "the reason a change made here survives a package update is that the "
                      "user's own file is read first")

    def test_the_two_tools_are_the_recorded_binaries_and_the_page_reports_both(self):
        """The names are drawn at runtime, so the static contract is the module's constants."""
        self.assertEqual(XDG["settings_tool"]["binary"], defaults.SETTINGS_TOOL)
        self.assertEqual(XDG["mime_tool"]["binary"], defaults.MIME_TOOL)
        sources = {str(getattr(row, "source", "") or "") for row in PLAN.walk()}
        self.assertIn("startup.tools_text", sources,
                      "the Startup page has no row reporting the two tools, so a person "
                      "cannot tell an absent tool from a refused write")
        self.assertIn("startup.refusal_gnome_autostart_enabled", sources)
        self.assertIn("startup.refusal_shell_wrapper", sources,
                      "a refusal recorded in the file has no row on the page, so the "
                      "sentence a person reads would have to be copied into the code")
        self.assertIn("startup.unsettable_0", sources)
        self.assertIn("startup.unsettable_1", sources,
                      "one unsettable role is explained and the other is not")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
