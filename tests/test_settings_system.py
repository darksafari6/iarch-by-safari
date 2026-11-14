#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the machine readers behind the Home page, run against fixture directories.

``iarch/settings-app/iarch_settings/services/system.py:11`` states the design and then
names this file as its proof: every figure the Home page shows is a file the kernel already
publishes, so the module reads files and runs no command at all -- no ``uname``, no
``lsb_release``, no ``upower``, no shell. *"A command needs a binary that may not be
installed, may print a different sentence on Arch than on Fedora, and cannot be tested
without a machine; a file under /proc or /sys has one format and can be tested by pointing
this module at a directory of fixtures, which is what tests/test_settings_system.py does."*

So every reader here is called with a fixture ``proc``, ``sys_root`` or ``etc``, and the
assertions are about the numbers those fixtures hold. That is the whole point of taking the
root as a parameter: a test that read the real ``/proc`` would pass on this machine and say
nothing about whether the parsing is right, and would fail on a machine that differs.

The second property is the one that decides what a person sees. A value that cannot be read
comes back as ``None``, never as a zero and never as an invented string -- a desktop with no
battery has *no battery row*, not a 0% one, and a container with no ``/proc/meminfo`` says
the figure is unavailable. Those are opposite statements about the machine, and only one of
them is true. Each reader is therefore tested twice: once against a fixture that has the
value, and once against an empty directory, where the answer has to be ``None`` or an empty
list rather than a plausible number.

The third is that ``/etc/os-release`` is *parsed* and never sourced. It is shell syntax, and
a settings panel that ran ``. /etc/os-release`` to read a label would be a panel that
executed a file it did not write -- so a fixture holding a command substitution is asserted
to come back as literal text.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.services import system  # noqa: E402

MODULE_PATH = ROOT / "iarch" / "settings-app" / "iarch_settings" / "services" / "system.py"
SOURCE = MODULE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

OS_RELEASE = """# A fixture, in the shape every distribution ships.
NAME="Arch Linux"
PRETTY_NAME="Arch Linux"
ID=arch
ID_LIKE=
VERSION_ID="2024.06.01"
BUILD_ID=rolling
ANSI_COLOR="38;2;23;147;209"
HOME_URL="https://archlinux.org/"
"""


def make_proc(base: Path, *, uptime: Optional[str] = "372266.41 1204550.19\n",
              loadavg: Optional[str] = "0.52 0.58 0.59 2/1834 44231\n",
              meminfo: Optional[str] = ("MemTotal:       16306624 kB\n"
                                        "MemFree:         8123456 kB\n"
                                        "MemAvailable:   12345678 kB\n"
                                        "Buffers:          234567 kB\n"),
              stat: Optional[str] = ("cpu  10132153 2094 3289794 123456789 45678 0 12345 678\n"
                                     "cpu0 10132153 2094 3289794 123456789 45678 0 12345 678\n"
                                     "intr 123456789\n")) -> Path:
    """A ``/proc`` with the four files this module reads, any of them omittable."""
    proc = base / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    for name, text in (("uptime", uptime), ("loadavg", loadavg),
                       ("meminfo", meminfo), ("stat", stat)):
        if text is not None:
            (proc / name).write_text(text, encoding="utf-8")
    return proc


def make_supply(base: Path, supplies: Dict[str, Dict[str, str]]) -> Path:
    """A ``/sys`` with the named power supplies and their files."""
    sys_root = base / "sys"
    for name, files in supplies.items():
        path = sys_root / "class" / "power_supply" / name
        path.mkdir(parents=True, exist_ok=True)
        for key, value in files.items():
            (path / key).write_text(value + "\n", encoding="utf-8")
    sys_root.mkdir(parents=True, exist_ok=True)
    return sys_root


def make_etc(base: Path, text: Optional[str] = OS_RELEASE) -> Path:
    etc = base / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    if text is not None:
        (etc / "os-release").write_text(text, encoding="utf-8")
    return etc


