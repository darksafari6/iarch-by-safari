# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The installer's wizard: every step numbered, every step answering.

``install.sh`` runs on a machine this repository cannot see, so most of what it
does can only be read, not run. What *can* be run here is the part that decides
what a person sees: the scaffolding that numbers the steps and prints a verdict,
the banner, and the reboot prompt. Those are extracted from the installer and
executed, which is why a mismatch between ``STEP_TOTAL`` and the number of steps
fails here rather than in front of somebody watching a half-finished install.

Two defects this file exists to keep fixed:

* The reboot prompt used to loop forever. An answer that was neither y nor n
  printed "Please answer" and asked again, and on a closed stdin ``read`` returns
  immediately with an empty answer -- so an unattended run spun on the same
  question until somebody killed it. An empty answer now means no, and a run with
  no terminal is not asked at all.
* ``STEP_TOTAL`` is a literal in one part of a file whose steps are calls in
  another part of the same file. Nothing but a test stops them drifting apart,
  and a banner that promises 20 steps and then prints ``[23/20]`` is worse than
  no number at all.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "install.sh"
TEXT = INSTALLER.read_text(encoding="utf-8")

#: The step calls, one per line, in the main flow.
STEP_CALLS = re.compile(r"^(?P<kind>run_step|fatal_step)\s+\"(?P<title>[^\"]+)\"", re.MULTILINE)

#: A transaction that names a target. `-Syy` and `-Syu` are deliberately not
#: matched: `-S` followed by another letter is a different operation, and both of
#: those change the databases rather than install a named package.
NAMED_TRANSACTION = re.compile(r"\b(?:pacman|yay)\s+-S(?:\s|$)")


def region(start_anchor: str, end_anchor: str) -> str:
    """A slice of the installer, with the anchors asserted rather than assumed.

    Extracting by index is how this repository tests its shell files, and it fails
    loudly when a refactor moves an anchor: a slice that silently came out empty
    would test nothing at all.
    """
    assert TEXT.count(start_anchor) == 1, f"{start_anchor!r} is not unique in install.sh"
    start = TEXT.index(start_anchor)
    assert end_anchor in TEXT[start:], f"{end_anchor!r} does not follow {start_anchor!r}"
    return TEXT[start:TEXT.index(end_anchor, start)]


SCAFFOLD = region("\nSTEP_TOTAL=", "check_if_chaotic_repo_was_added() {")
#: The two helpers that begin a step and always finish it, and the prompt that
#: ends the run. They live after the step functions, so a harness that wants them
#: has to ask for them.
RUNNERS = region("run_step() {", "prompt_reboot() {")
REBOOT = region("prompt_reboot() {", "# --- Main Installation Flow ---")
MAIN_FLOW = TEXT[TEXT.index("# --- Main Installation Flow ---"):]

#: The variables the scaffolding reads and the installer defines earlier. A
#: harness that forgot one would still run, and would be testing a different
#: program than the one that ships.
PREAMBLE = """#!/usr/bin/env bash
set -uo pipefail
ALL_OFF=''; BOLD=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; MAGENTA=''
REPO_DIR=%r
ACTUAL_USER='safari'
ACTUAL_USER_HOME='/tmp/safari'
DEFAULT_INSTALL=0
IARCH_PRODUCT_NAME='iArch by Safari'
IARCH_PRODUCT_TAGLINE='Glass Hyprland desktop session for Arch Linux and Fedora'
""" % str(ROOT)


