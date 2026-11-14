# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""What this machine is, read out of the kernel's own files.

The Home page shows a hostname, a distribution, a kernel, an uptime, a battery, a
CPU load and a memory figure. Every one of those is a file the kernel already
publishes, so this module reads files and runs no command at all: no ``uname``, no
``lsb_release``, no ``upower``, no shell. That is not a style preference. A command
needs a binary that may not be installed, may print a different sentence on Arch
than on Fedora, and cannot be tested without a machine; a file under ``/proc`` or
``/sys`` has one format and can be tested by pointing this module at a directory
of fixtures, which is what ``tests/test_settings_system.py`` does.

Every reader takes an optional ``root`` so exactly that is possible. The defaults
are the real ones.

A value that cannot be read comes back as ``None``, never as a zero and never as
an invented string. A desktop with no battery has no battery row; a container with
no ``/proc/meminfo`` says the figure is unavailable. Both are true statements, and
guessing either would put a number on screen that describes nothing.
"""
from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROC = Path("/proc")
SYS = Path("/sys")
ETC = Path("/etc")

#: The os-release keys this module reports. ``PRETTY_NAME`` is the one a human
#: reads; the others are what make "Arch Linux" and "Fedora Linux 41" separable
#: without parsing a sentence.
OS_RELEASE_KEYS = ("NAME", "VERSION", "VERSION_ID", "ID", "ID_LIKE", "PRETTY_NAME")

#: How long a CPU sample waits between its two reads of /proc/stat, in seconds.
CPU_SAMPLE_SECONDS = 0.25

#: A memory or CPU figure is a percentage; two decimals is more precision than a
#: bar can show and less than a rounding argument.
PERCENT_DECIMALS = 2


class SystemError(RuntimeError):
    """A reader was asked for something the kernel does not publish."""


def _read(path: Path) -> Optional[str]:
    """The text of ``path``, or ``None``. A missing file is not an exception."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_first_field(path: Path) -> Optional[str]:
    text = _read(path)
    if text is None:
        return None
    fields = text.split()
    return fields[0] if fields else None


