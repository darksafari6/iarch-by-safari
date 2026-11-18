#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""theme_engine — the two shell engines as data, and the read-only probes over them.

Purpose
    One decision (D-T1-01 in docs/DECISIONS.md) says this session has two shell
    engines and that exactly one of them runs. Everything that has to agree with
    that decision — ``iarch-shell-switch``, ``iarch-theme``, ``iarch-doctor shell``
    and, in a later part, the settings toggle and the installer — reads the engines
    from here instead of spelling a binary name of its own. This module changes
    nothing: it names the engines and answers questions about what is running.

Inputs
    Nothing from disk at import time. The probes take an injectable runner and, for
    paths, an environment mapping (``HOME``, ``XDG_CONFIG_HOME``).

Outputs
    ``Engine`` records, lookups by id and by pack ``engine`` value, the process
    scans that say which engines are running, the instance list the dynamic engine
    can be asked for, and the sentences that describe a violation of the
    one-shell rule.

Dependencies
    ``iarch.lib.configstore`` (paths), ``iarch.lib.processes`` (process table),
    ``iarch.lib.dbus_probe`` (notification-server owner), ``iarch.lib.runner``.

Every command named here is cited where it is used, and the full table — including
what was read out of Quickshell ``master`` (tag ``v0.3.2``)
``src/launch/parsecommand.cpp`` for ``--config``, ``--daemonize``,
``--no-duplicate``, ``kill``, ``list --json`` and ``ipc call`` — is in
docs/THEMES-ARCHITECTURE.md, "What the second engine is built on". The classic
engine's start command is the ``noctalia`` entry of ``data/design/startup.json``
(``exec_once``), which records its own reason beside it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from iarch.lib import configstore, dbus_probe, processes, runner

# --- the two engines ------------------------------------------------------

ENGINE_CLASSIC = "classic"
ENGINE_DYNAMIC = "dynamic"

#: The value a theme pack carries in its ``engine`` field. ``ishell`` names the
#: renderer a pack is written for; ``dynamic`` names the running engine. One table
#: maps the two and D-T1-03 forbids a second translation anywhere else.
PACK_ENGINE_CLASSIC = "classic"
PACK_ENGINE_ISHELL = "ishell"
PACK_ENGINE_TO_ENGINE: Dict[str, str] = {
    PACK_ENGINE_CLASSIC: ENGINE_CLASSIC,
    PACK_ENGINE_ISHELL: ENGINE_DYNAMIC,
}
ENGINE_TO_PACK_ENGINE: Dict[str, str] = {
    value: key for key, value in PACK_ENGINE_TO_ENGINE.items()
}

#: Classic stays the default until the dynamic engine passes the M5 QA gate
#: (docs/THEMES-MILESTONES.md): an install with no recorded choice runs the engine
#: this repository has verified end to end.
DEFAULT_ENGINE_ID = ENGINE_CLASSIC

#: The whole round trip — stop the old engine, start the new one, prove it is up —
#: has to finish inside this budget or the switch rolls back. Ten seconds is also
#: the window Quickshell's own crash handler uses before it refuses to restart
#: ("crashed within 10 seconds of launching. Not restarting to avoid a crash
#: loop.", ``src/launch/main.cpp``): a shell that cannot come up in ten seconds is
#: one its own toolkit would not retry either.
SWITCH_BUDGET_SECONDS = 10.0

#: The configuration name the dynamic engine's QML lives under, which makes its entry
#: point ``~/.config/quickshell/iarch/shell.qml`` (D-T1-11).
QUICKSHELL_CONFIG_NAME = "iarch"
QUICKSHELL_BIN = "quickshell"
CLASSIC_BIN = "noctalia"

#: IPC target the dynamic shell registers for theme hot-swap, and the two
#: functions this project calls on it. TODO(verify) ENG-03.
IPC_TARGET_THEME = "iarch.theme"
IPC_FUNCTION_APPLY = "apply"
IPC_FUNCTION_PING = "ping"

ENGINE_RECORD_NAME = "shell-engine.json"   #: the selected engine's record
SWITCH_RECORD_NAME = "shell-switch.json"   #: the snapshot a rollback restores