def run_harness(body: str, *, extra: str = "", answers: str = "", use_pty: bool = False,
                timeout: float = 20.0) -> tuple[int, str, bool]:
    """Run the scaffolding plus a driver body; report status, output, rebooted.

    ``reboot`` is stubbed, so a test that reached the real command would still
    only write a file -- and the file is the assertion.
    """
    directory = Path(tempfile.mkdtemp(prefix="iarch-wizard-"))
    try:
        script = directory / "harness.sh"
        script.write_text(PREAMBLE + SCAFFOLD + extra + body, encoding="utf-8")
        stub = directory / "reboot"
        stub.write_text('#!/usr/bin/env bash\nprintf "rebooted\\n" >> "$REBOOT_LOG"\nexit 0\n')
        stub.chmod(0o755)
        log = directory / "reboot.log"
        env = {**os.environ, "PATH": f"{directory}:/usr/bin:/bin", "REBOOT_LOG": str(log),
               "HOME": str(directory)}
        if not use_pty:
            completed = subprocess.run(["bash", str(script)], capture_output=True,
                                       text=True, env=env, input=answers, timeout=timeout)
            return completed.returncode, completed.stdout + completed.stderr, log.exists()

        master, slave = os.openpty()
        try:
            process = subprocess.Popen(["bash", str(script)], stdin=slave, stdout=slave,
                                       stderr=slave, env=env)
            os.close(slave)
            os.write(master, answers.encode("utf-8"))
            chunks: List[str] = []
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait(timeout=timeout)
                raise AssertionError(
                    "the prompt never finished: it is still asking after the answer "
                    "it was given") from exc
            while select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                chunks.append(chunk.decode("utf-8", "replace"))
            return status, "".join(chunks), log.exists()
        finally:
            os.close(master)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class TheStepList(unittest.TestCase):
    """What the main flow says it will do, read out of the file."""

    def setUp(self) -> None:
        self.calls = list(STEP_CALLS.finditer(TEXT))

    def titles(self) -> List[str]:
        return [match.group("title") for match in self.calls]

    def test_the_total_written_down_is_the_number_of_steps(self):
        total = re.search(r"^STEP_TOTAL=(\d+)$", TEXT, re.MULTILINE)
        self.assertIsNotNone(total, "STEP_TOTAL is not a literal assignment any more")
        self.assertEqual(
            int(total.group(1)), len(self.calls),
            "STEP_TOTAL and the step calls disagree, so the banner promises a count "
            "the run does not reach: " + ", ".join(self.titles()))

    def test_every_step_title_is_unique(self):
        titles = self.titles()
        self.assertEqual(len(titles), len(set(titles)),
                         "two steps announce the same title, so the summary cannot "
                         "say which one failed")

    def test_the_main_flow_does_not_begin_a_step_it_never_finishes(self):
        # The flow lists steps and nothing else; run_step and fatal_step are the
        # only two callers of step_begin, and each of them calls finish_step too.
        self.assertNotIn("step_begin", MAIN_FLOW,
                         "the main flow begins a step directly, so that step can end "
                         "with no verdict printed")
        call_sites = [line.strip() for line in TEXT.splitlines()
                      if line.strip().startswith("step_begin ")]
        self.assertEqual(len(call_sites), 2, call_sites)
        for helper in ("run_step() {", "fatal_step() {"):
            body = region(helper, "\n}" )
            with self.subTest(helper=helper):
                self.assertIn("step_begin", body)
                self.assertIn("finish_step", body,
                              f"{helper} begins a step it does not finish")

    def test_the_repository_artifacts_each_have_a_step(self):
        """The steps that install this repository rather than somebody's packages."""
        for function in ("install_repo_commands", "install_session_path",
                         "install_menu_entry", "deploy_wallpapers"):
            with self.subTest(step=function):
                self.assertIn(f"{function}() {{", TEXT, f"{function} is not defined")
                self.assertTrue(
                    re.search(rf"^(run_step|fatal_step)\s+\"[^\"]+\"\s+{function}\b",
                              TEXT, re.MULTILINE),
                    f"{function} is defined but never called as a step, so the "
                    "artifacts it owns are still not installed")

    def test_the_steps_that_stop_the_install_are_the_ones_with_no_session(self):
        fatal = [match.group("title") for match in STEP_CALLS.finditer(TEXT)
                 if match.group("kind") == "fatal_step"]
        self.assertEqual(fatal, ["Chaotic-AUR repository", "Core packages",
                                 "System upgrade", "Configuration payload",
                                 "Login manager"],
                         "a step became fatal, or stopped being fatal, without this "
                         "test being told: without these five there is no session to "
                         "log into, and continuing produces a machine that is harder "
                         "to diagnose than a stopped one")


class ThePackageTransactions(unittest.TestCase):
    """Nothing installs a package without going through lib/packages.sh."""

    def test_the_library_is_sourced_before_the_flow_that_calls_it(self):
        source_line = '. "$REPO_DIR/lib/packages.sh"'
        self.assertIn(source_line, TEXT)
        self.assertLess(TEXT.index(source_line), TEXT.index("# --- Main Installation Flow ---"),
                        "the library is sourced after the flow that calls it")

    def test_no_named_transaction_bypasses_the_library(self):
        named = [line.strip() for line in TEXT.splitlines()
                 if NAMED_TRANSACTION.search(line) and not line.strip().startswith("#")]
        self.assertEqual(
            named, [],
            "a package transaction bypasses lib/packages.sh, so it reinstalls a "
            "target that is already at the latest version: " + "; ".join(named))

    def test_the_two_database_operations_are_still_there(self):
        self.assertIn("pacman -Syy", TEXT, "the mirrorlist seeding disappeared")
        self.assertIn("pacman -Syu --noconfirm", TEXT, "the full upgrade disappeared")
        self.assertNotIn("yay -S", TEXT,
                         "a yay transaction is in the installer rather than the library")

    def test_the_system_upgrade_forgets_the_cached_plan(self):
        upgrade = region("upgrade_system() {", "update_user_directories() {")
        self.assertIn("pacman -Syu", upgrade)
        self.assertIn("packages_invalidate_cache", upgrade,
                      "the upgrade changes every version the later plans are computed "
                      "from, so the cache has to be dropped or they report stale states")


