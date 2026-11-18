# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The engine switch: one shell at a time, proved up, or put back exactly as it was."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import session_fake  # noqa: E402
from iarch.cli import engine_state, shell_switch, theme_engine as engines  # noqa: E402
from iarch.lib import processes  # noqa: E402


def steps(report) -> list:
    return [step["step"] for step in report["steps"]]


class ASwitchThatWorks(unittest.TestCase):
    def switch(self, env, fake, target="dynamic", **kwargs):
        return shell_switch.switch(target, env, run=fake.run, spawn=fake.spawn,
                                   clock=fake.clock, sleep=fake.sleep, **kwargs)

    def test_it_stops_the_old_engine_before_it_starts_the_new_one(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            self.assertEqual("switched", report["verdict"])
            self.assertEqual(["snapshot", "stop", "start", "verify", "record"], steps(report))
            self.assertEqual([], fake.pids("noctalia"), "the old engine was left running")
            self.assertEqual(1, len(fake.pids("quickshell")))
            self.assertEqual([("quickshell", "--config", "iarch", "--daemonize",
                               "--no-duplicate")], fake.spawned)

    def test_the_snapshot_is_taken_before_anything_is_stopped(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            snapshot = json.loads(Path(report["steps"][0]["path"]).read_text(encoding="utf-8"))
            self.assertEqual("classic", snapshot["previous_engine"])
            self.assertEqual([111], snapshot["previous_pids"])
            self.assertEqual("classic", snapshot["previous_record"]["engine"])
            self.assertEqual(engines.SWITCH_BUDGET_SECONDS, snapshot["budget_seconds"])
            self.assertEqual(str(engines.switch_record_path(env)), report["steps"][0]["path"])

    def test_the_choice_is_recorded_only_after_the_engine_is_up(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            record = json.loads(Path(report["record_path"]).read_text(encoding="utf-8"))
            self.assertEqual("dynamic", record["engine"])
            self.assertEqual("classic", record["previous"])
            self.assertEqual(1, record["schema_version"])
            self.assertEqual("dynamic", engine_state.selected_id(env))

    def test_the_engine_that_has_an_exit_command_is_asked_before_it_is_signalled(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"quickshell": [222]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake, target="classic")
            self.assertEqual("switched", report["verdict"])
            self.assertTrue(fake.called("quickshell", "kill", "--config", "iarch"))
            self.assertEqual([("noctalia",)], fake.spawned)
            stop = next(step for step in report["steps"] if step["step"] == "stop")
            self.assertTrue(stop["stopped"])
            self.assertIn("answered", stop["command"],
                          "the engine's own exit command was asked, and its answer is reported")
            kill_at = next(index for index, call in enumerate(fake.calls)
                           if call[:2] == ("quickshell", "kill"))
            last_pgrep = max(index for index, call in enumerate(fake.calls)
                             if call[0] == "pgrep")
            self.assertLess(kill_at, last_pgrep,
                            "the exit command was asked after the proof polls began, so the "
                            "switch started the new engine before stopping the old one")

    def test_the_proof_is_the_engine_own_instance_list_when_it_can_be_asked(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            verify = next(step for step in report["steps"] if step["step"] == "verify")
            self.assertTrue(verify["up"])
            self.assertEqual("instances", verify["how"])
            self.assertGreaterEqual(verify["attempts"], 1)

    def test_a_process_without_an_instance_list_is_reported_as_the_weaker_proof(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}, instances_ok=False) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            verify = next(step for step in report["steps"] if step["step"] == "verify")
            self.assertEqual("process-only", verify["how"],
                             "an engine that could be asked and did not list itself must not be "
                             "reported as though it had")

    def test_switching_to_the_engine_that_is_already_running_changes_nothing(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"quickshell": [333]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake)
            self.assertEqual("already", report["verdict"])
            self.assertEqual([], fake.spawned)
            self.assertEqual([333], fake.pids("quickshell"))
            self.assertFalse(engines.switch_record_path(env).exists(),
                             "no snapshot was taken, because nothing was stopped")
            self.assertEqual("dynamic", engine_state.selected_id(env),
                             "the record now agrees with the session it describes")

    def test_a_record_that_disagrees_with_the_session_is_corrected_rather_than_ignored(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"quickshell": [333]}) as fake:
            session_fake.install_shell(env)
            engine_state.write_engine_record("classic", None, env=env)
            report = self.switch(env, fake)
            self.assertEqual("already", report["verdict"])
            self.assertEqual("dynamic", engine_state.selected_id(env))
            self.assertIn("record", steps(report))

    def test_a_dry_run_plans_the_switch_and_touches_nothing(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            report = self.switch(env, fake, dry_run=True)
            self.assertEqual("dry-run", report["verdict"])
            self.assertEqual(["stop", "start", "verify"], steps(report))
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))
            self.assertFalse(Path(report["record_path"]).exists())
            self.assertFalse(engines.switch_record_path(env).exists())
            self.assertTrue(report["steps"][0]["by_signal"],
                            "the plan says the classic engine is stopped by a signal")


class ASwitchThatFails(unittest.TestCase):
    def test_an_engine_that_never_comes_up_is_rolled_back_inside_the_budget(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"quickshell": session_fake.INVISIBLE}) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep, budget=1.0)
            report = caught.exception.report
            self.assertEqual("rolled-back", report["verdict"])
            self.assertLessEqual(fake.now, 1.0 + 2 * processes.DEFAULT_GRACE_SECONDS,
                                 "the rollback was given the budget plus the grace a stopped "
                                 "process gets, and took longer than that")
            undo = report["rollback"]
            self.assertTrue(undo["previous_is_up"], "the session was left with no shell")
            self.assertIn("stop-half-started", [step["step"] for step in undo["steps"]])
            self.assertIn("restart-previous", [step["step"] for step in undo["steps"]])
            self.assertEqual(("noctalia",), fake.spawned[-1],
                             "the last thing the switch started was the engine it had stopped")
            self.assertEqual("classic", engine_state.selected_id(env),
                             "a refused switch must not record itself as having happened")
            message = str(caught.exception)
            for needle in ("not up within 1 seconds", "stopped", "started again"):
                self.assertIn(needle, message)

    def test_a_spawn_that_fails_brings_the_previous_engine_back(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"quickshell": session_fake.FAILS}) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep)
            self.assertEqual("rolled-back", caught.exception.report["verdict"])
            self.assertTrue(caught.exception.report["rollback"]["previous_is_up"])
            self.assertEqual("classic", engine_state.selected_id(env))
            self.assertIn("could not be started", str(caught.exception))

    def test_an_engine_that_will_not_stop_is_not_replaced(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}, protected=(111,)) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep)
            self.assertEqual("refused", caught.exception.report["verdict"])
            self.assertIsNone(caught.exception.report["rollback"],
                              "nothing was started, so there was nothing to undo")
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))
            self.assertIn("could not be stopped", str(caught.exception))

    def test_two_engines_running_is_refused_without_guessing_which_to_keep(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111], "quickshell": [222]}) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn)
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))
            self.assertEqual([222], fake.pids("quickshell"))
            self.assertIn("more than one shell engine", str(caught.exception))

    def test_a_process_table_that_cannot_be_read_never_reports_a_successful_switch(self):
        with session_fake.environment() as env, \
                session_fake.session(running={}, binaries=("quickshell", "noctalia",
                                                           "hyprctl", "dbus-send")) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep, budget=1.0)
            verify = next(step for step in caught.exception.report["steps"]
                          if step["step"] == "verify")
            self.assertEqual("unsearchable", verify["how"])
            self.assertIn("not installed", verify["note"])
            self.assertFalse(caught.exception.report["rollback"]["previous_is_up"])

    def test_the_default_budget_is_the_ten_seconds_the_contract_names(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"quickshell": session_fake.INVISIBLE}) as fake:
            session_fake.install_shell(env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                    clock=fake.clock, sleep=fake.sleep)
            self.assertEqual(10.0, caught.exception.report["budget_seconds"])
            verify = next(step for step in caught.exception.report["steps"]
                          if step["step"] == "verify")
            self.assertLessEqual(verify["elapsed"], 10.0)
            self.assertGreater(verify["attempts"], 1, "the budget was not polled, it was slept")

    def test_an_unknown_engine_is_a_usage_error_that_changed_nothing(self):
        with session_fake.environment() as env, session_fake.session() as fake:
            with self.assertRaises(shell_switch.SwitchError) as caught:
                shell_switch.switch("plasma", env, run=fake.run, spawn=fake.spawn)
            self.assertIn("classic (Classic)", str(caught.exception))
            self.assertIn("dynamic (iArch Shell)", str(caught.exception))
            self.assertEqual([], fake.spawned)


if __name__ == "__main__":
    unittest.main()
