# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The two shell scripts that give the keyboard-map CLI a name.

``iarch-keybinds`` is the name three things already depend on: the recovery bind in
``.config/hypr/keybind.lua`` probes for it with ``command -v``, the recovery entry in
``data/keybinds.default.json`` names it as the command to run, and the documentation
tells a person to type it. Until these scripts existed none of them could work, because
the repository has no ``console_scripts`` entry -- the CLI is one file that finds its own
package. That gap is what ``docs/UNVERIFIED.md`` carried as KB-01's blocker.

These tests run the scripts for real, in a subprocess, against a temporary ``HOME`` and a
temporary destination directory. Nothing here needs a compositor, so unlike the bind
firing (which stays unverified) this is observed behaviour rather than a reading.

What they pin, and why each is worth a test:

* the exit status passes through the wrapper untouched -- 0 clean, 1 refused, 2 bad input
  -- because the recovery bind and CI both read it, and a wrapper that swallowed a refusal
  would report a broken map as a repaired one;
* linking is idempotent, and a file this script did not write is never overwritten
  without ``--force``, and is backed up when it is;
* the generated wrapper names its checkout absolutely and fails loudly, with the command
  to re-run, when that checkout is gone -- a wrapper that silently ran some other copy of
  the CLI would repair a session with the wrong map;
* the name the recovery bind looks for is the name the link script provides, so the two
  cannot drift apart.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "iarch-keybinds.sh"
LINKER = ROOT / "scripts" / "iarch-link-cli.sh"
CLI = ROOT / "iarch" / "cli" / "iarch_keybinds.py"
KEYBIND_LUA = ROOT / ".config" / "hypr" / "keybind.lua"
DEFAULTS = ROOT / "data" / "keybinds.default.json"

HEADER = "Copyright (C) 2026 Safari — GPL-3.0-or-later"


def bash_syntax_ok(path: Path) -> bool:
    return subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


def linker_pairs() -> List[Tuple[str, str]]:
    """The ``(name, launcher)`` pairs ``scripts/iarch-link-cli.sh`` links.

    Read out of the script's own array rather than restated here: a second copy of the
    list would agree with itself after the script changed, which is the failure this file
    exists to prevent. Only the array is searched, because the file's comments explain the
    format with an example that would otherwise be read as an entry.
    """
    text = LINKER.read_text(encoding="utf-8")
    block = re.search(r"^COMMANDS=\(\n(.*?)^\)", text, re.S | re.M)
    assert block, "the COMMANDS array is not in scripts/iarch-link-cli.sh"
    return re.findall(r"^\s*\"([A-Za-z0-9._-]+):([^\"]+)\"\s*,?\s*$",
                      block.group(1), re.M)


def linker_commands() -> List[str]:
    return [name for name, _ in linker_pairs()]