@dataclass(frozen=True)
class Engine:
    """One shell engine: what runs it, how it is stopped, and where it reads."""

    id: str
    name: str
    group: str
    pack_engine: str
    binary: str
    start_command: Tuple[str, ...]
    stop_command: Optional[Tuple[str, ...]]
    instances_command: Optional[Tuple[str, ...]]
    config_root: Optional[str]
    entry_file: Optional[str]
    provides_notification_server: bool
    status: str
    provenance: str

    @property
    def stops_by_signal(self) -> bool:
        """True when there is no verified command to ask this engine to exit."""
        return self.stop_command is None


ENGINES: Tuple[Engine, ...] = (
    Engine(
        id=ENGINE_CLASSIC,
        name="Classic",
        group="classic",
        pack_engine=PACK_ENGINE_CLASSIC,
        binary=CLASSIC_BIN,
        start_command=(CLASSIC_BIN,),
        # No verified way to ask this engine to exit: the 66 verbs in
        # data/design/noctalia-ipc.json include no quit, and `session logout` ends
        # the session rather than the shell. TODO(verify) ENG-06: the switch
        # signals the pid it found instead.
        stop_command=None,
        instances_command=None,
        config_root=".config/noctalia",
        entry_file=None,  # not a file this project writes, so no preflight looks for one
        provides_notification_server=True,
        status="shipped",
        provenance="data/design/startup.json exec_once: noctalia",
    ),
    Engine(
        id=ENGINE_DYNAMIC,
        name="iArch Shell",
        group="dynamic",
        pack_engine=PACK_ENGINE_ISHELL,
        binary=QUICKSHELL_BIN,
        start_command=(QUICKSHELL_BIN, "--config", QUICKSHELL_CONFIG_NAME,
                       "--daemonize", "--no-duplicate"),
        stop_command=(QUICKSHELL_BIN, "kill", "--config", QUICKSHELL_CONFIG_NAME),
        instances_command=(QUICKSHELL_BIN, "list", "--json", "--config",
                           QUICKSHELL_CONFIG_NAME),
        config_root=f".config/quickshell/{QUICKSHELL_CONFIG_NAME}",
        # Quickshell discovers <xdg config dir>/quickshell/<name>/shell.qml
        # (src/launch/command.cpp, locateNamedConfig).
        entry_file="shell.qml",
        provides_notification_server=True,
        status="planned",
        provenance="Quickshell master (v0.3.2) src/launch/parsecommand.cpp",
    ),
)


def engine_ids() -> Tuple[str, ...]:
    return tuple(record.id for record in ENGINES)  # every id, in catalogue order


def engine_names() -> Dict[str, str]:
    """Engine id to the name a person sees; never the upstream project's name."""
    return {record.id: record.name for record in ENGINES}


def engine(engine_id: str) -> Optional[Engine]:
    return next((candidate for candidate in ENGINES if candidate.id == engine_id), None)


def by_pack_engine(pack_value: str) -> Optional[Engine]:
    """The engine a pack's ``engine`` field selects."""
    return engine(PACK_ENGINE_TO_ENGINE.get(pack_value, ""))


def default_engine() -> Engine:
    return engine(DEFAULT_ENGINE_ID) or ENGINES[0]


def other_engine(engine_id: str) -> Optional[Engine]:
    """The engine that must not be running while ``engine_id`` is, else ``None``.

    ``None`` for an unknown id: guessing which engine somebody meant is how a switch
    stops the shell a person is looking at.
    """
    if engine(engine_id) is None:
        return None
    return next(candidate for candidate in ENGINES if candidate.id != engine_id)


# --- paths -----------------------------------------------------------------


def config_dir_for(engine_id: str, env: Optional[Mapping[str, str]] = None) -> Optional[Any]:
    """Where an engine reads its own configuration, or ``None`` if it has none."""
    record = engine(engine_id)
    if record is None or record.config_root is None:
        return None
    home = configstore.home_dir(env)
    return home / record.config_root


