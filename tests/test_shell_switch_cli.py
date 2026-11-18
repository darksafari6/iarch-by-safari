# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""`iarch-shell-switch` on the command line: exit statuses, JSON, and the launcher."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import session_fake  # noqa: E402
from iarch.cli import iarch_shell_switch, shell_switch, theme_engine as engines  # noqa: E402

LAUNCHER = ROOT / "scripts" / "iarch-shell-switch.sh"
HEADER = "Copyright (C) 2026 Safari — GPL-3.0-or-later"


def call(argv, env):
    """Run the CLI with the environment it reads and a clock that never waits."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env, clear=False), session_fake.virtual_time(), \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = iarch_shell_switch.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class TheStatusCommand(unittest.TestCase):
    def test_it_reports_both_engines_and_exits_zero_when_one_shell_rule_holds(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     notification_owner=(":1.99", 111)):
            code, out, _err = call(["status"], env)
            self.assertEqual(0, code)
            self.assertIn("Classic", out)
            self.assertIn("iArch Shell", out)
            self.assertIn("running (pid 111)", out)
            self.assertIn("selected:    Classic", out)

    def test_json_mode_prints_one_object_and_nothing_else(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     notification_owner=(":1.99", 111)):
            code, out, _err = call(["status", "--json"], env)
            self.assertEqual(0, code)
            payload = json.loads(out)
            self.assertEqual("one-shell", payload["verdict"])
            self.assertEqual({"classic", "dynamic"}, set(payload["engines"]))
            self.assertEqual("classic", payload["record"]["engine"])
            self.assertIn("daemons", payload)

    def test_two_engines_running_exits_one_and_says_which(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111], "quickshell": [222]},
                                     notification_owner=(":1.99", 222)):
            code, _out, err = call(["status"], env)
            self.assertEqual(1, code)
            self.assertIn("more than one shell engine", err)

    def test_it_never_writes_anything(self):
        with session_fake.environment() as env, session_fake.session():
            call(["status", "--json"], env)
            self.assertFalse(engines.engine_record_path(env).exists())
            self.assertFalse(engines.switch_record_path(env).exists())


class TheSwitchCommand(unittest.TestCase):
    def test_a_switch_that_works_exits_zero_and_reports_its_steps(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            code, out, _err = call(["to", "dynamic"], env)
            self.assertEqual(0, code)
            for needle in ("snapshot", "stop", "start", "verify", "record", "switched"):
                self.assertIn(needle, out)
            self.assertEqual(1, len(fake.pids("quickshell")))

    def test_a_switch_that_rolls_back_exits_one_with_the_reason_on_stderr(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"quickshell": session_fake.INVISIBLE}):
            session_fake.install_shell(env)
            code, _out, err = call(["to", "dynamic"], env)
            self.assertEqual(1, code)
            self.assertIn("not up within", err)
            self.assertIn("started again", err)
            self.assertEqual("classic", json.loads(
                engines.engine_record_path(env).read_text(encoding="utf-8"))["engine"])

    def test_the_json_report_of_a_rollback_carries_the_steps_that_ran(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]},
                                     spawn_policy={"quickshell": session_fake.INVISIBLE}):
            session_fake.install_shell(env)
            code, out, _err = call(["to", "dynamic", "--json", "--budget", "1"], env)
            self.assertEqual(1, code)
            payload = json.loads(out)
            self.assertEqual("rolled-back", payload["verdict"],
                             "a switch that undid itself says so, rather than only that it failed")
            self.assertIn("error", payload)
            self.assertIn("snapshot", [step["step"] for step in payload["steps"]])
            self.assertTrue(payload["rollback"]["previous_is_up"])
            self.assertEqual("classic", payload["rollback"]["record_restored"])

    def test_a_dry_run_says_it_changed_nothing(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            code, out, _err = call(["to", "dynamic", "--dry-run"], env)
            self.assertEqual(0, code)
            self.assertIn("nothing was stopped, started or written", out)
            self.assertEqual([], fake.spawned)
            self.assertEqual([111], fake.pids("noctalia"))

    def test_an_unknown_engine_is_refused_by_the_parser_with_status_two(self):
        with session_fake.environment() as env, session_fake.session():
            with self.assertRaises(SystemExit) as caught:
                call(["to", "plasma"], env)
            self.assertEqual(2, caught.exception.code)

    def test_a_budget_that_cannot_work_is_a_usage_error(self):
        with session_fake.environment() as env, session_fake.session():
            code, _out, err = call(["to", "dynamic", "--budget", "0"], env)
            self.assertEqual(2, code)
            self.assertIn("--budget must be positive", err)

    def test_a_budget_longer_than_the_contract_warns_rather_than_failing(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            code, _out, err = call(["to", "dynamic", "--budget", "60"], env)
            self.assertEqual(0, code)
            self.assertIn("longer than the 10s", err)
            self.assertEqual(1, len(fake.pids("quickshell")),
                             "a long budget is allowed; it is only warned about")


class TheRollbackCommand(unittest.TestCase):
    def test_it_restores_the_previous_engine_and_exits_zero(self):
        with session_fake.environment() as env, \
                session_fake.session(running={"noctalia": [111]}) as fake:
            session_fake.install_shell(env)
            self.assertEqual(0, call(["to", "dynamic"], env)[0])
            code, out, _err = call(["rollback"], env)
            self.assertEqual(0, code)
            self.assertIn("rolled-back", out)
            self.assertEqual("classic", json.loads(
                engines.engine_record_path(env).read_text(encoding="utf-8"))["engine"])
            self.assertEqual([], fake.pids("quickshell"))

    def test_with_no_snapshot_it_is_a_usage_error_that_starts_nothing(self):
        with session_fake.environment() as env, session_fake.session() as fake:
            code, _out, err = call(["rollback"], env)
            self.assertEqual(2, code)
            self.assertIn("no switch to roll back", err)
            self.assertEqual([], fake.spawned)


class TheLauncher(unittest.TestCase):
    def test_it_is_present_executable_and_carries_the_header(self):
        self.assertTrue(LAUNCHER.is_file())
        self.assertTrue(LAUNCHER.stat().st_mode & 0o111)
        self.assertIn(HEADER, LAUNCHER.read_text(encoding="utf-8").splitlines()[1])

    def test_it_parses_as_bash(self):
        result = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_it_names_the_cli_it_runs(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("iarch/cli/iarch_shell_switch.py", text)
        self.assertIn('exec python3 "$cli" "$@"', text)

    def test_it_runs_the_cli_and_the_exit_status_survives(self):
        with session_fake.environment() as env:
            result = subprocess.run(["bash", str(LAUNCHER), "status", "--json"],
                                    capture_output=True, text=True, timeout=60,
                                    env={**os.environ, **env})
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual({"classic", "dynamic"}, set(payload["engines"]))

    def test_it_is_one_of_the_commands_the_linker_puts_on_path(self):
        linker = (ROOT / "scripts" / "iarch-link-cli.sh").read_text(encoding="utf-8")
        self.assertIn('"iarch-shell-switch:scripts/iarch-shell-switch.sh"', linker)


if __name__ == "__main__":
    unittest.main()