def _int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _percent(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    if part is None or whole is None or whole <= 0:
        return None
    return round(part / whole * 100.0, PERCENT_DECIMALS)


# ------------------------------------------------------------------ identity


def hostname() -> str:
    """This machine's name. ``socket.gethostname`` reads what uname(2) reports."""
    try:
        return socket.gethostname() or "localhost"
    except OSError:
        return "localhost"


def os_release(root: Path = ETC) -> Dict[str, str]:
    """``/etc/os-release`` as a dictionary, with the quotes removed.

    The file is shell syntax, but every value this module needs is either a bare
    word or a double-quoted one, so it is parsed as such rather than sourced: a
    settings panel that runs ``. /etc/os-release`` in a shell to read a label is a
    settings panel that executed a file it did not write.
    """
    text = _read(root / "os-release")
    if text is None:
        text = _read(root / "usr" / "lib" / "os-release")
    values: Dict[str, str] = {}
    if text is None:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def distro(root: Path = ETC) -> Dict[str, Optional[str]]:
    """The distribution, as the fields the Home page shows."""
    release = os_release(root)
    return {
        "name": release.get("PRETTY_NAME") or release.get("NAME"),
        "id": release.get("ID"),
        "like": release.get("ID_LIKE"),
        "version": release.get("VERSION"),
        "version_id": release.get("VERSION_ID"),
    }


def kernel() -> Dict[str, str]:
    """The kernel, from ``os.uname()`` -- a syscall, not the ``uname`` binary."""
    info = os.uname()
    return {"sysname": info.sysname, "release": info.release,
            "machine": info.machine, "node": info.nodename}


def session() -> Dict[str, Optional[str]]:
    """What kind of session this is, from the environment.

    ``None`` for a key that is not set, which is the honest answer outside a
    graphical session -- in CI, over SSH, or in a container.
    """
    return {
        "type": os.environ.get("XDG_SESSION_TYPE"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "session_desktop": os.environ.get("XDG_SESSION_DESKTOP"),
        # The compositor is named from the environment variable it sets rather than
        # from a guess: HYPRLAND_INSTANCE_SIGNATURE is present in every child the
        # compositor spawns and in nothing else.
        "compositor": ("hyprland" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else None),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "backend": os.environ.get("GDK_BACKEND"),
    }


# ------------------------------------------------------------------ figures


def uptime_seconds(proc: Path = PROC) -> Optional[float]:
    """Seconds since boot, or ``None``. ``/proc/uptime`` field one."""
    text = _read(proc / "uptime")
    if text is None:
        return None
    fields = text.split()
    if not fields:
        return None
    try:
        return float(fields[0])
    except ValueError:
        return None


def format_uptime(seconds: Optional[float]) -> str:
    """``3 days, 4:05`` -- a duration a person reads at a glance.

    ``None`` becomes a sentence rather than a zero, because an uptime of nothing
    would be a claim about a machine this module could not read.
    """
    if seconds is None:
        return "uptime unavailable"
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    clock = f"{hours}:{minutes:02d}"
    if days == 1:
        return f"1 day, {clock}"
    if days:
        return f"{days} days, {clock}"
    return clock


def load_average(proc: Path = PROC) -> Optional[Tuple[float, float, float]]:
    """The three load averages, or ``None``. ``/proc/loadavg``."""
    text = _read(proc / "loadavg")
    if text is None:
        return None
    fields = text.split()
    if len(fields) < 3:
        return None
    try:
        return (float(fields[0]), float(fields[1]), float(fields[2]))
    except ValueError:
        return None


def cpu_times(proc: Path = PROC) -> Optional[Dict[str, int]]:
    """The first line of ``/proc/stat``, as jiffies per state.

    ``user nice system idle iowait irq softirq steal`` -- the kernel publishes
    cumulative counters, so a load is the difference between two reads and never a
    single one. That is why this returns the counters and :func:`cpu_percent` takes
    two of them.
    """
    text = _read(proc / "stat")
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("cpu "):
            fields = line.split()[1:]
            names = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
            values: Dict[str, int] = {}
            for name, field in zip(names, fields):
                number = _int(field)
                if number is None:
                    return None
                values[name] = number
            return values
    return None


def cpu_percent(first: Optional[Dict[str, int]], second: Optional[Dict[str, int]]) -> Optional[float]:
    """Busy time between two :func:`cpu_times` reads, as a percentage.

    ``idle`` plus ``iowait`` is the time the CPU had nothing to do; everything else
    is work. Two identical reads give ``None`` rather than a division by zero, and
    so does a single missing read, because a load of 0% and a load nobody could
    measure are different sentences.
    """
    if not first or not second:
        return None
    total_before = sum(first.values())
    total_after = sum(second.values())
    idle_before = first.get("idle", 0) + first.get("iowait", 0)
    idle_after = second.get("idle", 0) + second.get("iowait", 0)
    total_delta = total_after - total_before
    idle_delta = idle_after - idle_before
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (total_delta - idle_delta) / total_delta * 100.0)),
                 PERCENT_DECIMALS)


def cpu_count() -> Optional[int]:
    """Logical CPUs, or ``None``."""
    try:
        return os.cpu_count() or None
    except (NotImplementedError, ValueError):
        return None


def sample_cpu(seconds: float = CPU_SAMPLE_SECONDS, proc: Path = PROC,
               sleep: Callable[[float], None] = time.sleep) -> Optional[float]:
    """Two reads of ``/proc/stat`` with a wait between them.

    ``sleep`` is a parameter so a test can pass a no-op and assert on the
    arithmetic instead of waiting, and so a page can be told exactly how long its
    refresh costs.
    """
    first = cpu_times(proc)
    sleep(seconds)
    return cpu_percent(first, cpu_times(proc))