class Fixture(unittest.TestCase):
    """A temporary root with a ``proc``, a ``sys`` and an ``etc`` under it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.proc = make_proc(self.base)
        self.sys_root = make_supply(self.base, {
            "BAT0": {"capacity": "73", "status": "Discharging"},
            "AC": {"online": "1"},
        })
        self.etc = make_etc(self.base)
        self.empty = self.base / "nowhere"
        self.empty.mkdir(parents=True, exist_ok=True)


class TestEveryFigureComesOutOfAFixtureFile(Fixture):
    """The numbers asserted are the numbers written into the fixture, not this machine's."""

    def test_the_uptime_is_the_first_field_of_the_fixture(self):
        self.assertAlmostEqual(372266.41, system.uptime_seconds(self.proc), places=2)

    def test_the_load_average_is_the_first_three_fields_of_the_fixture(self):
        self.assertEqual((0.52, 0.58, 0.59), system.load_average(self.proc))

    def test_memory_is_in_kibibytes_and_the_used_figure_is_total_minus_available(self):
        figures = system.memory(self.proc)
        self.assertEqual(16306624, figures["total_kib"])
        self.assertEqual(12345678, figures["available_kib"])
        self.assertEqual(8123456, figures["free_kib"])
        self.assertEqual(16306624 - 12345678, figures["used_kib"])
        self.assertAlmostEqual(24.29, figures["used_percent"], places=2)

    def test_available_and_free_are_both_reported_because_they_are_not_the_same_number(self):
        figures = system.memory(self.proc)
        self.assertNotEqual(figures["available_kib"], figures["free_kib"],
                            "the fixture says the two are equal, so the test cannot tell "
                            "whether the reader mixed them up")
        self.assertGreater(figures["available_kib"], figures["free_kib"],
                           "MemAvailable is what could be given to a new process without "
                           "swapping, which is more than MemFree and is the number a person "
                           "means by 'how much is left'")

    def test_the_cpu_counters_are_the_first_stat_line_in_order(self):
        times = system.cpu_times(self.proc)
        self.assertIsNotNone(times)
        self.assertEqual(["user", "nice", "system", "idle", "iowait", "irq", "softirq",
                          "steal"], list(times))
        self.assertEqual(10132153, times["user"])
        self.assertEqual(678, times["steal"])

    def test_the_per_cpu_lines_are_not_read_as_the_total(self):
        """`cpu ` with a trailing space is the aggregate; `cpu0` is one core."""
        proc = make_proc(self.base / "cpu0only",
                         stat="cpu0 1 2 3 4 5 6 7 8\ncpu  10 20 30 40 50 60 70 80\n")
        times = system.cpu_times(proc)
        self.assertEqual(10, times["user"], "the per-cpu line was read as the total")

    def test_the_distro_comes_out_of_the_fixtures_os_release(self):
        distro = system.distro(self.etc)
        self.assertEqual("Arch Linux", distro["name"])
        self.assertEqual("arch", distro["id"])
        self.assertEqual("2024.06.01", distro["version_id"])
        self.assertIsNone(distro["like"], "an empty ID_LIKE became an empty string, which "
                                          "the Home page would draw as a label")

    def test_a_battery_is_read_with_its_status_and_what_the_status_implies(self):
        found = system.batteries(self.sys_root)
        self.assertEqual(1, len(found))
        entry = found[0]
        self.assertEqual("BAT0", entry["name"])
        self.assertEqual(73, entry["percent"])
        self.assertEqual("Discharging", entry["status"])
        self.assertIs(False, entry["charging"])
        self.assertIs(False, entry["plugged_in"])

    def test_on_mains_is_true_from_the_ac_supply(self):
        self.assertIs(True, system.power_on_ac(self.sys_root))

    def test_the_primary_battery_is_the_first_one_and_two_are_sorted(self):
        sys_root = make_supply(self.base / "two", {
            "BAT1": {"capacity": "40", "status": "Charging"},
            "BAT0": {"capacity": "90", "status": "Full"},
        })
        found = system.batteries(sys_root)
        self.assertEqual(["BAT0", "BAT1"], [entry["name"] for entry in found],
                         "a two-battery machine reports its batteries in whatever order the "
                         "filesystem happens to list them")
        self.assertEqual("BAT0", system.primary_battery(sys_root)["name"])

    def test_the_plugged_in_and_charging_pairs_cover_the_four_statuses(self):
        for status, charging, plugged in (("Charging", True, True),
                                          ("Discharging", False, False),
                                          ("Full", False, True),
                                          ("Not charging", False, True),
                                          ("Unknown", False, False)):
            sys_root = make_supply(self.base / f"status-{status.replace(' ', '_')}",
                                   {"BAT0": {"capacity": "50", "status": status}})
            entry = system.batteries(sys_root)[0]
            with self.subTest(status=status):
                self.assertEqual(charging, entry["charging"])
                self.assertEqual(plugged, entry["plugged_in"],
                                 f"'{status}' means the mains are connected and the reader "
                                 f"said otherwise, so the page would show a battery icon "
                                 f"draining while plugged in")