def shell_entry(engine_id: str, env: Optional[Mapping[str, str]] = None) -> Optional[Any]:
    """The QML entry point an engine reads, or ``None`` if it declares none."""
    record = engine(engine_id)
    directory = config_dir_for(engine_id, env)
    if record is None or record.entry_file is None or directory is None:
        return None
    return directory / record.entry_file


def engine_record_path(env: Optional[Mapping[str, str]] = None) -> Any:
    """``~/.config/iarch/shell-engine.json`` — the selected engine."""
    return configstore.config_dir(env) / ENGINE_RECORD_NAME


def switch_record_path(env: Optional[Mapping[str, str]] = None) -> Any:
    """``~/.local/state/iarch/shell-switch.json`` — the snapshot a rollback restores."""
    return configstore.state_dir(env) / SWITCH_RECORD_NAME


# --- read-only probes ------------------------------------------------------


def running(record: Engine, run: Optional[runner.Runner] = None) -> processes.ProcessScan:
    """The pids of one engine, from the process table."""
    return processes.pids_named(record.binary, run=run)


def engines_running(run: Optional[runner.Runner] = None) -> Dict[str, Any]:
    """Every engine's scan as a dict, keyed by engine id."""
    return {record.id: running(record, run=run).as_dict() for record in ENGINES}


def instances(record: Engine, run: Optional[runner.Runner] = None) -> Tuple[Optional[List[Any]], Optional[runner.Answer]]:
    """What an engine says about its own instances, when it can be asked.

    Only the dynamic engine has a verified query (``quickshell list --json``); for
    the classic one this is ``(None, None)`` and the caller falls back to the process
    table, which is a weaker answer and is reported as one.
    """
    if record.instances_command is None:
        return None, None
    execute = run or runner.run
    answer = execute(record.instances_command, processes.PGREP_TIMEOUT_SECONDS)
    if answer is None:
        return None, None
    parsed = answer.as_json()
    if parsed is None:
        return None, answer
    return parsed if isinstance(parsed, list) else [parsed], answer


def ipc_call(target: str, function: str, arguments: Sequence[str] = (),
             run: Optional[runner.Runner] = None) -> Optional[runner.Answer]:
    """Call an ``IpcHandler`` function in the running dynamic shell.

    TODO(verify) ENG-03: ``quickshell ipc call`` was read out of
    ``src/launch/parsecommand.cpp`` and never run here, so ``None`` means "the shell
    could not be asked" and never "the shell agreed".
    """
    record = engine(ENGINE_DYNAMIC)
    if record is None:
        return None
    execute = run or runner.run
    command: Tuple[str, ...] = (
        record.binary, "ipc", "call", "--config", QUICKSHELL_CONFIG_NAME,
        target, function, *tuple(arguments),
    )
    return execute(command, processes.PGREP_TIMEOUT_SECONDS)


def notification_owner(run: Optional[runner.Runner] = None) -> Dict[str, Any]:
    """Who holds ``org.freedesktop.Notifications``, and which engine that is."""
    owner = dbus_probe.notification_server(run=run)
    report = owner.as_dict()
    report["engine"] = None
    if owner.pid is not None:
        for record in ENGINES:
            scan = running(record, run=run)
            if owner.pid in scan.pids:
                report["engine"] = record.id
                break
    return report


def one_shell_violations(scans: Mapping[str, processes.ProcessScan]) -> List[str]:
    """Sentences describing every way the one-shell rule is currently broken."""
    found: List[str] = []
    alive = [r for r in ENGINES if scans.get(r.id) is not None and scans[r.id].running]
    if len(alive) > 1:
        found.append("more than one shell engine is running: " + ", ".join(
            f"{r.name} (pid {', '.join(str(p) for p in scans[r.id].pids)})" for r in alive))
    for record in ENGINES:
        scan = scans.get(record.id)
        if scan is not None and not scan.searched and scan.note:
            found.append(f"whether {record.name} is running could not be checked: {scan.note}")
    return found


def scans(run: Optional[runner.Runner] = None) -> Dict[str, processes.ProcessScan]:
    """One process scan per engine, as a mapping keyed by engine id."""
    return {record.id: running(record, run=run) for record in ENGINES}
