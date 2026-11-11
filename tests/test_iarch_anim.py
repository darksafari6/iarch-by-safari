# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove iarch-anim writes what it validated, and undoes what the compositor rejects.

The interesting failures here are the ones that only happen next to a running
Hyprland, and this sandbox has none — no hyprctl, no luac, no session. So the
compositor is faked: a script on PATH that answers ``reload``, ``configerrors`` and
``animations`` the way src/ipc/s1/Commands.cpp does at v0.57.2, driven by
environment variables so one test can have a clean session and the next a session
that rejects the config. That is what makes the rollback path, the baseline
comparison and the "no answer is not a clean answer" rule testable at all.

What is asserted:

* each subcommand renders, writes and persists the state it claims, and the file it
  writes is the one the generator produces for that state;
* a change nothing needs is a no-op: re-applying the same state neither rewrites the
  file nor rotates a backup;
* ``--dry-run`` writes nothing and changes no settings;
* the multiplier is clamped and the clamped value is what gets stored, so
  ``current`` never reports a number the render did not use;
* ``toggle`` stores an override and drops it again when the flip lands back on what
  the preset declares, and refuses the two cases that cannot work rather than
  storing something the renderer would reject;
* reduce-motion forces the minimal preset and caps every duration, whatever was
  selected before;
* when the reload produces a config error that was not there before, the file goes
  back byte for byte, the compositor is reloaded again, the settings are left
  alone and the exit code is 1;
* an error that was already there is not blamed on this change, and a compositor
  that gives no answer is reported as unverified rather than passed;
* a render ``luac`` rejects never reaches the file;
* ``--json`` is one object on stdout with every key present, and the prose that a
  person reads is not mixed into it.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_animations_lua as anim  # noqa: E402
from iarch.cli import iarch_anim as cli  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
SETTINGS_SCHEMA = ROOT / 'data' / 'schemas' / 'settings.schema.json'

FAKE_HYPRCTL = '''#!/bin/sh
# A stand-in for hyprctl at v0.57.2. It remembers that a reload happened, and
# reports config errors the way configErrorsRequest does in its normal format:
# one line per error, and nothing at all when the config parsed cleanly.
MARK="$FAKE_BIN/.reloaded"
case "$*" in
  *reload*)
    touch "$MARK"
    exit 0
    ;;
  *configerrors*)
    if [ -n "$PRE_ERROR" ]; then printf '%s\\n' "$PRE_ERROR"; fi
    if [ -f "$MARK" ] && [ -n "$POST_ERROR" ]; then printf '%s\\n' "$POST_ERROR"; fi
    exit 0
    ;;
  *animations*)
    if [ -n "$ANIMATIONS_ANSWER" ]; then printf '%s\\n' "$ANIMATIONS_ANSWER"; fi
    exit 0
    ;;
esac
exit 0
'''

FAKE_LUAC = '''#!/bin/sh
# A stand-in for `luac -p FILE`: parses without executing, and fails when told to.
if [ -n "$LUAC_FAIL" ]; then
  printf 'luac: %s: syntax error\\n' "$2" >&2
  exit 1
fi
exit 0
'''


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def tokens() -> Dict[str, Any]:
    return read_json(TOKENS_PATH)


