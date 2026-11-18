# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The engine catalogue is one table, and every probe over it says what it could not see."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import session_fake  # noqa: E402
from iarch.cli import engine_state, iarch_doctor, shell_switch, theme_engine as engines  # noqa: E402
from iarch.lib import dbus_probe  # noqa: E402


class TheCatalogue(unittest.TestCase):
    def test_there_are_exactly_two_engines_and_their_ids_are_stable(self):
        self.assertEqual(("classic", "dynamic"), engines.engine_ids())
        self.assertEqual("classic", engines.DEFAULT_ENGINE_ID,
                         "a fresh install runs the engine this repository has verified")

    def test_the_names_a_person_sees_are_not_the_upstream_project_names(self):
        names = engines.engine_names()
        self.assertEqual({"classic": "Classic", "dynamic": "iArch Shell"}, names)
        for engine_id, label in names.items():
            with self.subTest(engine=engine_id):
                lowered = label.lower()
                self.assertNotIn("noctalia", lowered)
                self.assertNotIn("quickshell", lowered)
                self.assertNotEqual(engines.engine(engine_id).binary, lowered)
        self.assertIn("iArch", names["dynamic"],
                      "the second engine is this product's own, and is named for it")

    def test_the_binary_each_engine_runs_is_the_one_the_records_name(self):
        self.assertEqual("noctalia", engines.engine("classic").binary)
        self.assertEqual("quickshell", engines.engine("dynamic").binary)

    def test_the_pack_engine_vocabulary_maps_onto_the_runtime_vocabulary_both_ways(self):
        """D-T1-03: one table translates, and it has to be total."""
        self.assertEqual({"classic": "classic", "ishell": "dynamic"},
                         engines.PACK_ENGINE_TO_ENGINE)
        self.assertEqual({"classic": "classic", "dynamic": "ishell"},
                         engines.ENGINE_TO_PACK_ENGINE)
        for record in engines.ENGINES:
            with self.subTest(engine=record.id):
                self.assertEqual(record.id,
                                 engines.PACK_ENGINE_TO_ENGINE[record.pack_engine])
                self.assertIs(record, engines.by_pack_engine(record.pack_engine))
                self.assertIs(record, engines.engine(record.id))
        self.assertEqual(set(engines.PACK_ENGINE_TO_ENGINE.values()), set(engines.engine_ids()))
        self.assertIsNone(engines.by_pack_engine("kde"))

    def test_every_engine_declares_how_it_starts_and_whether_it_can_be_asked_to_stop(self):
        classic = engines.engine("classic")
        dynamic = engines.engine("dynamic")
        self.assertEqual(("noctalia",), classic.start_command)
        self.assertIsNone(classic.stop_command,
                          "no verified exit command exists, so the switch signals the pid")
        self.assertTrue(classic.stops_by_signal)
        self.assertEqual(("quickshell", "--config", "iarch", "--daemonize", "--no-duplicate"),
                         dynamic.start_command)
        self.assertEqual(("quickshell", "kill", "--config", "iarch"), dynamic.stop_command)
        self.assertEqual(("quickshell", "list", "--json", "--config", "iarch"),
                         dynamic.instances_command)
        self.assertFalse(dynamic.stops_by_signal)
        for record in engines.ENGINES:
            self.assertTrue(record.provides_notification_server,
                            "both engines run a notification server, which is why only one "
                            "of them may run")
            self.assertTrue(record.provenance, "a command with no citation is a guess")

    def test_the_entry_point_is_the_path_the_toolkit_discovers(self):
        with session_fake.environment() as env:
            home = Path(env["HOME"])
            self.assertEqual(home / ".config" / "quickshell" / "iarch" / "shell.qml",
                             engines.shell_entry("dynamic", env))
            self.assertIsNone(engines.shell_entry("classic", env),
                              "the classic engine's entry point is not a file this project writes")
            self.assertEqual(home / ".config" / "noctalia",
                             engines.config_dir_for("classic", env))
            self.assertIsNone(engines.shell_entry("unknown", env))

    def test_the_two_records_live_where_the_rest_of_the_user_state_lives(self):
        with session_fake.environment() as env:
            self.assertEqual(Path(env["IARCH_CONFIG_DIR"]) / "shell-engine.json",
                             engines.engine_record_path(env))
            self.assertEqual(Path(env["IARCH_STATE_DIR"]) / "shell-switch.json",
                             engines.switch_record_path(env))

    def test_other_engine_names_the_one_that_must_not_be_running(self):
        self.assertEqual("dynamic", engines.other_engine("classic").id)
        self.assertEqual("classic", engines.other_engine("dynamic").id)
        self.assertIsNone(engines.other_engine("unknown"))

    def test_the_budget_is_ten_seconds_and_says_where_the_number_came_from(self):
        self.assertEqual(10.0, engines.SWITCH_BUDGET_SECONDS)
        self.assertEqual(engines.SWITCH_BUDGET_SECONDS, shell_switch.BUDGET_SECONDS)
        source = Path(engines.__file__).read_text(encoding="utf-8")
        self.assertIn("src/launch/main.cpp", source,
                      "the budget is the toolkit's own crash-loop window, and the comment "
                      "that says so carries the file it was read from")
        self.assertIn("10 seconds", source)