def memory(proc: Path = PROC) -> Dict[str, Optional[Any]]:
    """Memory in kibibytes, plus the used percentage the Home page draws.

    ``MemAvailable`` is what the kernel says could be given to a new process
    without swapping, which is not ``MemFree`` and is the number a person means by
    "how much is left". Both are reported because a page that showed only one
    would be either wrong or unexplainable.
    """
    text = _read(proc / "meminfo")
    values: Dict[str, Optional[int]] = {"total": None, "available": None, "free": None}
    if text is not None:
        wanted = {"MemTotal": "total", "MemAvailable": "available", "MemFree": "free"}
        for line in text.splitlines():
            key, _, rest = line.partition(":")
            key = key.strip()
            if key in wanted:
                fields = rest.split()
                values[wanted[key]] = _int(fields[0]) if fields else None
    total = values["total"]
    available = values["available"]
    used = None if total is None or available is None else total - available
    return {
        "total_kib": total,
        "available_kib": available,
        "free_kib": values["free"],
        "used_kib": used,
        "used_percent": _percent(float(used) if used is not None else None,
                                 float(total) if total is not None else None),
    }


def format_kib(kib: Optional[int]) -> str:
    """``7.8 GiB``. ``None`` becomes a sentence, not a zero."""
    if kib is None:
        return "memory unavailable"
    value = float(kib) * 1024.0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} TiB"


# ------------------------------------------------------------------ battery


def battery_paths(sys_root: Path = SYS) -> List[Path]:
    """Every ``BAT*`` power supply, sorted so a two-battery machine is stable."""
    supply = sys_root / "class" / "power_supply"
    try:
        return sorted(path for path in supply.iterdir() if path.name.startswith("BAT"))
    except OSError:
        return []


def batteries(sys_root: Path = SYS) -> List[Dict[str, Any]]:
    """One entry per battery, with the fields the Home page shows.

    A desktop with no battery gives an empty list, which is why the caller hides
    the row rather than showing 0%: 0% and "this machine has no battery" are
    opposite statements and only one of them is true here.
    """
    found: List[Dict[str, Any]] = []
    for path in battery_paths(sys_root):
        capacity = _int(_read_first_field(path / "capacity"))
        status = (_read_first_field(path / "status") or "").strip() or None
        found.append({
            "name": path.name,
            "percent": capacity,
            "status": status,
            "charging": status == "Charging",
            "plugged_in": status in ("Charging", "Full", "Not charging"),
        })
    return found


def primary_battery(sys_root: Path = SYS) -> Optional[Dict[str, Any]]:
    """The first battery, or ``None`` when the machine has none."""
    found = batteries(sys_root)
    return found[0] if found else None


def power_on_ac(sys_root: Path = SYS) -> Optional[bool]:
    """Whether the machine is on mains power.

    Read from an ``AC*`` or ``ACAD`` supply's ``online`` file, which is what a
    laptop publishes; ``None`` when there is no such supply, which is the case on a
    desktop and in a container, and is not the same as "on battery".
    """
    supply = sys_root / "class" / "power_supply"
    try:
        candidates = sorted(path for path in supply.iterdir()
                            if path.name.startswith("AC"))
    except OSError:
        return None
    for path in candidates:
        online = _int(_read_first_field(path / "online"))
        if online is not None:
            return bool(online)
    return None


# ------------------------------------------------------------------ a snapshot


def snapshot(proc: Path = PROC, sys_root: Path = SYS, etc: Path = ETC,
             cpu_seconds: float = 0.0) -> Dict[str, Any]:
    """Everything the Home page shows, in one dictionary.

    ``cpu_seconds`` defaults to zero, which means the CPU load is only computed
    when a caller asks for a sample and accepts the wait; a page refreshing on a
    timer passes its own interval and pays for it knowingly. Everything else is one
    read of one file.
    """
    load = load_average(proc)
    cpu = sample_cpu(cpu_seconds, proc) if cpu_seconds > 0 else None
    return {
        "hostname": hostname(),
        "distro": distro(etc),
        "kernel": kernel(),
        "session": session(),
        "uptime_seconds": uptime_seconds(proc),
        "uptime": format_uptime(uptime_seconds(proc)),
        "load_average": load,
        "cpu_percent": cpu,
        "cpu_count": cpu_count(),
        "memory": memory(proc),
        "batteries": batteries(sys_root),
        "battery": primary_battery(sys_root),
        "on_ac": power_on_ac(sys_root),
    }
