# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Transactional dynamic-theme writes, with verified shell and compositor reloads.

Rendering is injected: callers must prepare the entire set of output actions
before this transaction begins. A missing IPC/compositor response is a failure,
not an implicit success. The transaction does not launch a shell.
"""
import os
from pathlib import Path

from iarch.cli import session_theme, theme_engine, theme_records
from iarch.cli.theme_pack_validate import validate_pack
from iarch.lib import compositor, configstore


class ApplyError(RuntimeError):
    """Apply failed; rollback failures are included in the message."""


def _signal(theme_id, run):
    answer = theme_engine.ipc_call(theme_engine.IPC_TARGET_THEME,
                                   theme_engine.IPC_FUNCTION_APPLY,
                                   (theme_id,), run=run)
    return answer is not None and not answer.timed_out and answer.ok


def apply(pack_path, render, *, env=None, run=None, play_sound=None):
    """Validate, render and apply one pack; restore bytes and reload on failure.

    ``render`` receives validated documents and returns session_theme action
    tuples (kind, path, body). It must be pure and must not write files. Only
    generated and preserving actions understood by the shared renderer are
    accepted. Exceptions before the first write leave the session untouched.
    """
    env = os.environ if env is None else env
    docs = validate_pack(pack_path)
    if docs['theme']['id'] == 'dynamic-reference':
        raise ApplyError('the reference pack cannot be applied')
    actions = list(render(docs))
    if not actions:
        raise ApplyError('renderer supplied no output actions')
    record_path = theme_records.selection_path(env)
    paths = [Path(item[1]) for item in actions]
    if len(set(paths)) != len(paths) or record_path in paths:
        raise ApplyError('duplicate output path')
    if any(item[0] not in ('generated', 'generated-existing', 'preserving') for item in actions):
        raise ApplyError('unknown output action')
    # A failed baseline probe means there is no way to tell whether a new error
    # appeared. Refuse before writing rather than treating that as an empty list.
    baseline = compositor.config_errors(run=run)
    if baseline is None:
        raise ApplyError('cannot read compositor errors before applying')
    previous = theme_records.read_selection(env)
    snapshots = {p: session_theme._snapshot(p) for p in paths + [record_path]}
    modes = {p: p.stat().st_mode & 0o7777 for p in snapshots
             if not p.is_symlink() and p.is_file()}
    started = False
    try:
        started = True
        changed, _ = session_theme._apply_actions(actions, env)
        theme_records.write_selection({'schema_version': 1, 'id': docs['theme']['id'],
                                       'engine': 'dynamic', 'overrides': previous['overrides']}, env)
        if not _signal(docs['theme']['id'], run):
            raise ApplyError('dynamic shell did not acknowledge the theme')
        reload_result = compositor.reload(run=run)
        if not reload_result['reloaded']:
            raise ApplyError('compositor reload failed')
        after = compositor.config_errors(run=run)
        if after is None:
            raise ApplyError('cannot read compositor errors after applying')
        fresh = compositor.new_errors(baseline, after)
        if fresh:
            raise ApplyError('compositor rejected theme: ' + '; '.join(fresh))
    except Exception as exc:
        failures = []
        if started:
            for path, snapshot in reversed(list(snapshots.items())):
                try:
                    session_theme._restore(path, snapshot)
                    if path in modes:
                        path.chmod(modes[path])
                except OSError as restore_error:
                    failures.append(f'{path}: {restore_error}')
            if previous['engine'] == 'dynamic' and not _signal(previous['id'], run):
                failures.append('shell restore signal failed')
            if not compositor.reload(run=run)['reloaded']:
                failures.append('compositor restore reload failed')
        suffix = '; rollback errors: ' + '; '.join(failures) if failures else ''
        raise ApplyError(f'{exc}{suffix}') from exc
    # Sound is post-commit and nonessential; playback failure cannot undo a
    # verified theme or falsely report that rollback happened.
    sound_warning = None
    if play_sound is not None:
        try:
            play_sound(docs, Path(pack_path))
        except Exception as exc:
            sound_warning = str(exc)
    return {'id': docs['theme']['id'], 'changed': [str(p) for p in changed],
            'verdict': 'applied', 'sound_warning': sound_warning}