class TheProbes(unittest.TestCase):
    def test_a_running_engine_is_found_and_a_stopped_one_is_not(self):
        with session_fake.session(running={"noctalia": [111]}) as fake:
            scans = engines.scans(run=fake.run)
            self.assertEqual([111], list(scans["classic"].pids))
            self.assertEqual([], list(scans["dynamic"].pids))
            self.assertTrue(scans["dynamic"].searched)
            self.assertEqual([], engines.one_shell_violations(scans))

    def test_two_engines_running_is_a_violation_naming_both(self):
        with session_fake.session(running={"noctalia": [111], "quickshell": [222]}) as fake:
            violations = engines.one_shell_violations(engines.scans(run=fake.run))
            self.assertEqual(1, len(violations))
            self.assertIn("more than one shell engine", violations[0])
            self.assertIn("111", violations[0])
            self.assertIn("222", violations[0])

    def test_a_probe_that_could_not_run_says_so_instead_of_reporting_nothing(self):
        with session_fake.session(binaries=()) as fake:
            scans = engines.scans(run=fake.run)
            self.assertFalse(scans["classic"].searched)
            self.assertIn("not installed", scans["classic"].note)
            violations = engines.one_shell_violations(scans)
            self.assertEqual(2, len(violations),
                             "an unsearchable table is a violation of knowing, not a clean bill")
            for line in violations:
                self.assertIn("could not be checked", line)

    def test_only_the_dynamic_engine_can_list_its_own_instances(self):
        with session_fake.session(running={"quickshell": [333]}) as fake:
            listed, answer = engines.instances(engines.engine("dynamic"), run=fake.run)
            self.assertEqual([{"pid": 333, "config": "iarch"}], listed)
            self.assertTrue(answer.ok)
            self.assertEqual((None, None), engines.instances(engines.engine("classic"), run=fake.run))

    def test_the_ipc_call_is_the_verified_argument_order(self):
        with session_fake.session(running={"quickshell": [444]}) as fake:
            answer = engines.ipc_call(engines.IPC_TARGET_THEME, engines.IPC_FUNCTION_APPLY,
                                      ["/tmp/x"], run=fake.run)
            self.assertTrue(answer.ok)
            self.assertEqual(("quickshell", "ipc", "call", "--config", "iarch",
                              "iarch.theme", "apply", "/tmp/x"), fake.calls[-1])

    def test_the_notification_owner_is_mapped_onto_the_engine_that_holds_it(self):
        with session_fake.session(running={"quickshell": [555]},
                                  notification_owner=(":1.99", 555)) as fake:
            report = engines.notification_owner(run=fake.run)
            self.assertEqual(":1.99", report["unique_name"])
            self.assertEqual(555, report["pid"])
            self.assertEqual("dynamic", report["engine"])

    def test_an_owner_that_is_neither_engine_is_reported_without_one(self):
        with session_fake.session(running={"noctalia": [666]},
                                  notification_owner=(":1.20", 999)) as fake:
            report = engines.notification_owner(run=fake.run)
            self.assertEqual(999, report["pid"])
            self.assertIsNone(report["engine"])

    def test_a_bus_nobody_owns_is_an_answer_and_a_missing_dbus_send_is_not(self):
        with session_fake.session() as fake:
            self.assertFalse(dbus_probe.notification_server(run=fake.run).owned)
            self.assertTrue(dbus_probe.notification_server(run=fake.run).searched)
            self.assertIn("no process owns", dbus_probe.notification_server(run=fake.run).note)
        with session_fake.session(binaries=("pgrep",)) as fake:
            owner = dbus_probe.notification_server(run=fake.run)
            self.assertFalse(owner.searched)
            self.assertIn("not installed", owner.note)


