# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""`iarch-shell-switch rollback`: the recovery path, and the snapshots it refuses."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import session_fake  # noqa: E402
from iarch.cli import engine_state, shell_switch, theme_engine as engines  # noqa: E402


class RollingBackByHand(unittest.TestCase):
    def switched(self, env, fake):
        session_fake.install_shell(env)
        return shell_switch.switch("dynamic", env, run=fake.run, spawn=fake.spawn,
                                   clock=fake.clock, sleep=fake.sleep)

    def test_rollback_restores_the_snapshotted_engine_and_stops_the_other(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            self.switched(env, fake)
            self.assertEqual("dynamic", engine_state.selected_id(env))
            report = shell_switch.rollback(env, run=fake.run, spawn=fake.spawn,
                                           clock=fake.clock, sleep=fake.sleep)
            self.assertEqual("rolled-back", report["verdict"])
            self.assertEqual("classic", engine_state.selected_id(env))
            self.assertEqual([("noctalia",)], fake.spawned[1:],
                             "the only thing the rollback started was the previous engine")
            self.assertEqual([], fake.pids("quickshell"))
            self.assertIn("stop-other", [step["step"] for step in report["steps"]])

    def test_rollback_stops_other_before_starting_previous(self):
        with session_fake.environment() as env, session_fake.session(running={"noctalia": [111]}) as fake:
            self.switched(env, fake)
            def spawn(command):
                self.assertEqual([], fake.pids("quickshell"))
                return fake.spawn(command)
            report = shell_switch.rollback(env, run=fake.run, spawn=spawn,
                                           clock=fake.clock, sleep=fake.sleep)
            steps = [step["step"] for step in report["steps"]]
            self.assertLess(steps.index("stop-other"), steps.index("restart-previous"))

    def test_rollback_refuses_to_start_if_other_engine_survives(self):
        with session_fake.environment() as env, session_fake.session(
                running={"noctalia": [111]}, protected=[111]) as fake:
            session_fake.install_shell(env)
            engine_state.write_switch_snapshot("dynamic", [], {"engine": "dynamic"}, 10.0, env)
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.rollback(env, run=fake.run, spawn=fake.spawn,
                                      clock=fake.clock, sleep=fake.sleep)
            self.assertIn("could not prove", str(caught.exception))
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))

    def test_rollback_of_an_engine_that_is_already_back_only_fixes_the_record(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            self.switched(env, fake)
            fake.running["quickshell"] = []
            fake.start("noctalia", 111)
            report = shell_switch.rollback(env, run=fake.run, spawn=fake.spawn,
                                           clock=fake.clock, sleep=fake.sleep)
            self.assertEqual(["already-running"], [step["step"] for step in report["steps"]][:1])
            self.assertEqual("classic", engine_state.selected_id(env))
            self.assertEqual([], fake.spawned[1:], "nothing was started a second time")

    def test_rollback_with_no_snapshot_says_there_is_nothing_to_undo(self):
        with session_fake.environment() as env, session_fake.session() as fake:
            with self.assertRaises(shell_switch.SwitchError) as caught:
                shell_switch.rollback(env, run=fake.run, spawn=fake.spawn)
            self.assertIn("no switch to roll back", str(caught.exception))
            self.assertIn(str(engines.switch_record_path(env)), str(caught.exception))

    def test_rollback_refuses_a_snapshot_naming_an_engine_it_does_not_know(self):
        with session_fake.environment() as env, session_fake.session() as fake:
            engine_state.write_switch_snapshot("plasma", [], {"engine": "classic"}, 10.0, env)
            with self.assertRaises(shell_switch.SwitchError) as caught:
                shell_switch.rollback(env, run=fake.run, spawn=fake.spawn)
            self.assertIn("does not know", str(caught.exception))
            self.assertEqual([], fake.spawned)

    def test_rollback_that_cannot_start_the_previous_engine_says_so(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"noctalia": session_fake.FAILS}) as fake:
            engine_state.write_switch_snapshot("classic", [111], {"engine": "classic"}, 10.0, env)
            fake.running["noctalia"] = []
            with self.assertRaises(shell_switch.RefusedError) as caught:
                shell_switch.rollback(env, run=fake.run, spawn=fake.spawn,
                                      clock=fake.clock, sleep=fake.sleep)
            self.assertIn("could not be started", str(caught.exception))



if __name__ == "__main__":
    unittest.main()