class TestAnUnreadableValueIsNoneAndNeverAZero(Fixture):
    """The second half of every reader: what a machine without that file answers."""

    def test_an_empty_proc_answers_none_for_every_figure(self):
        self.assertIsNone(system.uptime_seconds(self.empty))
        self.assertIsNone(system.load_average(self.empty))
        self.assertIsNone(system.cpu_times(self.empty))
        figures = system.memory(self.empty)
        self.assertIsNone(figures["total_kib"])
        self.assertIsNone(figures["used_kib"])
        self.assertIsNone(figures["used_percent"],
                          "a percentage nobody could measure came back as a number, and 0% "
                          "memory used is a claim about a machine this module could not read")

    def test_a_machine_with_no_battery_has_no_battery_row(self):
        sys_root = make_supply(self.base / "nobattery", {"AC": {"online": "1"}})
        self.assertEqual([], system.batteries(sys_root))
        self.assertIsNone(system.primary_battery(sys_root))

    def test_a_missing_power_supply_directory_is_the_same_answer(self):
        self.assertEqual([], system.batteries(self.empty))
        self.assertIsNone(system.power_on_ac(self.empty),
                          "no AC supply came back as False, which is 'on battery' -- the "
                          "opposite statement about a desktop or a container")

    def test_an_ac_supply_that_publishes_nothing_is_none_rather_than_false(self):
        sys_root = make_supply(self.base / "acblank", {"AC": {"online": ""}})
        self.assertIsNone(system.power_on_ac(sys_root))

    def test_off_mains_is_false_and_not_none(self):
        sys_root = make_supply(self.base / "offac", {"AC": {"online": "0"}})
        self.assertIs(False, system.power_on_ac(sys_root),
                      "0 was read as 'unknown', so a laptop on battery would show no power "
                      "state at all")

    def test_an_etc_with_no_os_release_answers_none_for_every_field(self):
        distro = system.distro(self.empty)
        self.assertEqual({}, system.os_release(self.empty))
        for key, value in distro.items():
            with self.subTest(field=key):
                self.assertIsNone(value, f"{key} was invented for a machine with no "
                                         f"os-release")

    def test_the_usr_lib_fallback_is_tried_when_etc_has_no_file(self):
        """A distribution that ships only /usr/lib/os-release still has a name."""
        base = self.base / "fallback"
        (base / "etc").mkdir(parents=True)
        target = base / "usr" / "lib" / "os-release"
        target.parent.mkdir(parents=True)
        target.write_text('PRETTY_NAME="Fedora Linux 41"\nID=fedora\n', encoding="utf-8")
        distro = system.distro(base / "etc")
        self.assertEqual("Fedora Linux 41", distro["name"],
                         "the fallback looked for usr *inside* the etc directory, which "
                         "exists on no real system")
        self.assertEqual("fedora", distro["id"])

    def test_the_etc_copy_wins_over_the_distributions_own(self):
        base = self.base / "both"
        (base / "etc").mkdir(parents=True)
        (base / "usr" / "lib").mkdir(parents=True)
        (base / "etc" / "os-release").write_text('PRETTY_NAME="Administrator copy"\n',
                                                 encoding="utf-8")
        (base / "usr" / "lib" / "os-release").write_text('PRETTY_NAME="Shipped copy"\n',
                                                         encoding="utf-8")
        self.assertEqual("Administrator copy", system.distro(base / "etc")["name"])

    def test_a_malformed_file_answers_none_rather_than_raising(self):
        base = self.base / "malformed"
        proc = make_proc(base, uptime="not a number\n", loadavg="0.5 0.4\n",
                         meminfo="MemTotal: kB\n", stat="cpu  a b c d e f g h\n")
        self.assertIsNone(system.uptime_seconds(proc))
        self.assertIsNone(system.load_average(proc), "two load averages were read as three")
        self.assertIsNone(system.cpu_times(proc))
        self.assertIsNone(system.memory(proc)["total_kib"])

    def test_a_battery_publishing_no_capacity_has_no_percentage(self):
        sys_root = make_supply(self.base / "nocap", {"BAT0": {"status": "Unknown"}})
        entry = system.batteries(sys_root)[0]
        self.assertIsNone(entry["percent"], "a missing capacity became 0%, so the Home page "
                                            "would show an empty battery that is not empty")
        self.assertEqual("Unknown", entry["status"])

    def test_a_battery_publishing_no_status_has_no_status(self):
        sys_root = make_supply(self.base / "nostatus", {"BAT0": {"capacity": "50"}})
        entry = system.batteries(sys_root)[0]
        self.assertIsNone(entry["status"])
        self.assertIs(False, entry["charging"])
        self.assertIs(False, entry["plugged_in"],
                      "a status nobody could read was guessed at, and 'plugged in' is not "
                      "the safe guess: it hides the warning a person needs")

    def test_a_status_containing_a_space_survives_the_read(self):
        """The kernel publishes `Not charging`, and a field split would truncate it."""
        sys_root = make_supply(self.base / "notcharging",
                               {"BAT0": {"capacity": "88", "status": "Not charging"}})
        entry = system.batteries(sys_root)[0]
        self.assertEqual("Not charging", entry["status"],
                         "the status was truncated at its space, so it matched none of the "
                         "four the reader names")
        self.assertIs(True, entry["plugged_in"],
                      "a laptop on mains at a charge threshold was reported as not plugged "
                      "in, which is a battery icon draining while the cable is connected")
        self.assertIs(False, entry["charging"])


