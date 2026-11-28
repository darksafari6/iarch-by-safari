# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Journalled notification handoff with injectable process and bus adapters.

Inputs: two engine ids, process and owner adapters, an iArch environment, and
clock/sleep. Outputs: a durable switch state and a verified result or an error
with recovery details. No notification history is transferred by this module.
"""
import time
from dataclasses import dataclass

from iarch.cli import engine_state, engine_steps, theme_engine
from iarch.lib import dbus_probe, processes, session_lock

RELEASE_SECONDS = 5.0
CLAIM_SECONDS = 10.0
INTERVAL_SECONDS = 0.25
TERMINAL = frozenset(('IDLE', 'VERIFIED', 'RESTORED', 'FAILED_SAFE'))


class HandoffError(RuntimeError):
    """A switch failed; inspect the attached durable state for recovery."""

    def __init__(self, message, state):
        super().__init__(message)
        self.state = dict(state)


@dataclass(frozen=True)
class Owner:
    known: bool
    pid: int | None = None
    unique_name: str | None = None


class NameOwnerProbe:
    """Read the notification owner without taking or releasing its bus name."""
    def __init__(self, run=None):
        self.run = run

    def get(self):
        owner = dbus_probe.notification_server(run=self.run)
        return Owner(owner.searched and (not owner.owned or owner.pid is not None),
                     owner.pid, owner.unique_name)


class ProcessControl:
    """Use configuration-scoped process scans and the existing shell helpers."""
    def __init__(self, run=None, spawn=None, clock=None, sleep=None, env=None):
        self.run, self.spawn, self.env = run, spawn, env
        self.clock, self.sleep = clock or time.monotonic, sleep or time.sleep

    def pids(self, name):
        scan = theme_engine.running(theme_engine.engine(name), run=self.run)
        if not scan.searched:
            raise RuntimeError('cannot identify shell processes: ' + str(scan.note))
        return list(scan.pids)

    def stop(self, name):
        record = theme_engine.engine(name)
        result = engine_steps.stop(record, self.pids(name), run=self.run,
                                   clock=self.clock, sleep=self.sleep)
        return result['stopped'] and not self.pids(name)

    def start(self, name):
        # Recovery must never bypass the same opt-in and readiness preflight.
        from iarch.cli import shell_switch
        record = theme_engine.engine(name)
        missing = shell_switch._preflight(record, self.env)
        if missing:
            raise RuntimeError(f'{record.name} cannot start: {missing}')
        return engine_steps.start(record, spawn=self.spawn)['started']


def _write(env, state, phase):
    state['phase'] = phase
    history = state.setdefault('history', [])
    if not history or history[-1] != phase:
        history.append(phase)
    engine_state.write_json(theme_engine.switch_record_path(env), state)


def _wait(probe, accept, seconds, clock, sleep):
    deadline = clock() + seconds
    while True:
        owner = probe.get()
        if not owner.known:
            raise RuntimeError('notification owner cannot be determined')
        if accept(owner):
            return owner
        if clock() >= deadline:
            raise RuntimeError('notification ownership timed out')
        sleep(min(INTERVAL_SECONDS, max(0.0, deadline - clock())))


def _empty(owner):
    return owner.unique_name is None and owner.pid is None


def _claimed(control, name, owner):
    return owner.unique_name is not None and owner.pid in control.pids(name)


def _restore(state, env, probe, control, clock, sleep):
    old, new = state['previous_engine'], state['target_engine']
    _write(env, state, 'ROLLING_BACK')
    owner = probe.get()
    if not owner.known:
        raise RuntimeError('notification owner cannot be determined during recovery')
    old_pids, new_pids = control.pids(old), control.pids(new)
    if owner.unique_name and owner.pid not in old_pids + new_pids:
        raise RuntimeError('another process owns notifications; refusing to terminate it')
    if new_pids and not control.stop(new):
        raise RuntimeError('target engine could not be stopped during recovery')
    if not old_pids:
        _wait(probe, _empty, RELEASE_SECONDS, clock, sleep)
        if not control.start(old):
            raise RuntimeError('previous engine could not be restarted')
    _wait(probe, lambda owner: _claimed(control, old, owner), CLAIM_SECONDS, clock, sleep)
    if control.pids(new) or len(control.pids(old)) != 1:
        raise RuntimeError('recovery did not produce exactly one previous engine')
    engine_state.write_engine_record(old, state.get('previous_record', {}).get('previous'), env=env)
    _write(env, state, 'RESTORED')


def handoff(old, new, *, env=None, probe=None, control=None, clock=None, sleep=None,
            claim_seconds=CLAIM_SECONDS):
    """Stop old, wait for release, start new, and verify ownership or recover.

    The caller must perform target preflight and feature gating first. All probes
    are observations, not a guarantee against independently launched daemons.
    """
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    probe = probe or NameOwnerProbe()
    control = control or ProcessControl(clock=clock, sleep=sleep, env=env)
    if old == new or not theme_engine.engine(old) or not theme_engine.engine(new):
        raise ValueError('handoff needs two distinct known engines')
    with session_lock.session_lock(env):
        journal = theme_engine.switch_record_path(env)
        prior = engine_state.switch_record(env)
        if journal.is_symlink() or (journal.exists() and prior is None):
            raise HandoffError('switch journal is unreadable or unsafe; no changes made', {})
        if prior and prior.get('schema_version') == 2 and prior.get('phase') not in TERMINAL:
            raise HandoffError('unfinished switch; run iarch-shell-switch recover', prior)
        if prior and prior.get('schema_version') not in (1, 2):
            raise HandoffError('unrecognized switch journal', prior)
        old_pids, new_pids = control.pids(old), control.pids(new)
        owner = probe.get()
        if len(old_pids) != 1 or new_pids or not owner.known or not _claimed(control, old, owner):
            raise HandoffError('expected one old engine owning notifications; nothing changed', {})
        state = {'schema_version': 2, 'phase': 'IDLE', 'previous_engine': old,
                 'target_engine': new, 'previous_pids': old_pids,
                 'previous_record': engine_state.engine_record(env)}
        _write(env, state, 'IDLE')
        try:
            _write(env, state, 'STOPPING_OLD')
            if not control.stop(old):
                raise RuntimeError('previous engine did not stop')
            _write(env, state, 'WAITING_RELEASE')
            _wait(probe, _empty, RELEASE_SECONDS, clock, sleep)
            _write(env, state, 'STARTING_NEW')
            if not control.start(new):
                raise RuntimeError('target engine did not start')
            _write(env, state, 'WAITING_CLAIM')
            _wait(probe, lambda owner: _claimed(control, new, owner), claim_seconds, clock, sleep)
            if len(control.pids(new)) != 1 or control.pids(old):
                raise RuntimeError('expected exactly one target engine')
            engine_state.write_engine_record(new, old, env=env)
            _write(env, state, 'VERIFIED')
            return dict(state)
        except Exception as exc:
            try:
                _restore(state, env, probe, control, clock, sleep)
                _write(env, state, 'FAILED_SAFE')
            except Exception as recovery:
                state['recovery_error'] = str(recovery)
                _write(env, state, 'ROLLING_BACK')
            raise HandoffError(str(exc), state) from exc


def recover(*, env=None, probe=None, control=None, clock=None, sleep=None):
    """Restore the prior engine recorded in an interrupted handoff."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    probe = probe or NameOwnerProbe()
    control = control or ProcessControl(clock=clock, sleep=sleep, env=env)
    with session_lock.session_lock(env):
        state = engine_state.switch_record(env)
        if not state or state.get('schema_version') != 2:
            raise HandoffError('no recoverable handoff journal', state or {})
        if state.get('phase') in TERMINAL:
            return state
        old, new = state.get('previous_engine'), state.get('target_engine')
        if not theme_engine.engine(old) or not theme_engine.engine(new) or old == new:
            raise HandoffError('invalid handoff journal', state)
        try:
            _restore(state, env, probe, control, clock, sleep)
        except Exception as exc:
            state['recovery_error'] = str(exc)
            _write(env, state, 'ROLLING_BACK')
            raise HandoffError(str(exc), state) from exc
        return dict(state)
