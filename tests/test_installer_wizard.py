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
  and a banner that promises 25 steps and then prints ``[23/20]`` is worse than
  no number at all.
"""

from __future__ import annotations

import json
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


def function(name: str) -> str:
    """One whole shell function, closing brace included.

    ``region`` stops *before* its end anchor, which is what makes it right for
    slicing up to the next definition and wrong for extracting a function to
    execute: the slice would be missing its brace and bash would read the rest of
    the harness as part of the body.
    """
    return region(f"{name}() {{", "\n}") + "\n}\n"


SCAFFOLD = region("\nSTEP_TOTAL=", "check_if_chaotic_repo_was_added() {")
#: The summary names the manifest when a run stopped, so the harness needs the
#: real path function rather than a copy of its answer.
MANIFEST = function("install_manifest_path")
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
CONFIG_DIR='/tmp/safari/.config'
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
        script.write_text(PREAMBLE + SCAFFOLD + MANIFEST + extra + body, encoding="utf-8")
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
        self.assertEqual(fatal, ["Preflight", "Chaotic-AUR repository", "Core packages",
                                 "System upgrade", "Configuration payload",
                                 "Login manager"],
                         "a step became fatal, or stopped being fatal, without this "
                         "test being told. The five after the report are the ones "
                         "without which there is no session to log into; the report is "
                         "fatal from the other end, because on a machine that is not "
                         "Arch, or one whose package database a running transaction "
                         "holds, every step after it fails -- and a summary listing "
                         "twenty-four failures hides the one cause")


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
        total = re.search(r"^STEP_TOTAL=(\d+)$", TEXT, re.MULTILINE).group(1)
        self.assertIn(f"[ 1/{total}] Done step", out,
                      "the banner's count is a literal in the installer, so a test that "
                      "pinned the number here would fail on every step added and teach "
                      "nothing about the scaffolding")
        self.assertIn("\u2713 done", out)
        self.assertIn(f"[ 2/{total}] Skipped step", out)
        self.assertIn("skipped: nothing selected", out)
        self.assertIn(f"[ 3/{total}] Broken step", out)
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


class ThePaperworkAfterAFailure(unittest.TestCase):
    """A run that stopped is the run whose paperwork matters most.

    Part 6's acceptance is that a failed run reports what it touched and where the
    backups are. The manifest path used to be printed only at the end of the main
    flow, which a fatal step never reaches: it prints the summary and exits, so the
    one run that needed the answer was the one that did not get it.
    """

    def test_a_stopped_run_names_the_manifest_and_the_backups(self):
        body = ('myfail() { step_fail "the repository is missing"; return 1; }\n'
                'fatal_step "Broken step" myfail\n'
                "printf 'unreachable\\n'\n")
        status, out, rebooted = run_harness(body, extra=RUNNERS)
        self.assertEqual(1, status, "a fatal step must fail the run")
        self.assertIn("These steps did not finish:", out)
        self.assertIn("/tmp/safari/.local/state/iarch/install-manifest.txt", out,
                      "the run stopped without saying what it touched")
        self.assertIn("/tmp/safari/.config/<name>.bak.<timestamp>", out,
                      "the run stopped without saying where the backups are")
        self.assertIn("/etc/pacman.conf.bak.<epoch seconds>", out)
        self.assertNotIn("unreachable", out, "fatal_step returned instead of exiting")
        self.assertFalse(rebooted)

    def test_a_run_that_finished_still_names_the_manifest_once(self):
        status, out, _ = run_harness("step_begin \"Only step\"; finish_step\nwizard_summary\n")
        self.assertEqual(0, status)
        self.assertNotIn("install-manifest.txt", out,
                         "a clean run prints the manifest at the end of the main flow; "
                         "a summary that repeated it would say the same thing twice")


class TheQuestionsAndTheReport(unittest.TestCase):
    """What this work added: prompts that can end, and a report that runs first.

    Both defects had the shape the reboot prompt already had. A bare
    ``read -r -p`` fails at end of input and leaves its variable empty, and an
    empty answer is not one of the branches a ``(y/n)`` question offers -- so
    Ctrl-D at any of the fourteen prompts printed "Please answer 'y' or 'n'."
    and asked again, forever, and a run with stdin closed spun before it reached
    a single package step. And ``tools/preflight.py`` existed, was tested, and
    was never called by the installer it was written for.
    """

    #: Reports this test writes, so the step under test reads real findings from
    #: the real tool rather than a stub of the thing that produces them.
    BLOCKED_REPORT = {
        "os": "Ubuntu 24.04.2 LTS", "official_arch": False, "pacman_lock": True,
        "pacman": "/usr/bin/pacman", "sudo": "/usr/bin/sudo",
        "network": "GitHub check ok", "nvidia": False, "nvidia_module_loaded": False,
        "hyprland_command": "/usr/bin/Hyprland",
    }
    WARNED_REPORT = {
        "os": "Arch Linux", "official_arch": True, "pacman_lock": False,
        "pacman": "/usr/bin/pacman", "sudo": "Not found",
        "network": "GitHub check failed: could not resolve host",
        "nvidia": True, "nvidia_module_loaded": False,
        "hyprland_command": "Not found",
    }
    CLEAN_REPORT = {
        "os": "Arch Linux", "official_arch": True, "pacman_lock": False,
        "pacman": "/usr/bin/pacman", "sudo": "/usr/bin/sudo",
        "network": "GitHub check ok", "nvidia": False, "nvidia_module_loaded": False,
        "hyprland_command": "/usr/bin/Hyprland",
    }

    def run_preflight_step(self, report):
        """Execute the real step against a report this test wrote."""
        body = "".join([
            "stub=$(mktemp -d)\n",
            'cat > "$stub/report.json" <<\'EOS\'\n',
            json.dumps(report, indent=2), "\n",
            "EOS\n",
            'preflight_collect() { printf \'%s\\n\' "$stub/report.json"; }\n',
            "record_installed_file() { return 0; }\n",
            'run_step "Preflight" preflight_report\n',
            'printf \'verdict=%s\\n\' "$STEP_VERDICT"\n',
        ])
        return run_harness(body, extra=RUNNERS + function("preflight_report"))

    # --- the prompts --------------------------------------------------------

    def test_every_prompt_goes_through_the_helper_that_can_end(self):
        bare = [line.strip() for line in TEXT.splitlines()
                if "read -r -p" in line and not line.strip().startswith("#")]
        self.assertEqual([], bare,
                         "a prompt still reads straight from stdin, so an end of input "
                         "leaves its variable empty and the loop asks again forever: "
                         + "; ".join(bare))
        answered = re.findall(r"^\s*\w+=\$\(read_answer ", TEXT, re.MULTILINE)
        self.assertEqual(14, len(answered),
                         "the number of prompts changed without this test being told. "
                         "Each one needs an advertised default, because that default is "
                         "what an end of input and --yes both take")

    def test_a_prompt_with_nothing_left_to_read_takes_the_default_it_advertises(self):
        status, out, _ = run_harness(
            'answer=$(read_answer "Install now? (y/n): " n)\n'
            "printf 'got=%s\\n' \"$answer\"\n",
            extra=function("read_answer"), answers="")
        self.assertEqual(0, status)
        self.assertIn("got=n", out)
        self.assertIn("No answer to read", out,
                      "a default taken silently cannot be told from an answer given")

    def test_a_prompt_reads_what_a_person_typed(self):
        status, out, _ = run_harness(
            'answer=$(read_answer "Choose audio option (0-2): " "")\n'
            "printf 'got=%s\\n' \"$answer\"\n",
            extra=function("read_answer"), answers="2\n")
        self.assertEqual(0, status)
        self.assertIn("got=2", out)

    def test_yes_means_the_advertised_default_and_not_yes(self):
        """The whole risk of the flag: a removal prompt whose default is no."""
        status, out, _ = run_harness(
            "ASSUME_YES=1\n"
            'removal=$(read_answer "Remove these packages and their unused '
            'dependencies? (y/N): " n)\n'
            'proceed=$(read_answer "Install now? (y/n): " n)\n'
            "printf 'removal=%s proceed=%s\\n' \"$removal\" \"$proceed\"\n",
            extra=function("read_answer"))
        self.assertEqual(0, status)
        self.assertIn("removal=n proceed=n", out,
                      "--yes answered yes to everything, which turns a prompt whose "
                      "advertised default is no into a removal nobody agreed to")
        self.assertIn("(--yes)", out, "a default taken by a flag must say so in the log")

    def test_the_installer_refuses_to_ask_a_pipe(self):
        guard = TEXT.index("ERROR: this installer asks questions and stdin is not a terminal.")
        self.assertLess(guard, TEXT.index("Install ${IARCH_PRODUCT_NAME} now?"),
                        "the guard sits after the first prompt, so a piped run reads its "
                        "answers out of the pipe before anything refuses it")
        self.assertIn('[ ! -t 0 ] && [ "$ASSUME_YES" -ne 1 ]', TEXT)
        self.assertIn("exit 2", TEXT[guard:guard + 400],
                      "a refusal that exits zero tells a calling script the install worked")
        refusal = TEXT[guard:guard + 400]
        for named in ("--yes", "--preflight-only"):
            self.assertIn(named, refusal,
                          f"the refusal does not name {named}, so the person it stops has "
                          "no next step")

    def test_an_argument_nobody_defined_is_a_refusal(self):
        self.assertIn('echo "ERROR: unknown argument \'$1\'." >&2', TEXT)
        self.assertLess(TEXT.index("while [ $# -gt 0 ]; do"),
                        TEXT.index("if [[ $EUID -ne 0 ]]; then"),
                        "arguments are parsed after the root check, so --help needs root")
        usage = region("usage() {", "\n}")
        for switch in ("--yes", "--preflight-only", "--help"):
            self.assertIn(switch, usage, f"usage does not mention {switch}")

    def test_the_report_needs_neither_root_nor_a_terminal(self):
        """`--preflight-only` is a question about an install, not an install."""
        early = TEXT.index('if [ "$PREFLIGHT_ONLY" -eq 1 ]; then')
        self.assertLess(early, TEXT.index("if [[ $EUID -ne 0 ]]; then"),
                        "the read-only report is behind the root check, so asking whether "
                        "an install would work needs the privilege it is a question about")
        self.assertLess(early, TEXT.index("if [ ! -t 0 ]"),
                        "the report is behind the terminal check, so it cannot be run from "
                        "a script that is deciding whether to run the installer")
        block = TEXT[early:early + 700]
        self.assertIn('$SCRIPT_DIR/tools/preflight.py', block,
                      "REPO_DIR is not assigned until after the root check, so a report run "
                      "before it has to read SCRIPT_DIR")
        completed = subprocess.run(["bash", str(INSTALLER), "--preflight-only"],
                                   capture_output=True, text=True, timeout=120)
        self.assertIn("Hardware & compatibility (read-only)", completed.stdout)
        self.assertNotIn("must be run as root", completed.stdout + completed.stderr,
                         "the report asked for root, which the usage text says it does not")

    # --- the report as a step ----------------------------------------------

    def test_the_report_is_the_first_step_and_runs_before_anything_privileged(self):
        calls = list(STEP_CALLS.finditer(TEXT))
        self.assertEqual("Preflight", calls[0].group("title"),
                         "a privileged step runs before the report, so the machine's "
                         "answer about itself comes after something was already changed")
        self.assertEqual("fatal_step", calls[0].group("kind"),
                         "the report is advisory, which means the twenty-four failures "
                         "that follow it on a machine that cannot run them are the summary")
        self.assertLess(MAIN_FLOW.index('fatal_step "Preflight"'),
                        MAIN_FLOW.index('fatal_step "Chaotic-AUR repository"'),
                        "the first privileged step fetches a signing key before the "
                        "report has said whether this machine can run it")

    def test_a_blocker_fails_the_step(self):
        status, out, _ = self.run_preflight_step(self.BLOCKED_REPORT)
        self.assertEqual(0, status)
        self.assertIn("verdict=fail", out)
        self.assertIn("is not verified as vanilla Arch Linux", out)
        self.assertIn("db.lck exists", out)
        self.assertIn("this machine cannot run the steps that follow", out)

    def test_a_warning_is_printed_and_walked_past(self):
        status, out, _ = self.run_preflight_step(self.WARNED_REPORT)
        self.assertEqual(0, status)
        self.assertIn("verdict=ok", out,
                      "a warning stopped the install, which makes the split between a fact "
                      "and a judgement decorative")
        self.assertIn("warning: sudo is not installed", out)
        self.assertIn("warning: an NVIDIA controller is present", out)
        self.assertIn("warning: the outbound probe could not reach", out)
        self.assertNotIn("BLOCKER:", out, "a warning was reported as a blocker")

    def test_a_clean_report_says_so_instead_of_saying_nothing(self):
        status, out, _ = self.run_preflight_step(self.CLEAN_REPORT)
        self.assertEqual(0, status)
        self.assertIn("verdict=ok", out)
        self.assertIn("none, and no warning either", out,
                      "silence after a check cannot be told from a check that never ran")

    def test_the_report_goes_where_a_person_can_read_it_afterwards(self):
        extra = function("preflight_report_path")
        status, out, _ = run_harness("preflight_report_path\n", extra=extra)
        self.assertEqual(0, status)
        self.assertIn("/tmp/safari/.local/state/iarch/preflight.json", out)
        self.assertIn('record_installed_file "$path"', function("preflight_report"),
                      "the report is not in the manifest, so it is a file an uninstall "
                      "leaves behind and a person cannot find")

    # --- the display manager ------------------------------------------------

    def test_the_switch_is_written_down_before_it_happens(self):
        greeter = region("install_greeter() {", "\n}")
        self.assertIn("record_display_manager_state", greeter)
        self.assertLess(greeter.index("record_display_manager_state"),
                        greeter.index("systemctl disable sddm"),
                        "the record is written after the switch, so it says greetd was what "
                        "the machine booted before greetd")

    def test_the_record_names_the_units_that_were_enabled(self):
        body = "".join([
            "stub=$(mktemp -d)\n",
            'cat > "$stub/systemctl" <<\'EOS\'\n',
            "#!/bin/sh\n",
            '[ "$1" = is-enabled ] || exit 1\n',
            'case "$2" in ENABLED) exit 0 ;; *) exit 1 ;; esac\n',
            "EOS\n",
            'chmod +x "$stub/systemctl"\n',
            'PATH="$stub:$PATH"\n',
            "state_dir=$(mktemp -d)\n",
            'display_manager_state_path() { printf \'%s\\n\' '
            '"$state_dir/display-manager-before.txt"; }\n',
            "record_installed_file() { return 0; }\n",
            "record_display_manager_state\n",
            'printf \'state=[%s]\\n\' "$(tr \'\\n\' \' \' < "$state_dir/display-manager-before.txt")"\n',
        ])
        extra = function("record_display_manager_state")

        status, out, _ = run_harness(body.replace("ENABLED", "sddm"), extra=extra)
        self.assertEqual(0, status, out)
        self.assertIn("state=[sddm ]", out)

        status, out, _ = run_harness(body.replace("ENABLED", "nothing"), extra=extra)
        self.assertEqual(0, status, out)
        self.assertIn("state=[none ]", out,
                      "an empty state file cannot be told from a file nobody wrote")

        # A second run must not overwrite the first answer with "greetd".
        twice = body.replace("ENABLED", "sddm").replace(
            "record_display_manager_state\n",
            "record_display_manager_state\nrecord_display_manager_state\n")
        status, out, _ = run_harness(twice, extra=extra)
        self.assertEqual(0, status, out)
        self.assertIn("state=[sddm ]", out)
        self.assertIn("already recorded", out)

    # --- the DDC switch -----------------------------------------------------

    def test_the_switch_edits_the_file_the_payload_actually_deploys(self):
        """The old branch wrote a v4 key into a file the v5 payload never ships."""
        import tomllib  # Python 3.11+, which tools/toml_set_flag.py already requires

        code = "\n".join(line for line in TEXT.splitlines()
                         if not line.strip().startswith("#"))
        for gone in ("enableDdcSupport", "noctalia/settings.json"):
            self.assertNotIn(gone, code,
                             f"{gone} is code again. It was the v4 spelling, written into "
                             "a file deploy_configs replaces with a staged tree carrying "
                             "config.toml only, so the branch reported a switch it never "
                             "set; the name survives in this repository as a comment that "
                             "explains what was wrong")
        extra = function("enable_noctalia_ddc")
        deployed = (ROOT / ".config" / "noctalia" / "config.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config.toml"
            target.write_text(deployed, encoding="utf-8")
            status, out, _ = run_harness(
                f"enable_noctalia_ddc {target}\n"
                "printf 'rc=%s\\n' \"$?\"\n", extra=extra)
            self.assertEqual(0, status, out)
            self.assertIn("rc=0", out)
            parsed = tomllib.loads(target.read_text(encoding="utf-8"))
            self.assertIs(True, parsed["brightness"]["enable_ddcutil"],
                          "the switch was not set in the file the shell reads")
            self.assertIn("theme", parsed, "the rest of the deployed profile was lost")
            self.assertIn("#", target.read_text(encoding="utf-8"),
                          "the comments the generated file carries were dropped")

    def test_the_step_says_so_when_there_is_no_file_to_edit(self):
        extra = function("enable_noctalia_ddc")
        status, out, _ = run_harness(
            "enable_noctalia_ddc /nonexistent/config.toml\n"
            "printf 'rc=%s\\n' \"$?\"\n", extra=extra)
        self.assertEqual(0, status)
        self.assertIn("rc=1", out)
        self.assertIn("is not there", out,
                      "a missing file reported as success is the defect this replaced")

    # --- the two claims the steps make about themselves ---------------------

    def test_the_system_upgrade_announces_what_it_is_about_to_change(self):
        upgrade = region("upgrade_system() {", "update_user_directories() {")
        self.assertIn("packages_outdated_names", upgrade,
                      "the whole-system transaction is still a blanket --noconfirm with no "
                      "review, which is the half of INS-01 this step owns")
        self.assertLess(upgrade.index("packages_outdated_names"),
                        upgrade.index("pacman -Syu --noconfirm"),
                        "the review happens after the transaction it was for")

    def test_ownership_follows_the_paths_the_step_copied(self):
        self.assertNotIn('chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR"', TEXT,
                         "a recursive chown of the whole config directory is back: it is a "
                         "claim about every file in it, including the ones this installer "
                         "has never heard of (INS-02)")
        backup = region("copy_backup_configs() {", "apply_dolby_pipewire_profile() {")
        self.assertIn('chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR/$restored_name"',
                      backup)

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