class TestNoCommandIsEverRun(unittest.TestCase):
    """The design claim, checked against the module's own syntax tree."""

    def test_the_module_imports_no_way_to_run_a_program(self):
        imported = set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("subprocess", "pty", "shlex", "commands", "popen2"):
            with self.subTest(module=banned):
                self.assertNotIn(banned, imported,
                                 f"system.py imports {banned}, and the whole reason it reads "
                                 f"files is that a command cannot be tested without a machine")

    def test_no_call_reaches_a_shell(self):
        called = set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name):
                        called.add(f"{func.value.id}.{func.attr}")
                    else:
                        called.add(func.attr)
                elif isinstance(func, ast.Name):
                    called.add(func.id)
        for banned in ("os.system", "os.popen", "os.exec", "spawn", "check_output",
                       "check_call", "Popen", "run"):
            with self.subTest(call=banned):
                self.assertNotIn(banned, called,
                                 f"system.py calls {banned}, which runs a program")

    def test_the_kernel_is_read_from_a_syscall_and_not_from_the_uname_binary(self):
        self.assertIn("os.uname()", SOURCE)
        self.assertNotIn('"uname"', SOURCE)
        self.assertNotIn("'uname'", SOURCE)
        info = system.kernel()
        self.assertEqual({"sysname", "release", "machine", "node"}, set(info))
        self.assertTrue(info["sysname"])

    def test_os_release_is_parsed_and_never_sourced(self):
        """A command substitution in the file has to come back as literal text."""
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp)
            (etc / "os-release").write_text(
                'NAME="$(touch /tmp/pwned-by-os-release)"\nID=test\n', encoding="utf-8")
            values = system.os_release(etc)
            self.assertEqual("$(touch /tmp/pwned-by-os-release)", values["NAME"],
                             "the file was executed rather than parsed, so a settings panel "
                             "ran a file it did not write")
            self.assertFalse(Path("/tmp/pwned-by-os-release").exists())

    def test_quotes_are_removed_and_comments_and_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp)
            (etc / "os-release").write_text(
                "# a comment\n\nNAME='Single Quoted'\nID=bare\nEMPTY=\n", encoding="utf-8")
            values = system.os_release(etc)
            self.assertEqual("Single Quoted", values["NAME"])
            self.assertEqual("bare", values["ID"])
            self.assertEqual("", values["EMPTY"])
            self.assertNotIn("# a comment", values)

    def test_the_reported_keys_are_the_recorded_ones(self):
        self.assertEqual(("NAME", "VERSION", "VERSION_ID", "ID", "ID_LIKE", "PRETTY_NAME"),
                         system.OS_RELEASE_KEYS,
                         "PRETTY_NAME is the one a person reads and ID is what separates "
                         "'Arch Linux' from 'Fedora Linux 41' without parsing a sentence")


