#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""engine_state — what the session says about its shell engine, and what is really running.

Purpose
    Two records and one probe. ``~/.local/state/iarch/engine.json`` is the engine
    the user selected; ``~/.local/state/iarch/shell-switch.json`` is the snapshot a
    rollback restores; the process table is the only authority on what is actually
    running. Keeping the three in one module is what stops a caller from reading
    the record and calling it the truth.

Inputs
    An environment mapping (``HOME``, ``XDG_CONFIG_HOME``, ``IARCH_CONFIG_DIR``,
    ``IARCH_STATE_DIR``) and an injectable runner for the probes.

Outputs
    ``engine_record()`` and ``switch_record()`` as dicts, the paths they came from,
    and ``state()`` — one report holding both engines' scans, the record, the
    notification-server owner and every way the one-shell rule is currently broken.

Dependencies
    ``iarch.cli.theme_engine`` for the catalogue and the record paths,
    ``iarch.lib.configstore`` for atomic writes, ``iarch.lib.runner`` for commands.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from iarch.cli import theme_engine as engines
from iarch.lib import configstore, runner

SCHEMA_VERSION = 1


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    """A JSON object from disk, or ``None`` when it is absent, unreadable or not one."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write and persist an atomic engine or handoff record before proceeding."""
    configstore.atomic_write(Path(path), json.dumps(dict(payload), indent=2) + "\n",
                             validate_json=True, durable=True)
    return Path(path)


def timestamp() -> str:
    """UTC, to the second: the format every other record in this project uses."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def engine_record(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """The selected engine, defaulting to the one an install starts with.

    ``stored`` says whether the file named a known engine. A record that is absent,
    unreadable or names something this build does not know is reported as the
    repository default rather than as an error, because an install that has never
    switched is the normal case.
    """
    path = engines.engine_record_path(env)
    legacy = engines.legacy_engine_record_path(env)
    # Read the old location only until the new authoritative file exists. Never
    # overwrite or delete the old record as a side effect of this read.
    source = legacy if not path.exists() and not path.is_symlink() else path
    stored = {} if source.is_symlink() else (read_json(source) or {})
    engine_id = stored.get("engine")
    version = stored.get("schema_version", SCHEMA_VERSION)
    known = engine_id in engines.engine_ids() and type(version) is int and version == SCHEMA_VERSION
    return {"schema_version": version if type(version) is int else SCHEMA_VERSION,
            "engine": engine_id if known else engines.DEFAULT_ENGINE_ID,
            "switched_at": stored.get("switched_at"),
            "previous": stored.get("previous"),
            "path": str(path), "stored": known}


def dynamic_engine_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Explicit opt-in; absence, malformed data and symlinks all fail closed."""
    path = configstore.config_dir(env) / 'dynamic-engine.json'
    if path.is_symlink():
        return False
    payload = read_json(path)
    return (isinstance(payload, dict) and set(payload) == {'dynamic_engine_enabled'}
            and payload['dynamic_engine_enabled'] is True)


def write_engine_record(engine_id: str, previous: Optional[str],
                        when: Optional[str] = None,
                        env: Optional[Mapping[str, str]] = None) -> Path:
    """Record the selected engine, keeping the one it replaced beside it."""
    if engines.engine(engine_id) is None:
        raise ValueError(f"unknown engine id: {engine_id!r}")
    target = engines.engine_record_path(env)
    if target.is_symlink():
        raise ValueError('refusing a symlink engine record')
    if target.exists():
        if not target.is_file():
            raise ValueError('engine record must be a regular file')
        configstore.backup_of(target, env)
    return write_json(target,
                      {"schema_version": SCHEMA_VERSION, "engine": engine_id,
                       "switched_at": when or timestamp(), "previous": previous})


def switch_record(env: Optional[Mapping[str, str]] = None) -> Optional[Dict[str, Any]]:
    """The snapshot of the switch in flight, or ``None`` when there is none."""
    return read_json(engines.switch_record_path(env))


def write_switch_snapshot(previous_engine: str, previous_pids: List[int],
                          previous_record: Mapping[str, Any], budget: float,
                          env: Optional[Mapping[str, str]] = None) -> Path:
    """Snapshot what is running before anything is stopped."""
    return write_json(engines.switch_record_path(env),
                      {"schema_version": SCHEMA_VERSION, "previous_engine": previous_engine,
                       "previous_pids": list(previous_pids),
                       "previous_record": dict(previous_record),
                       "taken_at": timestamp(), "budget_seconds": budget})


def state(env: Optional[Mapping[str, str]] = None,
          run: Optional[runner.Runner] = None) -> Dict[str, Any]:
    """Everything a report needs about the session's shell, in one read."""
    scans = engines.scans(run=run)
    return {
        "engines": {key: scan.as_dict() for key, scan in scans.items()},
        "violations": engines.one_shell_violations(scans),
        "record": engine_record(env),
        "notification": engines.notification_owner(run=run),
    }


def running_ids(before: Mapping[str, Any]) -> List[str]:
    """The engine ids the process table says are running, in catalogue order."""
    return [record.id for record in engines.ENGINES
            if before["engines"].get(record.id, {}).get("pids")]


def selected_id(env: Optional[Mapping[str, str]] = None) -> str:
    """The engine the record selects, which is what a login would start."""
    return engine_record(env)["engine"]