class TheRecords(unittest.TestCase):
    def test_an_absent_record_is_the_repository_default_and_says_it_was_not_stored(self):
        with session_fake.environment() as env:
            record = engine_state.engine_record(env)
            self.assertEqual("classic", record["engine"])
            self.assertFalse(record["stored"])
            self.assertEqual(1, record["schema_version"])

    def test_a_record_naming_an_unknown_engine_falls_back_rather_than_crashing(self):
        with session_fake.environment() as env:
            path = engines.engine_record_path(env)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"engine": "kde"}), encoding="utf-8")
            record = engine_state.engine_record(env)
            self.assertEqual("classic", record["engine"])
            self.assertFalse(record["stored"])

    def test_a_record_that_is_not_json_is_read_as_absent(self):
        with session_fake.environment() as env:
            path = engines.engine_record_path(env)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not json", encoding="utf-8")
            self.assertFalse(engine_state.engine_record(env)["stored"])

    def test_writing_a_record_is_atomic_and_refuses_an_unknown_engine(self):
        with session_fake.environment() as env:
            path = engine_state.write_engine_record("dynamic", "classic", env=env)
            self.assertEqual({"schema_version": 1, "engine": "dynamic", "previous": "classic"},
                             {key: value for key, value in json.loads(path.read_text()).items()
                              if key != "switched_at"})
            self.assertEqual("dynamic", engine_state.selected_id(env))
            with self.assertRaises(ValueError):
                engine_state.write_engine_record("kde", None, env=env)

    def test_the_snapshot_carries_what_a_rollback_has_to_restore(self):
        with session_fake.environment() as env:
            engine_state.write_switch_snapshot("classic", [111], {"engine": "classic"}, 10.0, env)
            snapshot = engine_state.switch_record(env)
            self.assertEqual("classic", snapshot["previous_engine"])
            self.assertEqual([111], snapshot["previous_pids"])
            self.assertEqual(10.0, snapshot["budget_seconds"])
            self.assertIn("taken_at", snapshot)


class ThePreflight(unittest.TestCase):
    def test_a_missing_binary_is_found_before_anything_is_stopped(self):
        with session_fake.environment() as env, \
                session_fake.session(binaries=("pgrep", "noctalia"),
                                     running={"noctalia": [111]}) as fake:
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep)
            self.assertIn("not installed", str(caught.exception))
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"), "the session was left alone")
            self.assertEqual("refused", caught.exception.report["verdict"])

    def test_a_missing_entry_point_is_found_before_anything_is_stopped(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep)
            self.assertIn("shell.qml", str(caught.exception))
            self.assertIn("installer", str(caught.exception))
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))


class TheDoctorCheck(unittest.TestCase):
    """`iarch-doctor shell` is read-only, and its verdicts are the three it documents."""

    def ask(self, env, argv=("shell", "--json")):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), mock.patch.dict(os.environ, env, clear=False):
            code = iarch_doctor.main(list(argv))
        text = stdout.getvalue()
        return code, (json.loads(text) if text.strip().startswith("{") else text)

    def test_one_engine_running_and_owning_the_bus_is_ok(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"quickshell": [777]},
                                     notification_owner=(":1.99", 777)):
            code, payload = self.ask(env)
            self.assertEqual(0, code)
            self.assertEqual("ok", payload["verdict"])
            self.assertEqual(["dynamic"], payload["running"])
            self.assertEqual("dynamic", payload["notification"]["engine"])
            self.assertEqual([], payload["problems"])

    def test_it_changes_nothing_while_it_looks(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     notification_owner=(":1.99", 111)) as fake:
            self.ask(env)
            self.assertEqual([111], fake.pids("noctalia"))
            self.assertEqual([], fake.spawned)
            self.assertFalse(any(call[:2] == ("quickshell", "kill") for call in fake.calls))

    def test_no_engine_running_is_an_error_when_the_table_could_be_read(self):
        with session_fake.environment() as env, session_fake.session():
            code, payload = self.ask(env)
            self.assertEqual(1, code)
            self.assertEqual("error", payload["verdict"])
            self.assertTrue(any("no shell engine is running" in problem
                                for problem in payload["problems"]))

    def test_a_probe_that_could_not_run_is_unverified_and_exits_zero(self):
        with session_fake.environment() as env, session_fake.session(binaries=()):
            code, payload = self.ask(env)
            self.assertEqual(0, code, "a check that could not happen is not a failed desktop")
            self.assertEqual("unverified", payload["verdict"])
            self.assertEqual([], payload["running"])

    def test_another_notification_daemon_is_reported_as_a_problem(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [888], "dunst": [999]},
                                     notification_owner=(":1.99", 888)):
            _code, payload = self.ask(env)
            self.assertTrue(any("dunst" in problem for problem in payload["problems"]),
                            payload["problems"])

    def test_two_engines_running_is_reported_as_a_violation(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111], "quickshell": [222]},
                                     notification_owner=(":1.99", 222)):
            code, payload = self.ask(env)
            self.assertEqual(1, code)
            self.assertEqual(["classic", "dynamic"], payload["running"])
            self.assertTrue(any("more than one shell engine" in problem
                                for problem in payload["problems"]))

    def test_the_human_report_names_the_engines_the_way_the_product_does(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     notification_owner=(":1.99", 111)):
            _code, text = self.ask(env, argv=("shell",))
            self.assertIn("Classic", text)
            self.assertIn("iArch Shell", text)
            self.assertIn("one shell engine, one notification server", text)
            self.assertNotIn("noctalia", text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