class TestTheSessionIsReadFromTheEnvironment(unittest.TestCase):
    """None for a key that is not set, which is the honest answer outside a graphical session."""

    REPORTED_AS = {"XDG_SESSION_TYPE": "type", "XDG_CURRENT_DESKTOP": "desktop",
                   "XDG_SESSION_DESKTOP": "session_desktop",
                   "HYPRLAND_INSTANCE_SIGNATURE": "compositor",
                   "WAYLAND_DISPLAY": "wayland_display", "GDK_BACKEND": "backend"}

    def test_nothing_is_invented_when_the_environment_is_bare(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            reported = system.session()
        for key, field in self.REPORTED_AS.items():
            with self.subTest(key=key):
                self.assertIsNone(reported[field],
                                  "a key that is not set was given a value, and in CI, over "
                                  "SSH or in a container that value describes nothing")

    def test_the_compositor_is_named_from_the_variable_only_it_sets(self):
        with mock.patch.dict(os.environ,
                             {"HYPRLAND_INSTANCE_SIGNATURE": "abc123"}, clear=True):
            self.assertEqual("hyprland", system.session()["compositor"])
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "Hyprland"}, clear=True):
            self.assertIsNone(system.session()["compositor"],
                              "the compositor was guessed from a desktop label that anything "
                              "can set, rather than from the variable the compositor itself "
                              "puts in every child it spawns")

    def test_the_hostname_falls_back_to_a_name_rather_than_an_empty_string(self):
        self.assertTrue(system.hostname())


class TestALoadIsADifferenceBetweenTwoReads(Fixture):
    """The kernel publishes cumulative counters, so one read is not a load."""

    FIRST = {"user": 100, "nice": 0, "system": 50, "idle": 800, "iowait": 50,
             "irq": 0, "softirq": 0, "steal": 0}
    SECOND = {"user": 200, "nice": 0, "system": 100, "idle": 1550, "iowait": 50,
              "irq": 0, "softirq": 0, "steal": 0}

    def test_busy_time_between_two_reads_is_a_percentage(self):
        """Totals 1000 then 1900, idle 850 then 1600: 150 busy jiffies out of 900."""
        self.assertAlmostEqual(16.67, system.cpu_percent(self.FIRST, self.SECOND), places=2)

    def test_two_identical_reads_are_none_and_not_a_division_by_zero(self):
        self.assertIsNone(system.cpu_percent(self.FIRST, dict(self.FIRST)))

    def test_one_missing_read_is_none_and_not_zero_percent(self):
        self.assertIsNone(system.cpu_percent(None, self.SECOND))
        self.assertIsNone(system.cpu_percent(self.FIRST, None))
        self.assertIsNone(system.cpu_percent({}, {}),
                          "a load nobody could measure came back as a number")

    def test_the_figure_is_clamped_to_a_percentage(self):
        """An idle counter that went backwards would give more than 100% busy."""
        earlier = {"user": 100, "nice": 0, "system": 0, "idle": 500, "iowait": 0,
                   "irq": 0, "softirq": 0, "steal": 0}
        later = {"user": 900, "nice": 0, "system": 0, "idle": 100, "iowait": 0,
                 "irq": 0, "softirq": 0, "steal": 0}
        self.assertEqual(100.0, system.cpu_percent(earlier, later),
                         "a figure above 100% would be drawn as a bar longer than its track")

    def test_a_total_that_went_backwards_is_none_because_counters_are_cumulative(self):
        earlier = {"user": 1000, "nice": 0, "system": 0, "idle": 0, "iowait": 0,
                   "irq": 0, "softirq": 0, "steal": 0}
        later = {"user": 0, "nice": 0, "system": 0, "idle": 100, "iowait": 0,
                 "irq": 0, "softirq": 0, "steal": 0}
        self.assertIsNone(system.cpu_percent(earlier, later),
                          "the kernel publishes cumulative counters, so a smaller total "
                          "means the two reads are not comparable and any percentage "
                          "computed from them describes nothing")

    def test_a_sample_waits_exactly_as_long_as_the_caller_asked(self):
        """`sleep` is a parameter so a page knows what its refresh costs."""
        waited: List[float] = []
        system.sample_cpu(0.25, self.proc, sleep=waited.append)
        self.assertEqual([0.25], waited,
                         "the sample waited for a different interval than the caller asked "
                         "for, so a page refreshing on a timer cannot budget its own cost")

    def test_a_sample_of_zero_seconds_still_answers_from_the_fixture(self):
        waited: List[float] = []
        percent = system.sample_cpu(0.0, self.proc, sleep=waited.append)
        self.assertEqual([0.0], waited)
        self.assertIsNone(percent, "two reads with no wait between them are the same read, "
                                   "and a load of 0% would be invented")

    def test_the_default_interval_is_recorded_once(self):
        self.assertEqual(0.25, system.CPU_SAMPLE_SECONDS)