class Sandbox(unittest.TestCase):
    """A temporary config home, settings dir and PATH, per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.config_home = root / 'config'
        self.state_dir = root / 'iarch'
        self.fake_bin = root / 'bin'
        for path in (self.config_home, self.state_dir, self.fake_bin):
            path.mkdir(parents=True)

        self.hyprctl = self.fake_bin / 'hyprctl'
        self.hyprctl.write_text(FAKE_HYPRCTL, encoding='utf-8')
        self.hyprctl.chmod(self.hyprctl.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        self.luac = self.fake_bin / 'luac'
        self.luac.write_text(FAKE_LUAC, encoding='utf-8')
        self.luac.chmod(self.luac.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        self.env: Dict[str, str] = {
            'PATH': f'{self.fake_bin}:' + os.environ.get('PATH', ''),
            'IARCH_CONFIG_DIR': str(self.state_dir),
            'FAKE_BIN': str(self.fake_bin),
            'HOME': str(root),
        }
        patcher = mock.patch.dict(os.environ, self.env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._clear_reloaded)

    def _clear_reloaded(self):
        (self.fake_bin / '.reloaded').unlink(missing_ok=True)

    # ------------------------------------------------------------ helpers

    def session(self, **variables: str) -> None:
        """Point the fake compositor at a scenario."""
        os.environ.update({key: value for key, value in variables.items()})
        for key in ('PRE_ERROR', 'POST_ERROR', 'LUAC_FAIL', 'ANIMATIONS_ANSWER'):
            if key not in variables:
                os.environ.pop(key, None)
        self._clear_reloaded()

    def run_cli(self, *argv: str) -> Tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*argv, '--config-home', str(self.config_home)])
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *argv: str) -> Tuple[int, Dict[str, Any], str]:
        code, out, err = self.run_cli(*argv, '--json')
        return code, json.loads(out), err

    @property
    def target(self) -> Path:
        return self.config_home / 'hypr' / 'generated' / 'animations.lua'

    @property
    def settings_path(self) -> Path:
        return self.state_dir / 'settings.json'

    def settings(self) -> Dict[str, Any]:
        return read_json(self.settings_path)['animation']

    def written(self) -> str:
        return self.target.read_text(encoding='utf-8')

    def backups(self) -> List[Path]:
        directory = configstore.backup_dir(os.environ)
        return sorted(directory.glob('*.bak')) if directory.is_dir() else []


class ReadingTheState(Sandbox):
    def test_current_works_before_anything_has_been_written(self):
        code, out, _err = self.run_cli('current')
        self.assertEqual(0, code)
        self.assertIn('smooth', out)
        self.assertIn('repository default', out)

    def test_a_settings_file_with_no_animation_block_still_resolves(self):
        # configstore.load merges the repository defaults under the user's file, so
        # a settings.json written before Part 3 has to keep working.
        self.settings_path.write_text(json.dumps({'version': 1, 'preset': 'glass',
                                                  'effects': {'blur': True, 'transparency': True,
                                                              'animations': True,
                                                              'shadows': True}}),
                                      encoding='utf-8')
        code, out, _err = self.run_cli('current')
        self.assertEqual(0, code)
        self.assertIn('smooth', out)

    def test_a_settings_file_the_user_chose_wins(self):
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'animation': {'preset': 'bouncy', 'speed': 1.5,
                                                    'reduce_motion': False,
                                                    'event_overrides': {'fadeDim': False}}},
                         os.environ)
        code, out, _err = self.run_cli('current')
        self.assertEqual(0, code)
        self.assertIn('bouncy', out)
        self.assertIn('1.5', out)
        self.assertIn('fadeDim=off', out)

    def test_a_non_boolean_override_is_refused(self):
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'animation': {'preset': 'smooth', 'speed': 1.0,
                                                    'reduce_motion': False,
                                                    'event_overrides': {'fade': 'off'}}},
                         os.environ)
        code, _out, err = self.run_cli('current')
        self.assertEqual(2, code)
        self.assertIn('not a boolean', err)

    def test_a_current_state_the_file_does_not_match_is_said_so(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text('-- something else entirely\n', encoding='utf-8')
        code, out, _err = self.run_cli('current')
        self.assertEqual(0, code)
        self.assertIn('does NOT match this state', out)


class WritingTheState(Sandbox):
    def test_set_writes_the_file_the_generator_produces(self):
        self.session()
        code, _out, _err = self.run_cli('set', 'bouncy')
        self.assertEqual(0, code)
        expected = cli._rendered_bytes(
            self.target,
            anim.build_preset(tokens(), anim.load_surface(), anim.load_preset('bouncy'))
            .rstrip('\n'))
        self.assertEqual(expected, self.written())

    def test_set_records_the_state_in_the_users_settings(self):
        self.session()
        self.run_cli('set', 'snappy')
        self.assertEqual({'preset': 'snappy', 'speed': 1.0, 'reduce_motion': False,
                          'event_overrides': {}}, self.settings())

    def test_the_settings_it_writes_validate_against_the_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest('jsonschema not installed; CI validates with the library')
        self.session()
        self.run_cli('set', 'bouncy')
        jsonschema.validate(read_json(self.settings_path), read_json(SETTINGS_SCHEMA))

    def test_it_keeps_the_settings_it_did_not_touch(self):
        self.session()
        self.run_cli('set', 'bouncy')
        document = read_json(self.settings_path)
        self.assertEqual('glass', document['preset'])
        self.assertIn('effects', document)
        self.assertIn('theme', document)

    def test_every_preset_can_be_applied(self):
        self.session()
        for name in ('smooth', 'snappy', 'bouncy', 'minimal', 'off'):
            with self.subTest(preset=name):
                code, _out, err = self.run_cli('set', name)
                self.assertEqual(0, code, err)
                self.assertEqual(name, self.settings()['preset'])
                self.assertIn(f'animations/{name}.json', self.written())

    def test_the_off_preset_writes_only_the_master_switch(self):
        self.session()
        self.run_cli('set', 'off')
        body = self.written()
        self.assertIn('enabled = false', body)
        self.assertNotIn('hl.curve', body)
        self.assertNotIn('hl.animation', body)

    def test_reapplying_the_same_state_is_a_no_op(self):
        self.session()
        self.run_cli('set', 'bouncy')
        before, backups = self.written(), len(self.backups())
        code, out, _err = self.run_cli('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertIn('unchanged', out)
        self.assertEqual(before, self.written())
        self.assertEqual(backups, len(self.backups()), 'a no-op rotated a backup')

    def test_a_change_keeps_a_backup_of_what_it_replaced(self):
        self.session()
        self.run_cli('set', 'bouncy')
        first = self.written()
        self.run_cli('set', 'snappy')
        self.assertIn('animations/snappy.json', self.written())
        self.assertTrue(any(first.encode('utf-8') in path.read_bytes() or
                            'bouncy' in path.read_text(encoding='utf-8')
                            for path in self.backups()),
                        'the previous render was not backed up')

    def test_dry_run_writes_nothing_and_changes_no_settings(self):
        self.session()
        code, out, _err = self.run_cli('set', 'bouncy', '--dry-run')
        self.assertEqual(0, code)
        self.assertIn('would write', out)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.settings_path.exists())

    def test_no_reload_writes_the_file_but_does_not_ask_the_compositor(self):
        self.session()
        code, out, err = self.run_cli('set', 'bouncy', '--no-reload')
        self.assertEqual(0, code, err)
        self.assertTrue(self.target.exists())
        self.assertFalse((self.fake_bin / '.reloaded').exists())
        self.assertIn('skipped (--no-reload)', out)


class TheMultiplierIsClamped(Sandbox):
    def test_a_multiplier_inside_the_bounds_is_stored_as_given(self):
        self.session()
        self.run_cli('speed', '1.25')
        self.assertEqual(1.25, self.settings()['speed'])

    def test_a_multiplier_above_the_ceiling_is_clamped_and_stored_clamped(self):
        self.session()
        code, _out, err = self.run_cli('speed', '99')
        self.assertEqual(0, code)
        self.assertEqual(2.0, self.settings()['speed'])
        self.assertIn('outside 0.5..2.0', err)

    def test_a_multiplier_below_the_floor_is_clamped(self):
        self.session()
        self.run_cli('speed', '0.01')
        self.assertEqual(0.5, self.settings()['speed'])

    def test_the_clamped_value_is_what_the_render_uses(self):
        self.session()
        self.run_cli('speed', '99')
        expected = cli._rendered_bytes(
            self.target,
            anim.build_preset(tokens(), anim.load_surface(), anim.load_preset('smooth'),
                              multiplier=2.0).rstrip('\n'))
        self.assertEqual(expected, self.written())

    def test_a_multiplier_that_is_not_a_number_is_a_usage_error(self):
        # argparse rejects it before main() runs, so this is a SystemExit(2) rather
        # than a returned code — still exit 2, still nothing written.
        err = StringIO()
        with self.assertRaises(SystemExit) as caught:
            with redirect_stdout(StringIO()), redirect_stderr(err):
                cli.main(['speed', 'fast', '--config-home', str(self.config_home)])
        self.assertEqual(2, caught.exception.code)
        self.assertIn('invalid float value', err.getvalue())
        self.assertFalse(self.target.exists())

    def test_speed_survives_a_preset_change(self):
        self.session()
        self.run_cli('speed', '1.5')
        self.run_cli('set', 'bouncy')
        self.assertEqual({'preset': 'bouncy', 'speed': 1.5}, 
                         {k: v for k, v in self.settings().items()
                          if k in ('preset', 'speed')})


class ToggleIsAnOverrideThatDoesNotOutliveItsReason(Sandbox):
    def test_toggling_an_event_off_stores_an_override_and_disables_it(self):
        self.session()
        self.run_cli('set', 'smooth')
        code, out, _err = self.run_cli('toggle', 'borderangle')
        self.assertEqual(0, code, out)
        self.assertIn('off', out)
        self.assertEqual({'borderangle': False}, self.settings()['event_overrides'])
        self.assertIn('leaf = "borderangle", enabled = false', self.written())

    def test_toggling_it_back_drops_the_override(self):
        self.session()
        self.run_cli('set', 'smooth')
        self.run_cli('toggle', 'borderangle')
        self.run_cli('toggle', 'borderangle')
        self.assertEqual({}, self.settings()['event_overrides'])
        self.assertIn('leaf = "borderangle", enabled = true', self.written())

    def test_the_other_events_are_untouched_by_a_toggle(self):
        self.session()
        self.run_cli('set', 'smooth')
        before = self.written()
        self.run_cli('toggle', 'borderangle')
        after = self.written()
        self.assertEqual(before.count('hl.animation'), after.count('hl.animation'))
        self.assertIn('leaf = "windows", enabled = true', after)

    def test_toggling_an_event_the_preset_does_not_declare_is_refused(self):
        self.session()
        self.run_cli('set', 'smooth')
        code, _out, err = self.run_cli('toggle', 'fadePopups')
        self.assertEqual(2, code)
        self.assertIn('is not an event', err)

    def test_toggling_on_an_event_the_preset_declares_off_is_refused_with_a_reason(self):
        self.session()
        self.run_cli('set', 'minimal')
        code, _out, err = self.run_cli('toggle', 'windows')
        self.assertEqual(1, code)
        self.assertIn('nothing to turn on', err)

    def test_toggling_the_master_switch_off_preset_is_refused(self):
        self.session()
        self.run_cli('set', 'off')
        code, _out, err = self.run_cli('toggle', 'windows')
        self.assertEqual(1, code)
        self.assertIn('master animation switch off', err)


class ReduceMotion(Sandbox):
    def test_it_renders_minimal_with_every_duration_capped(self):
        self.session()
        self.run_cli('set', 'bouncy')
        code, _out, err = self.run_cli('reduce-motion', 'on')
        self.assertEqual(0, code, err)
        cap = anim.reduce_motion_cap_ms(tokens())
        seen = 0
        for line in self.written().splitlines():
            # The header comments mention "speed = duration_ms / 100", so only the
            # hl.animation calls are parsed.
            if not line.startswith('hl.animation') or 'speed =' not in line:
                continue
            speed = float(line.split('speed =')[1].split(',')[0])
            self.assertLessEqual(speed * 100, cap, line)
            seen += 1
        self.assertTrue(seen, 'no animated event was checked')

    def test_it_keeps_the_preset_the_person_chose(self):
        self.session()
        self.run_cli('set', 'bouncy')
        self.run_cli('reduce-motion', 'on')
        state = self.settings()
        self.assertEqual('bouncy', state['preset'])
        self.assertTrue(state['reduce_motion'])

    def test_turning_it_off_brings_that_preset_back(self):
        self.session()
        self.run_cli('set', 'bouncy')
        self.run_cli('reduce-motion', 'on')
        self.run_cli('reduce-motion', 'off')
        self.assertIn('animations/bouncy.json', self.written())
        self.assertFalse(self.settings()['reduce_motion'])

    def test_it_turns_off_everything_that_moves(self):
        self.session()
        self.run_cli('reduce-motion', 'on')
        body = self.written()
        for leaf in ('windows', 'workspaces', 'specialWorkspace', 'borderangle'):
            self.assertIn(f'leaf = "{leaf}", enabled = false', body)

    def test_toggling_motion_back_on_under_it_is_refused(self):
        self.session()
        self.run_cli('reduce-motion', 'on')
        code, _out, err = self.run_cli('toggle', 'windows')
        self.assertEqual(1, code)
        self.assertIn('reduce-motion is on', err)


class TheCompositorGetsTheLastWord(Sandbox):
    def test_a_clean_reload_is_verified(self):
        self.session()
        code, report, _err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('clean', report['verification']['verdict'])
        self.assertEqual([], report['verification']['configerrors']['new'])
        self.assertIn('hyprctl reload', report['reload']['ran'])

    def test_a_new_config_error_rolls_the_file_back(self):
        self.session()
        self.run_cli('set', 'bouncy')
        before = self.written()
        self.session(POST_ERROR='animation leaf notARealLeaf is not a node')
        code, _out, err = self.run_cli('set', 'snappy')
        self.assertEqual(1, code)
        self.assertIn('put back and reloaded', err)
        self.assertIn('notARealLeaf', err)
        self.assertEqual(before, self.written())

    def test_a_rollback_leaves_the_settings_alone(self):
        self.session()
        self.run_cli('set', 'bouncy')
        self.session(POST_ERROR='boom')
        self.run_cli('set', 'snappy')
        self.assertEqual('bouncy', self.settings()['preset'])

    def test_a_rollback_reloads_again_so_the_session_runs_the_restored_file(self):
        self.session()
        self.run_cli('set', 'bouncy')
        self.session(POST_ERROR='boom')
        _code, report, _err = self.run_json('set', 'snappy')
        self.assertTrue(report['rollback']['restored'])
        self.assertEqual(['boom'], report['rollback']['reason'])
        self.assertEqual(2, len(report['reload']['ran']), report['reload'])

    def test_a_rollback_of_a_first_write_removes_the_file_it_created(self):
        # There was nothing to restore, so restoring means not leaving a config the
        # compositor has just rejected behind.
        self.session(POST_ERROR='boom')
        code, _out, _err = self.run_cli('set', 'bouncy')
        self.assertEqual(1, code)
        self.assertFalse(self.target.exists())

    def test_an_error_that_was_already_there_is_not_blamed_on_this_change(self):
        self.session(PRE_ERROR='somebody elses typo in hyprland.conf')
        code, report, err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('clean', report['verification']['verdict'])
        self.assertEqual(['somebody elses typo in hyprland.conf'],
                         report['verification']['configerrors']['baseline'])
        self.assertEqual([], report['verification']['configerrors']['new'])
        code, _out, err = self.run_cli('current')
        self.assertEqual(0, code)

    def test_a_pre_existing_error_is_still_reported_to_the_person(self):
        self.session(PRE_ERROR='an old typo')
        _code, _out, err = self.run_cli('set', 'bouncy')
        self.assertIn('already had 1 parsing error', err)

    def test_a_compositor_that_gives_no_answer_is_unverified_not_passed(self):
        self.session()
        self.hyprctl.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        self.hyprctl.chmod(self.hyprctl.stat().st_mode | stat.S_IXUSR)
        code, report, _err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('unverified', report['verification']['verdict'])

    def test_no_compositor_at_all_is_a_warning_and_still_writes_the_file(self):
        os.environ['PATH'] = str(Path(self.tmp.name) / 'empty')
        code, report, err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('unverified', report['verification']['verdict'])
        self.assertTrue(self.target.exists())
        self.assertTrue(any('not on PATH' in line for line in report['reload']['skipped']))

    def test_the_live_animation_state_can_be_asked_for(self):
        self.session(ANIMATIONS_ANSWER='{"animations":[{"name":"windows"}],"beziers":[]}')
        self.run_cli('set', 'bouncy')
        code, report, _err = self.run_json('current', '--live')
        self.assertEqual(0, code)
        self.assertEqual('clean', report['verification']['verdict'])
        self.assertIsNotNone(report['verification']['live'])


class LuaIsParsedWhenAParserExists(Sandbox):
    def test_a_render_luac_accepts_is_written(self):
        self.session()
        code, report, _err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('passed', report['verification']['luac']['status'])
        self.assertTrue(self.target.exists())

    def test_a_render_luac_rejects_never_reaches_the_file(self):
        self.session(LUAC_FAIL='1')
        code, report, _err = self.run_json('set', 'bouncy')
        self.assertEqual(1, code)
        self.assertFalse(report['ok'])
        self.assertEqual('failed', report['verification']['luac']['status'])
        self.assertIn('syntax error', report['verification']['luac']['detail'])
        # Under --json the reason is in the object, not on stderr: stdout carries one
        # parseable document and nothing else.
        self.assertIn('not valid Lua', report['error'])
        self.assertIsNone(report['written'])
        self.assertIsNone(report['settings'])
        self.assertFalse(self.target.exists())
        self.assertFalse(self.settings_path.exists())

    def test_the_same_refusal_is_prose_on_stderr_without_json(self):
        self.session(LUAC_FAIL='1')
        code, _out, err = self.run_cli('set', 'bouncy')
        self.assertEqual(1, code)
        self.assertIn('not valid Lua', err)

    def test_no_lua_compiler_is_reported_as_missing_not_passed(self):
        self.luac.unlink()
        self.session()
        code, report, _err = self.run_json('set', 'bouncy')
        self.assertEqual(0, code)
        self.assertEqual('missing', report['verification']['luac']['status'])
        self.assertTrue(self.target.exists())


class TheJsonContract(Sandbox):
    KEYS = {'tool', 'command', 'ok', 'state', 'effective', 'target', 'written',
            'unchanged', 'dry_run', 'backup', 'settings', 'rollback', 'warnings',
            'reload', 'verification'}

    def test_every_command_prints_one_object_and_nothing_else(self):
        self.session()
        for argv in (['list'], ['current'], ['set', 'bouncy'], ['speed', '1.2'],
                     ['toggle', 'fadeDim'], ['reduce-motion', 'on'],
                     ['reduce-motion', 'off']):
            with self.subTest(command=argv[0]):
                code, out, _err = self.run_cli(*argv, '--json')
                self.assertEqual(0, code, out)
                document = json.loads(out)  # one object, or this raises
                self.assertEqual('iarch-anim', document['tool'])
                self.assertTrue(self.KEYS.issubset(document), 
                                self.KEYS - set(document))

    def test_the_object_carries_the_resolved_plan_parts_4_and_5_read(self):
        self.session()
        _code, report, _err = self.run_json('set', 'bouncy')
        events = report['effective']['events']
        self.assertEqual(18, len(events))
        windows = next(e for e in events if e['leaf'] == 'windows')
        self.assertEqual({'leaf', 'enabled', 'duration_ms', 'speed', 'curve', 'kind',
                          'style', 'duration_is_inert'}, set(windows))
        self.assertEqual(300, windows['duration_ms'])
        self.assertEqual(3.0, windows['speed'])
        self.assertEqual('iarch-overshoot', windows['curve'])

    def test_a_failure_is_also_one_object_with_the_exit_code_in_it(self):
        self.session()
        code, out, _err = self.run_cli('set', 'nope', '--json')
        self.assertEqual(2, code)
        document = json.loads(out)
        self.assertFalse(document['ok'])
        self.assertEqual(2, document['exit'])
        self.assertIn('unknown preset', document['error'])

    def test_a_refusal_is_one_object_too(self):
        self.session(POST_ERROR='boom')
        code, out, _err = self.run_cli('set', 'bouncy', '--json')
        self.assertEqual(1, code)
        document = json.loads(out)
        self.assertFalse(document['ok'])
        self.assertEqual(1, document['exit'])
        self.assertTrue(document['rollback']['restored'])

    def test_list_reports_every_preset_and_which_one_is_active(self):
        self.session()
        self.run_cli('set', 'bouncy')
        _code, report, _err = self.run_json('list')
        names = [entry['name'] for entry in report['presets']]
        self.assertEqual(['smooth', 'snappy', 'bouncy', 'minimal', 'off'], names)
        active = [entry['name'] for entry in report['presets'] if entry['active']]
        self.assertEqual(['bouncy'], active)
        minimal = next(e for e in report['presets'] if e['name'] == 'minimal')
        self.assertEqual(11, minimal['events_animating'])
        off = next(e for e in report['presets'] if e['name'] == 'off')
        self.assertEqual(0, off['events_animating'])
        self.assertFalse(off['master'])

    def test_prose_and_json_are_not_mixed_on_stdout(self):
        self.session()
        _code, out, _err = self.run_cli('set', 'bouncy', '--json')
        self.assertFalse(out.lstrip().startswith('iArch'), out[:80])
        self.assertTrue(out.lstrip().startswith('{'))


class UsageErrors(Sandbox):
    def test_an_unknown_preset_names_the_real_ones(self):
        code, _out, err = self.run_cli('set', 'nope')
        self.assertEqual(2, code)
        self.assertIn('smooth, snappy, bouncy, minimal, off', err)

    def test_a_relative_config_home_is_refused(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['current', '--config-home', 'relative/path'])
        self.assertEqual(2, code)
        self.assertIn('absolute path', err.getvalue())

    def test_no_subcommand_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stderr(StringIO()):
                cli.main([])
        self.assertEqual(2, caught.exception.code)


if __name__ == '__main__':
    unittest.main()