class TheVerdicts(unittest.TestCase):
    """The scaffolding, executed."""

    def test_a_step_finishes_with_the_verdict_it_asked_for(self):
        status, out, _ = run_harness("""
step_begin "Done step"; finish_step
step_begin "Skipped step"; step_skip "nothing selected"; finish_step
step_begin "Broken step"; step_fail "the repository is missing"; finish_step
wizard_summary
""")
        self.assertIn("[ 1/24] Done step", out)
        self.assertIn("\u2713 done", out)
        self.assertIn("[ 2/24] Skipped step", out)
        self.assertIn("skipped: nothing selected", out)
        self.assertIn("[ 3/24] Broken step", out)
        self.assertIn("failed: the repository is missing", out)
        self.assertIn("\u2713 1 done   \u2013 1 skipped   \u2717 1 failed", out)
        self.assertIn("Broken step", out.split("These steps did not finish:")[1])
        self.assertEqual(status, 1, "a run with a failed step must not report success")

    def test_a_clean_run_exits_zero(self):
        status, out, _ = run_harness("""
step_begin "Only step"; finish_step
wizard_summary
""")
        self.assertIn("\u2713 1 done   \u2013 0 skipped   \u2717 0 failed", out)
        self.assertEqual(status, 0)

    def test_run_step_turns_a_bare_failure_into_a_verdict(self):
        status, out, _ = run_harness("""
failing() { return 3; }
skipping() { step_skip "not selected"; return 0; }
run_step "Failing" failing
run_step "Skipping" skipping
wizard_summary
""", extra=RUNNERS)
        self.assertIn("failed: Failing returned a failure", out)
        self.assertIn("skipped: not selected", out)
        self.assertEqual(status, 1)

    def test_the_banner_is_a_rectangle(self):
        _, out, _ = run_harness("wizard_banner\n")
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 5, f"the banner is not five lines: {lines}")
        widths = {len(line) for line in lines}
        self.assertEqual(len(widths), 1, f"the banner's lines differ in width: {widths}")
        self.assertTrue(lines[0].startswith("  \u256d") and lines[0].endswith("\u256e"))
        self.assertTrue(lines[-1].startswith("  \u2570") and lines[-1].endswith("\u256f"))
        for line in lines[1:-1]:
            self.assertTrue(line.startswith("  \u2502") and line.endswith("\u2502"), line)
        self.assertIn("iArch by Safari", out)
        self.assertIn("installer v", out)
        self.assertIn("user safari", out)

    def test_a_long_line_is_cut_to_the_box_rather_than_widening_it(self):
        _, out, _ = run_harness(
            "IARCH_PRODUCT_TAGLINE='a tagline far too long to fit inside the box the "
            "banner draws around it, which is the whole point of cutting it'\n"
            "wizard_banner\n")
        widths = {len(line) for line in out.splitlines() if line.strip()}
        self.assertEqual(len(widths), 1, f"a long line broke the box: {widths}")


class TheRebootPrompt(unittest.TestCase):
    """The question at the end, which used to be unanswerable."""

    def test_no_terminal_means_no_question(self):
        status, out, rebooted = run_harness("prompt_reboot\n", extra=REBOOT)
        self.assertEqual(status, 0)
        self.assertIn("Not rebooting", out)
        self.assertFalse(rebooted, "a test rebooted the machine")

    def test_a_default_install_is_not_asked_either(self):
        status, out, rebooted = run_harness("DEFAULT_INSTALL=1\nprompt_reboot\n", extra=REBOOT)
        self.assertEqual(status, 0)
        self.assertIn("Not rebooting", out)
        self.assertFalse(rebooted)

    def test_answering_no_ends_the_prompt(self):
        status, out, rebooted = run_harness("prompt_reboot\n", extra=REBOOT,
                                            answers="n\n", use_pty=True)
        self.assertEqual(status, 0, "answering n did not end the prompt")
        self.assertIn("Log out and back in", out)
        self.assertFalse(rebooted, "answering n rebooted the machine")

    def test_an_empty_answer_means_no(self):
        status, out, rebooted = run_harness("prompt_reboot\n", extra=REBOOT,
                                            answers="\n", use_pty=True)
        self.assertEqual(status, 0, "pressing enter at the prompt did not end it")
        self.assertIn("Log out and back in", out)
        self.assertFalse(rebooted)

    def test_an_unreadable_answer_is_asked_again_and_then_ends(self):
        status, out, rebooted = run_harness("prompt_reboot\n", extra=REBOOT,
                                            answers="perhaps\nn\n", use_pty=True)
        self.assertEqual(status, 0)
        self.assertIn("Please answer y or n.", out)
        self.assertIn("Log out and back in", out)
        self.assertFalse(rebooted)

    def test_answering_yes_reaches_the_reboot_command(self):
        status, _, rebooted = run_harness("prompt_reboot\n", extra=REBOOT,
                                          answers="y\n", use_pty=True)
        self.assertEqual(status, 0)
        self.assertTrue(rebooted, "answering y did not reach the reboot command")


class TheShellIsStillValid(unittest.TestCase):
    """Cheap, and it turns a syntax error into a named failure instead of noise."""

    def test_bash_parses_the_installer(self):
        completed = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_shellcheck_has_nothing_to_say_if_it_is_installed(self):
        shellcheck = shutil.which("shellcheck")
        if shellcheck is None:
            self.skipTest("shellcheck is not installed")
        completed = subprocess.run(
            [shellcheck, "--severity=warning", str(INSTALLER),
             str(ROOT / "lib" / "packages.sh"), str(ROOT / "tests" / "test_packages.sh")],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