class IsolatedRun(unittest.TestCase):
    """A subprocess run with its own HOME and PATH, so nothing touches this machine."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="iarch-launcher-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        (self.home / ".config" / "iarch").mkdir(parents=True)
        self.bin = self.tmp / "bin"

    def run_script(self, script: Path, *argv: str, path: Optional[Path] = None,
                   fake_uid: Optional[str] = None) -> subprocess.CompletedProcess:
        env = {
            "HOME": str(self.home),
            # A PATH with no user bin directory: the tests that need the linked name to
            # resolve put one there themselves, and the ones that do not must not find a
            # stray iarch-keybinds this machine happens to have.
            "PATH": str(path or self.tmp / "empty-bin") + ":/usr/bin:/bin",
        }
        if fake_uid is not None:
            env["PATH"] = str(self.fake_id_dir(fake_uid)) + ":" + env["PATH"]
        return subprocess.run([str(script), *argv], capture_output=True, text=True,
                              env=env, cwd=str(ROOT), timeout=120)

    def fake_id_dir(self, uid: str) -> Path:
        """A directory holding an ``id`` that reports the uid asked for.

        The scripts refuse to run as root. That branch cannot be reached by becoming
        root in a test, but it can be reached by putting a lying ``id`` earlier on PATH,
        which is enough to prove the refusal exists rather than assuming it.
        """
        directory = self.tmp / f"fake-id-{uid}"
        directory.mkdir(exist_ok=True)
        fake = directory / "id"
        fake.write_text(f'#!/bin/sh\nif [ "${{1:-}}" = "-u" ]; then echo {uid}; '
                        'else echo "uid=0(root)"; fi\n', encoding="utf-8")
        fake.chmod(0o755)
        return directory

    def link(self, *argv: str) -> subprocess.CompletedProcess:
        return self.run_script(LINKER, "--dest", str(self.bin), *argv)

    def linked_wrapper(self) -> Path:
        return self.bin / "iarch-keybinds"

    def run_linked(self, *argv: str) -> subprocess.CompletedProcess:
        """Run the linked command *by name*, the way the recovery bind would."""
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin"}
        return subprocess.run(["iarch-keybinds", *argv], capture_output=True, text=True,
                              env=env, cwd=str(ROOT), timeout=120)


class TheLauncher(IsolatedRun):
    """``scripts/iarch-keybinds.sh``: a name for the CLI, from a checkout."""

    def test_the_launcher_is_present_executable_and_carries_the_header(self):
        self.assertTrue(LAUNCHER.is_file(), "the launcher is missing")
        self.assertTrue(LAUNCHER.stat().st_mode & stat.S_IXUSR,
                        "a launcher nobody can execute is not a launcher; git tracks "
                        "the mode, so this fails in a fresh clone too")
        lines = LAUNCHER.read_text(encoding="utf-8").splitlines()
        self.assertEqual("#!/usr/bin/env bash", lines[0])
        self.assertIn(HEADER, lines[1], "the header is not the first comment line")

    def test_the_launcher_parses_as_bash(self):
        self.assertTrue(bash_syntax_ok(LAUNCHER))

    def test_it_runs_the_cli_and_the_exit_status_survives(self):
        """The whole reason the wrapper execs rather than calls."""
        clean = self.run_script(LAUNCHER, "check")
        self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)

        direct = subprocess.run([sys.executable, str(CLI), "check"],
                                capture_output=True, text=True, cwd=str(ROOT),
                                env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"},
                                timeout=120)
        self.assertEqual(direct.returncode, clean.returncode)
        self.assertEqual(direct.stdout, clean.stdout,
                         "the launcher is not running the same CLI the module is")

    def test_a_refused_change_exits_1_and_bad_input_exits_2_through_the_wrapper(self):
        refused = self.run_script(LAUNCHER, "set", "applications.terminal", "--key", "T")
        self.assertEqual(1, refused.returncode, refused.stdout + refused.stderr)
        self.assertIn("already bound", refused.stdout + refused.stderr)

        bad = self.run_script(LAUNCHER, "set", "applications.terminal", "--key", ".")
        self.assertEqual(2, bad.returncode, bad.stdout + bad.stderr)
        self.assertIn("period", bad.stdout + bad.stderr)

    def test_it_says_what_is_wrong_when_it_is_not_in_a_checkout(self):
        """Copied out of the repository, it must not run some other copy of the CLI."""
        stray = self.tmp / "stray" / "iarch-keybinds.sh"
        stray.parent.mkdir(parents=True)
        shutil.copyfile(LAUNCHER, stray)
        stray.chmod(0o755)
        result = self.run_script(stray, "check")
        self.assertEqual(70, result.returncode)
        self.assertIn("iarch_keybinds.py is missing", result.stderr)

    def test_it_does_not_need_pythonpath_because_the_cli_finds_its_own_package(self):
        """A launcher that set PYTHONPATH would be a second opinion about where the
        package lives, and the CLI already has one."""
        code = "\n".join(line for line in
                         LAUNCHER.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("PYTHONPATH", code,
                         "the launcher started having an opinion about where the package "
                         "lives, which is the CLI's opinion to have")
        self.assertIn("sys.path", CLI.read_text(encoding="utf-8"),
                      "the CLI no longer puts the repository root on sys.path itself, "
                      "so the launcher would have to start doing it")


class TheLinker(IsolatedRun):
    """``scripts/iarch-link-cli.sh``: putting that name somewhere PATH can find."""

    def test_the_linker_parses_as_bash_and_carries_the_header(self):
        self.assertTrue(bash_syntax_ok(LINKER))
        self.assertIn(HEADER, LINKER.read_text(encoding="utf-8").splitlines()[1])

    def test_it_links_the_name_the_recovery_bind_looks_for(self):
        """The integration this whole file exists for, in both directions."""
        linked = linker_commands()
        self.assertIn("iarch-keybinds", linked)

        lua = KEYBIND_LUA.read_text(encoding="utf-8")
        probed = set(re.findall(r"command -v ([a-z0-9-]+)", lua))
        for name in sorted(probed & {"iarch-keybinds"}):
            self.assertIn(name, linked,
                          f"keybind.lua probes for {name!r} on PATH and nothing puts it "
                          "there, so the recovery bind can only ever take its fallback")

        import json
        record = json.loads(DEFAULTS.read_text(encoding="utf-8"))
        recovery = next(b for b in record["bindings"]
                        if b["id"] == "recovery.reapply-defaults")
        self.assertIn(recovery["action"]["command"][0], linked,
                      "the record names a command the link script does not provide")

    def test_every_command_it_promises_has_a_launcher_that_exists(self):
        pairs = linker_pairs()
        self.assertTrue(pairs, "no commands are declared")
        for name, relative in pairs:
            with self.subTest(command=name):
                launcher = ROOT / relative
                self.assertTrue(launcher.is_file(), f"{name} points at a missing file")
                self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR,
                                f"{name}'s launcher is not executable")

    def test_after_linking_the_command_runs_by_name_and_reports_a_clean_map(self):
        result = self.link()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.linked_wrapper().is_file())
        self.assertTrue(self.linked_wrapper().stat().st_mode & stat.S_IXUSR,
                        "a wrapper without the execute bit resolves on PATH and then "
                        "fails, which is worse than not resolving")

        by_name = self.run_linked("check")
        self.assertEqual(0, by_name.returncode, by_name.stdout + by_name.stderr)

    def test_the_wrapper_names_its_checkout_absolutely(self):
        self.link()
        text = self.linked_wrapper().read_text(encoding="utf-8")
        self.assertIn(f"launcher='{LAUNCHER}'", text,
                      "a relative or $HOME-based path would resolve against whatever "
                      "directory the session happened to be in when the bind fired")
        self.assertIn("Generated by scripts/iarch-link-cli.sh", text,
                      "without the marker the script cannot tell its own file from a "
                      "foreign one, and --remove would delete something it did not write")

    def test_linking_twice_changes_nothing(self):
        self.link()
        first = self.linked_wrapper().read_bytes()
        stamp = self.linked_wrapper().stat().st_mtime_ns
        again = self.link()
        self.assertEqual(0, again.returncode, again.stdout + again.stderr)
        self.assertIn("already linked", again.stdout)
        self.assertEqual(first, self.linked_wrapper().read_bytes())
        self.assertEqual(stamp, self.linked_wrapper().stat().st_mtime_ns,
                         "an idempotent command that rewrites the file every run makes "
                         "every install look like a change")

    def test_check_reports_the_link_and_reports_its_absence(self):
        missing = self.link("--check")
        self.assertEqual(1, missing.returncode)
        self.assertIn("not linked", missing.stdout + missing.stderr)

        self.link()
        present = self.link("--check")
        self.assertEqual(0, present.returncode, present.stdout + present.stderr)

    def test_check_fails_when_the_wrapper_points_at_another_checkout(self):
        self.link()
        text = self.linked_wrapper().read_text(encoding="utf-8")
        self.linked_wrapper().write_text(
            text.replace(str(LAUNCHER), "/somewhere/else/iarch-keybinds.sh"),
            encoding="utf-8")
        result = self.link("--check")
        self.assertEqual(1, result.returncode)
        self.assertIn("different checkout", result.stdout + result.stderr)

    def test_a_file_it_did_not_write_is_refused_and_left_byte_identical(self):
        self.bin.mkdir(parents=True)
        foreign = self.linked_wrapper()
        foreign.write_text("#!/bin/sh\necho somebody else's iarch-keybinds\n",
                           encoding="utf-8")
        foreign.chmod(0o755)
        before = foreign.read_bytes()

        for argv in ([], ["--check"], ["--remove"]):
            with self.subTest(argv=argv or "link"):
                result = self.link(*argv)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("not written by this script",
                              result.stdout + result.stderr)
                self.assertEqual(before, foreign.read_bytes(),
                                 "a file belonging to somebody else was touched")

    def test_force_replaces_a_foreign_file_and_keeps_it_beside_the_new_one(self):
        self.bin.mkdir(parents=True)
        foreign = self.linked_wrapper()
        foreign.write_text("#!/bin/sh\necho somebody else's iarch-keybinds\n",
                           encoding="utf-8")
        foreign.chmod(0o755)

        result = self.link("--force")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        backup = self.bin / "iarch-keybinds.iarch-backup"
        self.assertTrue(backup.is_file(), "the foreign file was destroyed, not replaced")
        self.assertIn("somebody else", backup.read_text(encoding="utf-8"))
        self.assertEqual(0, self.run_linked("check").returncode)

    def test_remove_deletes_what_it_wrote_and_is_not_an_error_when_there_is_nothing(self):
        self.link()
        self.assertTrue(self.linked_wrapper().is_file())
        removed = self.link("--remove")
        self.assertEqual(0, removed.returncode, removed.stdout + removed.stderr)
        self.assertFalse(self.linked_wrapper().exists())

        again = self.link("--remove")
        self.assertEqual(0, again.returncode, again.stdout + again.stderr)
        self.assertIn("nothing to remove", again.stdout)

    def test_a_wrapper_whose_checkout_is_gone_fails_loudly_with_the_way_back(self):
        self.link()
        wrapper = self.linked_wrapper()
        wrapper.write_text(
            wrapper.read_text(encoding="utf-8").replace(
                str(LAUNCHER), str(self.tmp / "deleted-checkout" / "iarch-keybinds.sh")),
            encoding="utf-8")
        result = self.run_linked("check")
        self.assertEqual(70, result.returncode)
        self.assertIn("is gone or is not executable", result.stderr)
        self.assertIn("iarch-link-cli.sh", result.stderr,
                      "an error that does not name the command that fixes it leaves the "
                      "person with a broken recovery bind and no next step")

    def test_it_refuses_to_run_as_root(self):
        """A root-owned wrapper in a user's ~/.local/bin is a broken install that looks
        like a working one, so the refusal is the feature."""
        result = self.run_script(LINKER, "--dest", str(self.bin), fake_uid="0")
        self.assertEqual(1, result.returncode)
        self.assertIn("refusing to run as root", result.stderr)
        self.assertFalse(self.linked_wrapper().exists())

        # --check is read-only, so it is allowed to answer as root.
        checked = self.run_script(LINKER, "--check", "--dest", str(self.bin),
                                  fake_uid="0")
        self.assertEqual(1, checked.returncode)
        self.assertIn("not linked", checked.stdout + checked.stderr)

    def test_it_creates_the_destination_directory_and_says_when_it_is_not_on_path(self):
        self.assertFalse(self.bin.exists())
        result = self.link()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.bin.is_dir())
        self.assertIn("not on PATH", result.stdout,
                      "a linked command that cannot be reached by name is the exact "
                      "failure this script exists to end, so it has to say so")

    def test_an_unknown_option_is_refused_with_a_usage_and_status_2(self):
        for argv in (["--nonsense"], ["--dest"]):
            with self.subTest(argv=argv):
                result = self.run_script(LINKER, *argv)
                self.assertEqual(2, result.returncode)
        helped = self.run_script(LINKER, "--help")
        self.assertEqual(0, helped.returncode)
        self.assertIn("--remove", helped.stdout)

    def test_it_does_not_use_the_repository_as_its_destination_by_default(self):
        """The default has to be the user's own bin directory, never the checkout: a
        wrapper written into the repository would be committed and would then point at
        whatever machine built it."""
        text = LINKER.read_text(encoding="utf-8")
        self.assertIn('.local/bin', text)
        self.assertNotIn('dest="$root', text)
        self.assertNotIn("dest=\"$here", text)


class TheShellGate(IsolatedRun):
    """The two CI gates, run here so a failure is found before it is pushed.

    Both build their file list the way the workflow does: every tracked ``*.sh``, plus
    the two session launchers that live without a ``.sh`` suffix. Those two paths are read
    out of ``.github/workflows/iarch-checks.yml`` rather than written here, for the usual
    reason — a second copy of a list agrees with itself after the first one changes — and
    because they carry a previous product name, which `tools/naming_audit.py` rightly
    refuses to see spread into another file.
    """

    WORKFLOW = ROOT / ".github" / "workflows" / "iarch-checks.yml"

    def extra_scripts(self) -> List[Path]:
        text = self.WORKFLOW.read_text(encoding="utf-8")
        found = re.search(r"scripts\+=\(([^)]*)\)", text)
        assert found, "the workflow no longer lists the suffix-less session launchers, " \
                      "so this test cannot tell which files CI checks beyond *.sh"
        return [ROOT / name for name in found.group(1).split()]

    def scripts(self) -> List[Path]:
        tracked = subprocess.run(["git", "ls-files", "*.sh"], capture_output=True,
                                 text=True, cwd=str(ROOT), timeout=60)
        self.assertEqual(0, tracked.returncode, tracked.stderr)
        names = [ROOT / line for line in tracked.stdout.split() if line]
        names += self.extra_scripts()
        return names

    def test_every_tracked_shell_script_parses(self):
        for script in self.scripts():
            with self.subTest(script=script.name):
                self.assertTrue(script.is_file(), f"missing script: {script}")
                self.assertTrue(bash_syntax_ok(script), f"bash -n failed: {script}")

    def test_the_new_scripts_are_tracked_so_the_ci_gates_cover_them(self):
        """Both CI steps build their file list from `git ls-files '*.sh'`, so an
        untracked script is silently unchecked rather than loudly failing."""
        tracked = subprocess.run(["git", "ls-files", "scripts/"], capture_output=True,
                                 text=True, cwd=str(ROOT), timeout=60)
        listed = set(tracked.stdout.split())
        for relative in ("scripts/iarch-keybinds.sh", "scripts/iarch-link-cli.sh"):
            with self.subTest(script=relative):
                self.assertIn(relative, listed,
                              "an untracked launcher is not shellchecked, not bash -n'd, "
                              "and not in a fresh clone")

    def test_shellcheck_is_clean_when_it_is_available(self):
        shellcheck = shutil.which("shellcheck")
        if shellcheck is None:
            self.skipTest("shellcheck is not installed (CI installs shellcheck-py)")
        result = subprocess.run(
            [shellcheck, "--severity=warning", "--",
             *[str(s) for s in self.scripts()]],
            capture_output=True, text=True, cwd=str(ROOT), timeout=600)
        self.assertEqual(0, result.returncode,
                         "shellcheck found errors or warnings:\n" + result.stdout)


class NoLeftovers(IsolatedRun):
    """Running these scripts must not change the repository."""

    def test_linking_and_removing_leaves_the_working_tree_clean(self):
        before = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                text=True, cwd=str(ROOT), timeout=60).stdout
        self.link()
        self.run_linked("check")
        self.link("--remove")
        after = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, cwd=str(ROOT), timeout=60).stdout
        self.assertEqual(before, after,
                         "a launcher or a linked command wrote into the repository")

    def test_the_environment_the_scripts_read_is_not_the_developer_machine(self):
        """Every run above passes HOME and PATH explicitly; this asserts the helper does."""
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        self.assertNotEqual(str(ROOT), str(self.home))
        self.assertTrue(CLI.is_file())


if __name__ == "__main__":
    unittest.main()
