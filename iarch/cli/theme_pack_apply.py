# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Transactional dynamic-theme writes, with verified shell and compositor reloads.

Rendering is injected: callers must prepare the entire set of output actions
before this transaction begins. A missing IPC/compositor response is a failure,
not an implicit success. The transaction does not launch a shell.
"""
import base64
import copy
import json
import os
from pathlib import Path

from iarch.cli import session_theme, theme_engine, theme_records
from iarch.cli.theme_pack_validate import validate_pack
from iarch.lib import compositor, configstore


class ApplyError(RuntimeError):
    """Apply failed; rollback failures are included in the message."""


def _signal(theme_id, run, no_transition=False):
    answer = theme_engine.ipc_call(theme_engine.IPC_TARGET_THEME,
                                   theme_engine.IPC_FUNCTION_APPLY,
                                   (theme_id, 'no-transition') if no_transition else (theme_id,), run=run)
    if answer is None or answer.timed_out or not answer.ok:
        return False
    # Exit zero means only that IPC was transported. A handler must explicitly
    # acknowledge the apply; an empty or negative reply is not verification.
    reply = answer.stdout.strip()
    if reply.lower() in ('true', 'ok'):
        return True
    try:
        value = json.loads(reply)
    except ValueError:
        return False
    return isinstance(value, dict) and value.get('ok') is True and value.get('id') == theme_id


def _checkpoint_path(env):
    return configstore.state_dir(env) / 'theme-rollback.json'


def _encode_snapshots(snapshots, modes, previous):
    entries = []
    for path, (kind, data, link) in snapshots.items():
        entries.append({'path': str(path), 'kind': kind,
                        'data': base64.b64encode(data).decode('ascii') if data is not None else None,
                        'link': link, 'mode': modes.get(path)})
    return {'schema_version': 1, 'previous': previous, 'files': entries}


def _decode_snapshots(payload, env):
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or not isinstance(payload.get('files'), list):
        raise ApplyError('invalid rollback record')
    allowed_roots = (configstore.home_dir(env) / '.config', configstore.config_dir(env))
    snapshots, modes = {}, {}
    for item in payload['files']:
        if not isinstance(item, dict) or set(item) != {'path', 'kind', 'data', 'link', 'mode'}:
            raise ApplyError('invalid rollback entry')
        path = Path(item['path'])
        if not path.is_absolute() or '..' in path.parts or not any(path.is_relative_to(root) and path != root for root in allowed_roots):
            raise ApplyError('rollback path outside configuration roots')
        if path in snapshots or item['kind'] not in ('file', 'missing', 'symlink'):
            raise ApplyError('invalid rollback path or kind')
        try:
            data = base64.b64decode(item['data'], validate=True) if item['data'] is not None else None
        except (ValueError, TypeError) as exc:
            raise ApplyError('invalid rollback data') from exc
        if (item['kind'] == 'file' and data is None) or (item['kind'] != 'file' and data is not None):
            raise ApplyError('rollback entry data does not match kind')
        if item['kind'] == 'symlink' and not isinstance(item['link'], str):
            raise ApplyError('invalid rollback symlink')
        mode = item['mode']
        if mode is not None and (not isinstance(mode, int) or not 0 <= mode <= 0o7777):
            raise ApplyError('invalid rollback mode')
        snapshots[path] = (item['kind'], data, item['link'])
        if mode is not None:
            modes[path] = mode
    return snapshots, modes


def _restore_snapshots(snapshots, modes):
    failures = []
    for path, snapshot in reversed(list(snapshots.items())):
        try:
            session_theme._restore(path, snapshot)
            if path in modes:
                path.chmod(modes[path])
        except OSError as exc:
            failures.append(f'{path}: {exc}')
    return failures


def rollback(*, env=None, run=None):
    """Restore the last successful apply; recover the current state on failure."""
    env = os.environ if env is None else env
    checkpoint = _checkpoint_path(env)
    try:
        payload = json.loads(checkpoint.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ApplyError(f'no readable rollback record: {exc}') from exc
    snapshots, modes = _decode_snapshots(payload, env)
    previous = payload.get('previous')
    if not isinstance(previous, dict) or previous.get('engine') not in ('classic', 'dynamic') or not isinstance(previous.get('id'), str):
        raise ApplyError('invalid previous selection')
    baseline = compositor.config_errors(run=run)
    if baseline is None:
        raise ApplyError('cannot read compositor errors before rollback')
    current_selection = theme_records.read_selection(env)
    current = {path: session_theme._snapshot(path) for path in snapshots}
    current_modes = {p: p.stat().st_mode & 0o7777 for p in current if not p.is_symlink() and p.is_file()}
    try:
        errors = _restore_snapshots(snapshots, modes)
        if errors:
            raise ApplyError('; '.join(errors))
        if previous['engine'] == 'dynamic' and not _signal(previous['id'], run):
            raise ApplyError('shell did not acknowledge rollback')
        if not compositor.reload(run=run)['reloaded']:
            raise ApplyError('compositor reload failed during rollback')
        after = compositor.config_errors(run=run)
        if after is None or compositor.new_errors(baseline, after):
            raise ApplyError('compositor could not verify rollback')
    except Exception as exc:
        errors = _restore_snapshots(current, current_modes)
        if current_selection['engine'] == 'dynamic' and not _signal(current_selection['id'], run):
            errors.append('shell restore signal failed')
        if not compositor.reload(run=run)['reloaded']:
            errors.append('compositor restore reload failed')
        raise ApplyError(str(exc) + ('; recovery errors: ' + '; '.join(errors) if errors else '')) from exc
    checkpoint.unlink()
    return {'verdict': 'rolled-back', 'id': previous['id']}


def apply(pack_path, render, *, env=None, run=None, play_sound=None, no_transition=False):
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
    overrides = theme_records.read_overrides(env)
    effective = copy.deepcopy(docs)
    if overrides['accent'] is not None:
        effective['palette']['colors']['accent'] = overrides['accent']
    actions = list(render(effective))
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
        if not _signal(docs['theme']['id'], run, no_transition):
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
        checkpoint = _encode_snapshots(snapshots, modes, previous)
        configstore.atomic_write(_checkpoint_path(env), json.dumps(checkpoint, indent=2) + '\n', validate_json=True)
    except Exception as exc:
        failures = []
        if started:
            failures.extend(_restore_snapshots(snapshots, modes))
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