class TestAFigureNobodyCouldReadIsASentence(unittest.TestCase):
    """The formatter is the last place a None could quietly become a zero."""

    def test_an_unavailable_uptime_says_so(self):
        self.assertEqual("uptime unavailable", system.format_uptime(None))

    def test_an_unavailable_memory_figure_says_so(self):
        self.assertEqual("memory unavailable", system.format_kib(None))

    def test_a_duration_is_days_and_a_clock(self):
        self.assertEqual("0:00", system.format_uptime(0))
        self.assertEqual("1:05", system.format_uptime(3900))
        self.assertEqual("1 day, 0:00", system.format_uptime(86400))
        self.assertEqual("3 days, 4:05", system.format_uptime(3 * 86400 + 4 * 3600 + 300))
        self.assertEqual("2 days, 0:09", system.format_uptime(2 * 86400 + 570),
                         "the minutes are not zero-padded, so a clock reads as two numbers")

    def test_a_size_climbs_the_units_and_stops_at_tebibytes(self):
        self.assertEqual("0 B", system.format_kib(0), "0 KiB is 0 bytes, and a size of "
                                                      "nothing is not the same sentence as "
                                                      "a size nobody could read")
        self.assertEqual("1.0 MiB", system.format_kib(1024))
        self.assertEqual("1.0 GiB", system.format_kib(1024 * 1024))
        self.assertEqual("7.8 GiB", system.format_kib(int(7.8 * 1024 * 1024)))
        self.assertIn("TiB", system.format_kib(1024 ** 4))

    def test_the_percentage_precision_is_recorded_once(self):
        self.assertEqual(2, system.PERCENT_DECIMALS)


class TestTheSnapshotIsOneReadPerFigure(Fixture):
    """Everything the Home page shows, and the CPU load only when it is asked for."""

    def test_the_snapshot_has_the_thirteen_keys_the_home_page_reads(self):
        shot = system.snapshot(self.proc, self.sys_root, self.etc)
        self.assertEqual(
            {"hostname", "distro", "kernel", "session", "uptime_seconds", "uptime",
             "load_average", "cpu_percent", "cpu_count", "memory", "batteries", "battery",
             "on_ac"}, set(shot))

    def test_every_figure_in_the_snapshot_came_from_the_fixture(self):
        shot = system.snapshot(self.proc, self.sys_root, self.etc)
        self.assertEqual("Arch Linux", shot["distro"]["name"])
        self.assertAlmostEqual(372266.41, shot["uptime_seconds"], places=2)
        self.assertEqual("4 days, 7:24", shot["uptime"])
        self.assertEqual((0.52, 0.58, 0.59), shot["load_average"])
        self.assertEqual(16306624, shot["memory"]["total_kib"])
        self.assertEqual(73, shot["battery"]["percent"])
        self.assertIs(True, shot["on_ac"])

    def test_a_cpu_load_is_computed_only_when_the_caller_accepts_the_wait(self):
        shot = system.snapshot(self.proc, self.sys_root, self.etc, cpu_seconds=0.0)
        self.assertIsNone(shot["cpu_percent"],
                          "the snapshot sampled the CPU without being asked, so every Home "
                          "page refresh now costs a quarter of a second")

    def test_a_snapshot_of_an_empty_machine_answers_none_everywhere(self):
        shot = system.snapshot(self.empty, self.empty, self.empty)
        self.assertIsNone(shot["uptime_seconds"])
        self.assertEqual("uptime unavailable", shot["uptime"])
        self.assertIsNone(shot["load_average"])
        self.assertIsNone(shot["cpu_percent"])
        self.assertEqual([], shot["batteries"])
        self.assertIsNone(shot["battery"])
        self.assertIsNone(shot["on_ac"])
        self.assertIsNone(shot["memory"]["used_percent"])
        self.assertIsNone(shot["distro"]["name"])
        self.assertTrue(shot["hostname"], "the hostname is the one figure that always has an "
                                          "answer, because uname(2) always has one")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
