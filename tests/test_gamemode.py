# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove game mode composes two tools, and knows what the session is running.

Game mode is not a third renderer. It saves the state it is about to replace,
asks ``iarch-theme`` for the performance intensity and ``iarch-anim`` for the
preset that intensity is paired with, reloads, then asks the compositor what it
actually runs and compares. So the tests here are mostly about the seams:

* the values come out of the tokens, not out of the tool -- every leaf game mode
  checks is one the surface record vouches for, and the preset it applies is the
  one ``intensities.performance.motion`` already names, read through
  ``gen_animations_lua.preset_for_intensity`` so the pairing cannot drift;
* the files it leaves behind are byte for byte the files the two tools leave
  behind when asked directly, which is what makes it a composition rather than a
  fork of them;
* a missing binary is unverified, never a failure and never a pass: no hyprctl
  means four unverified leaves and exit 0, and ``getoption`` answering
  ``no such option`` is quoted rather than read as ``false``;
* a session that was asked and disagreed is reported as a failure, and the files
  and the record are deliberately *not* rolled back, because rewriting them to
  match a compositor that just answered something else would leave both sides
  describing a state nobody asked for;
* when the motion half refuses, the intensity half goes back to the state this
  run found -- which is the saved restore point the first time and the
  performance intensity the second, and the difference is the whole reason the
  rollback target is passed in rather than read from the record;
* reduce-motion is never switched off by a performance mode: the motion half
  renders ``minimal`` instead and the report says so;
* ``off`` restores what ``on`` saved, refuses a record it cannot honour instead of
  guessing, and ``--forget`` clears a record without sending anything.

The compositor is faked the way tests/test_iarch_anim.py fakes it: a script on
PATH answering ``getoption`` the way ``dispatchGetOption`` does at v0.57.2
(``{"option": ..., "<type>": ..., "set": ...}``, or the literal ``no such
option``), ``reload`` the way ``reloadRequest`` does, and ``unknown request`` for
anything else. A reload applies the leaf values a test wrote to
``$FAKE_BIN/on_reload`` first, which is how "the compositor took the config" and
"the compositor said ok and changed nothing" are both testable.
"""
from __future__ import annotations

import json
import os
import re
import stat
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
from iarch.cli import gen_glass_lua as glass  # noqa: E402
from iarch.cli import iarch_anim as anim_cli  # noqa: E402
from iarch.cli import iarch_gamemode as cli  # noqa: E402
from iarch.cli import theme as theme_cli  # noqa: E402
from iarch.lib import configstore, modes  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
ANIMATIONS_SURFACE = ROOT / 'data' / 'design' / 'animations.json'
SETTINGS_SCHEMA = ROOT / 'data' / 'schemas' / 'settings.schema.json'
TOKENS_SCHEMA = ROOT / 'data' / 'schemas' / 'tokens.schema.json'

FAKE_HYPRCTL = '''#!/bin/sh
# A stand-in for hyprctl at v0.57.2. getoption answers the way dispatchGetOption
# does (src/ipc/s1/Commands.cpp:1717-1800) -- one JSON object with exactly one
# type key, or the literal "no such option" for a leaf it does not know. reload
# answers ok, and first applies whatever a test wrote to $FAKE_BIN/on_reload, so
# one test can have a compositor that took the config and the next one that said
# ok and changed nothing. Anything unregistered answers "unknown request" and
# still exits 0 (src/ipc/s1/S1.cpp:107).
#
# Builtins only. The sandbox PATH holds nothing but this directory, so grep, sed,
# cut, cat and mv are not there to use -- and putting /usr/bin back on PATH would
# let a real hyprctl answer for a fake a test deliberately removed, which is the
# one way an "it could not be asked" test silently becomes a passing one.
LOG="$FAKE_BIN/hyprctl.log"
STATE="$FAKE_BIN/state"
for arg in "$@"; do printf '%s\n' "$arg" >> "$LOG"; done
printf -- '--\n' >> "$LOG"
[ -f "$STATE" ] || : > "$STATE"

read_leaf() {
  # $1 = leaf. Prints the stored "kind:value", or nothing: the last line wins the
  # way a compositor's own value would.
  found=""
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$1="*) found="${line#*=}" ;;
    esac
  done < "$STATE"
  printf '%s' "$found"
}

set_leaf() {
  # $1 = leaf, $2 = "kind:value". Rewrites the state without the old line for it.
  keep=""
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$1="*) ;;
      *) keep="${keep}${line}
" ;;
    esac
  done < "$STATE"
  printf '%s%s=%s\n' "$keep" "$1" "$2" > "$STATE"
}

apply_file() {
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] || continue
    set_leaf "${line%%=*}" "${line#*=}"
  done < "$1"
}

case "$1" in
  getoption)
    stored=$(read_leaf "$2")
    if [ -z "$stored" ]; then printf 'no such option\n'; exit 0; fi
    printf '{"option": "%s", "%s": %s, "set": true }\n' "$2" "${stored%%:*}" "${stored#*:}"
    exit 0
    ;;
  reload)
    apply_file "$FAKE_BIN/on_reload"
    printf 'ok\n'
    exit 0
    ;;
  configerrors)
    if [ -n "$CONFIG_ERRORS" ]; then printf '%s\n' "$CONFIG_ERRORS"; fi
    exit 0
    ;;
esac
printf 'unknown request\n'
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

FAKE_NOCTALIA = '''#!/bin/sh
# A stand-in for `noctalia msg ...` at v5.4.1: the literal "ok" on success. Game
# mode only ever asks it to reload the shell's own config.
LOG="$FAKE_BIN/noctalia.log"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
printf 'ok\\n'
exit 0
'''

# The four leaves game mode checks, and the values the performance intensity gives
# them. Spelled out here so a test that asserts them is asserting the promise
# rather than re-deriving it from the same tokens the tool reads.
PERFORMANCE_LEAVES = {
    'decoration:blur:enabled': False,
    'decoration:glow:enabled': False,
    'decoration:dim_inactive': False,
    'animations:enabled': False,
}
# With reduce-motion on, the motion half renders `minimal` rather than `off`, and
# minimal leaves Hyprland's master animation switch on: the accessibility setting
# is honoured, so the leaf game mode checks is true even at the performance
# intensity. Getting this wrong in either direction is the bug the test exists for.
PERFORMANCE_REDUCED_LEAVES = {
    'decoration:blur:enabled': False,
    'decoration:glow:enabled': False,
    'decoration:dim_inactive': False,
    'animations:enabled': True,
}
FROSTED_LEAVES = {
    'decoration:blur:enabled': True,
    'decoration:glow:enabled': True,
    'decoration:dim_inactive': True,
    'animations:enabled': True,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def tokens() -> Dict[str, Any]:
    return read_json(TOKENS_PATH)


def lua_block(text: str, key: str) -> str:
    """The whole ``key = { ... }`` table in rendered Lua, braces balanced."""
    start = text.index(f'{key} = {{')
    brace = text.index('{', start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f'unbalanced Lua table for {key!r}')


def leaf_in(text: str, key: str, value: Any) -> bool:
    """Whether rendered Lua assigns ``value`` to ``key`` anywhere in ``text``."""
    wanted = {True: 'true', False: 'false'}.get(value, str(value))
    return re.search(rf'(?<![\w.]){re.escape(key)}\s*=\s*{re.escape(wanted)}\b', text) is not None


class TheRecordedSurface(unittest.TestCase):
    """What the tokens and the schemas say, before any tool runs."""

    def test_game_mode_names_an_intensity_the_tokens_define(self):
        tk = tokens()
        self.assertIn(cli.game_intensity(tk), tk['intensities'])
        self.assertEqual('performance', cli.game_intensity(tk))

    def test_the_preset_is_the_one_the_intensity_is_already_paired_with(self):
        tk = tokens()
        intensity = cli.game_intensity(tk)
        self.assertEqual(tk['intensities'][intensity]['motion']['preset'],
                         cli.paired_preset(tk, intensity))
        self.assertEqual('off', cli.paired_preset(tk, intensity))

    def test_game_mode_records_no_motion_preset_of_its_own(self):
        # A second copy of the pairing is how a mode and an intensity start to
        # disagree, so the tokens deliberately do not carry one.
        self.assertNotIn('preset', tokens()['modes']['game'])
        self.assertNotIn('animation_preset', tokens()['modes']['game'])

    def test_the_master_switch_comes_from_the_preset_document(self):
        preset = anim.load_preset(cli.paired_preset(tokens(), 'performance'))
        self.assertIs(False, bool(preset.get('master')))
        self.assertFalse(cli.master_of('off'))
        self.assertTrue(cli.master_of('smooth'))

    def test_every_leaf_it_checks_is_one_a_surface_record_vouches_for(self):
        # The three decoration leaves come from the vocabulary the glass generator
        # is allowed to emit; the master switch comes from the animation surface,
        # which records it with its own upstream citation. Neither list is invented
        # by the mode tool, which is the rule that keeps a check honest.
        recorded = set(tokens()['hyprland']['leaves'])
        for leaf in cli.CHECK_LEAVES:
            self.assertIn(leaf, recorded, f'{leaf} is not in tokens.hyprland.leaves')
        master = read_json(ANIMATIONS_SURFACE)['master_switch']
        self.assertEqual(master['leaf'], cli.MASTER_LEAF)
        self.assertIn('ConfigValues.cpp:348', master['source'])
        self.assertNotIn(cli.MASTER_LEAF, recorded,
                         'the animation master switch belongs to the animation surface')

    def test_the_expected_values_are_the_tokens_values_not_a_slogan(self):
        tk = tokens()
        preset = cli.paired_preset(tk, cli.game_intensity(tk))
        expected = cli.expected_leaves(tk, cli.game_intensity(tk), preset)
        self.assertEqual(PERFORMANCE_LEAVES, expected)

    def test_the_runtime_record_names_eval_and_keeps_the_rejected_keyword(self):
        runtime = tokens()['modes']['runtime']
        self.assertTrue(runtime['set_via'].startswith('hyprctl eval '))
        self.assertEqual('hyprctl getoption <leaf> -j', runtime['read_via'])
        self.assertEqual('hyprctl configerrors', runtime['errors_via'])
        self.assertEqual('hyprctl reload', runtime['reload_via'])
        # The rejected spelling stays in the record with its evidence: the shipped
        # manual still documents `hyprctl keyword`, so the next reader needs the
        # reason it cannot be used, not just its absence.
        self.assertEqual('hyprctl keyword <leaf> <value>', runtime['rejected_spelling'])
        self.assertIn('src/ipc/s1/Commands.cpp:2084-2126', runtime['rejected_note'])
        self.assertIn('docs/hyprctl.1.rst:36-40', runtime['rejected_note'])

    def test_nothing_in_the_tokens_offers_the_removed_keyword_command_as_a_route(self):
        raw = TOKENS_PATH.read_text(encoding='utf-8')
        for match in re.finditer(r'hyprctl keyword', raw):
            context = raw[max(0, match.start() - 200):match.end() + 200]
            self.assertTrue('rejected' in context or 'does not exist' in context
                            or 'No keyword command' in context,
                            'hyprctl keyword is cited as a live mechanism')

    def test_the_schema_closes_the_runtime_record(self):
        schema = read_json(TOKENS_SCHEMA)['properties']['modes']
        runtime = schema['properties']['runtime']
        self.assertFalse(runtime['additionalProperties'])
        self.assertEqual('^hyprctl eval ', runtime['properties']['set_via']['pattern'])
        for key in ('set_via', 'read_via', 'errors_via', 'reload_via', 'source',
                    'rejected_spelling', 'rejected_note'):
            self.assertIn(key, runtime['required'])

    def test_settings_does_not_require_the_modes_block(self):
        # A settings.json written before Part 3 has to keep validating, and keep
        # loading, or upgrading would look like a corrupt file to the person who
        # never asked for a mode switch.
        schema = read_json(SETTINGS_SCHEMA)
        self.assertIn('modes', schema['properties'])
        self.assertNotIn('modes', schema['required'])
        self.assertFalse(schema['properties']['modes']['additionalProperties'])
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest('jsonschema not installed; CI validates with the library')
        jsonschema.Draft7Validator.check_schema(schema)
        old = {'version': 1, 'preset': 'glass',
               'effects': {'blur': True, 'transparency': True, 'animations': True,
                           'shadows': True}}
        self.assertEqual([], list(jsonschema.Draft7Validator(schema).iter_errors(old)))
        self.assertEqual([], list(jsonschema.Draft7Validator(schema)
                                  .iter_errors(read_json(ROOT / 'data' / 'settings.default.json'))))

    def test_the_record_enums_agree_with_the_settings_enums(self):
        # The schema cannot read another key, so the two enums are duplicated --
        # and duplication that nothing checks is how a record starts lying.
        schema = read_json(SETTINGS_SCHEMA)['properties']
        game = schema['modes']['properties']['game']['properties']['previous']['properties']
        tk = tokens()
        self.assertEqual(sorted(schema['theme']['properties']['intensity']['enum']),
                         sorted(game['intensity']['enum']))
        self.assertEqual(sorted(schema['animation']['properties']['preset']['enum']),
                         sorted(game['animation_preset']['enum']))
        self.assertEqual(sorted(tk['intensities']), sorted(game['intensity']['enum']))
        on_disk = sorted(path.stem for path in (ROOT / 'data' / 'design' / 'animations').glob('*.json'))
        self.assertEqual(on_disk, sorted(game['animation_preset']['enum']))

    def test_the_default_settings_carry_both_modes_off(self):
        defaults = read_json(ROOT / 'data' / 'settings.default.json')
        self.assertEqual({'game': {'active': False}, 'focus': {'active': False}},
                         defaults['modes'])


class Sandbox(unittest.TestCase):
    """A temporary config home, settings dir and PATH with a faked session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.config_home = root / 'config'
        self.state_dir = root / 'iarch'
        self.fake_bin = root / 'bin'
        for path in (self.config_home, self.state_dir, self.fake_bin):
            path.mkdir(parents=True)

        for name, body in (('hyprctl', FAKE_HYPRCTL), ('luac', FAKE_LUAC),
                           ('noctalia', FAKE_NOCTALIA)):
            script = self.fake_bin / name
            script.write_text(body, encoding='utf-8')
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        # PATH holds nothing but the fake bin dir, so a real hyprctl or noctalia on
        # this machine cannot answer for a removed fake and quietly turn an
        # "could not be asked" test into a passing one. The fakes run through an
        # absolute #!/bin/sh and need no PATH of their own.
        self.env: Dict[str, str] = {
            'PATH': str(self.fake_bin),
            'FAKE_BIN': str(self.fake_bin),
            'IARCH_CONFIG_DIR': str(self.state_dir),
            'IARCH_STATE_DIR': str(self.state_dir),
            'HOME': str(root),
        }
        patcher = mock.patch.dict(os.environ, self.env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session()

    # ------------------------------------------------------------ faked session

    def session(self, leaves: Optional[Dict[str, Any]] = None, **variables: str) -> None:
        """Point the fake compositor at a scenario, and clear its logs."""
        self.set_leaves(leaves if leaves is not None else FROSTED_LEAVES)
        (self.fake_bin / 'on_reload').unlink(missing_ok=True)
        for name in ('hyprctl.log', 'noctalia.log'):
            (self.fake_bin / name).unlink(missing_ok=True)
        os.environ.update(variables)
        for key in ('LUAC_FAIL', 'CONFIG_ERRORS'):
            if key not in variables:
                os.environ.pop(key, None)

    def set_leaves(self, leaves: Dict[str, Any]) -> None:
        """What ``hyprctl getoption`` will answer, as leaf=kind:value lines."""
        (self.fake_bin / 'state').write_text(self.encode(leaves), encoding='utf-8')

    @staticmethod
    def encode(leaves: Dict[str, Any]) -> str:
        lines = []
        for leaf, value in leaves.items():
            if isinstance(value, bool):
                lines.append(f'{leaf}=bool:{"true" if value else "false"}')
            else:
                lines.append(f'{leaf}=float:{value}')
        return '\n'.join(lines) + ('\n' if lines else '')

    def leaves_now(self) -> Dict[str, Any]:
        """What the fake compositor would answer for every leaf it stores."""
        state = (self.fake_bin / 'state').read_text(encoding='utf-8')
        found: Dict[str, Any] = {}
        for line in state.splitlines():
            leaf, _, stored = line.partition('=')
            kind, _, value = stored.partition(':')
            if kind == 'bool':
                found[leaf] = value == 'true'
            elif kind == 'float':
                found[leaf] = float(value)
            else:
                found[leaf] = value
        return found

    def reload_applies(self, leaves: Dict[str, Any]) -> None:
        """Make the fake compositor take the config on its next reload.

        A real reload re-parses the generated Lua, which is what puts the applied
        intensity's leaves into the running config; the fake is told the outcome
        instead of being taught to read Lua, so the assumption stays visible in the
        test that relies on it.
        """
        (self.fake_bin / 'on_reload').write_text(self.encode(leaves), encoding='utf-8')

    def running(self, leaves: Dict[str, Any]) -> None:
        """A session that runs ``leaves`` and keeps running them across a reload.

        This is the ordinary case on a real desktop -- a reload re-parses the
        generated Lua, so the values just applied are the values still running --
        and it is what a test that expects exit 0 has to set up. The interesting
        opposite, a compositor that answers ok and changes nothing, is what
        ``session()`` alone leaves in place.
        """
        self.set_leaves(leaves)
        self.reload_applies(leaves)

    def clear_logs(self) -> None:
        for name in ('hyprctl.log', 'noctalia.log'):
            (self.fake_bin / name).unlink(missing_ok=True)

    def reloads(self) -> List[List[str]]:
        return [call for call in self.logged('hyprctl.log') if call[:2] == ['hyprctl', 'reload']]

    def remove_binary(self, name: str) -> None:
        (self.fake_bin / name).unlink()

    def logged(self, name: str) -> List[List[str]]:
        """Every logged invocation of one fake, as the argument vector it was called with.

        The fakes log ``"$@"``, which is the vector without the program name, so
        the name is put back here: a test asserting what was sent should read like
        the command line, not like a fragment of one.
        """
        path = self.fake_bin / name
        if not path.is_file():
            return []
        binary = path.stem
        calls: List[List[str]] = []
        current: List[str] = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if line == '--':
                calls.append([binary, *current])
                current = []
            else:
                current.append(line)
        return calls

    # ------------------------------------------------------------ helpers

    def run_cli(self, *argv: str) -> Tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*argv, '--config-home', str(self.config_home)])
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *argv: str) -> Tuple[int, Dict[str, Any], str]:
        code, out, err = self.run_cli(*argv, '--json')
        return code, json.loads(out), err

    @property
    def glass_path(self) -> Path:
        return self.config_home / 'hypr' / 'generated' / 'glass.lua'

    @property
    def animations_path(self) -> Path:
        return self.config_home / 'hypr' / 'generated' / 'animations.lua'

    @property
    def settings_path(self) -> Path:
        return configstore.user_path('settings', os.environ)

    def settings(self) -> Dict[str, Any]:
        return read_json(self.settings_path)

    def record(self) -> Dict[str, Any]:
        return self.settings().get('modes', {}).get('game', {})

    def written_glass(self) -> str:
        return self.glass_path.read_text(encoding='utf-8')

    def written_animations(self) -> str:
        return self.animations_path.read_text(encoding='utf-8')

    def backups(self) -> List[Path]:
        directory = configstore.backup_dir(os.environ)
        return sorted(directory.glob('*.bak')) if directory.is_dir() else []

    def apply_directly(self, intensity: str, preset: str) -> Path:
        """Ask the two tools for the same state in a second home, and return it.

        Game mode's promise is that it composes them, so the strongest check on
        its output is that the files are the files they produce -- not a second
        implementation of the render inside the test.
        """
        home = Path(tempfile.mkdtemp(dir=self.tmp.name))
        _tk, _preset, colour, _intensity = theme_cli._resolve(None, None, os.environ)
        # Both siblings print, and the motion one prints a whole JSON report, so
        # their output is swallowed here: this helper is a reference render, not
        # the thing under test.
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            theme_cli.main(['apply', colour, '--intensity', intensity,
                            '--config-home', str(home), '--no-reload'])
            anim_cli.main(['set', preset, '--config-home', str(home), '--json'])
        return home


class SwitchingItOn(Sandbox):
    def test_on_writes_exactly_what_the_two_tools_write(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        home = self.apply_directly('performance', 'off')
        self.assertEqual((home / 'hypr' / 'generated' / 'glass.lua').read_text(encoding='utf-8'),
                         self.written_glass())
        self.assertEqual(
            (home / 'hypr' / 'generated' / 'animations.lua').read_text(encoding='utf-8'),
            self.written_animations())

    def test_the_performance_payload_really_turns_the_four_leaves_off(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        glass_text = self.written_glass()
        decoration = lua_block(glass_text, 'decoration')
        self.assertTrue(leaf_in(decoration, 'dim_inactive', False))
        self.assertTrue(leaf_in(lua_block(decoration, 'blur'), 'enabled', False))
        self.assertTrue(leaf_in(lua_block(decoration, 'glow'), 'enabled', False))
        self.assertTrue(leaf_in(lua_block(self.written_animations(), 'animations'),
                                'enabled', False))

    def test_on_records_the_state_it_replaced(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.assertEqual({'active': True,
                          'previous': {'colour_preset': 'midnight-glass',
                                       'intensity': 'frosted',
                                       'animation_preset': 'smooth',
                                       'reduce_motion': False}}, self.record())

    def test_the_settings_it_writes_validate_against_the_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest('jsonschema not installed; CI validates with the library')
        self.session()
        self.run_cli('on')
        schema = read_json(SETTINGS_SCHEMA)
        self.assertEqual([], list(jsonschema.Draft7Validator(schema)
                                  .iter_errors(self.settings())))

    def test_on_says_what_the_theme_and_animation_blocks_now_say(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        settings = self.settings()
        self.assertEqual('performance', settings['theme']['intensity'])
        self.assertEqual('off', settings['animation']['preset'])

    def test_on_asks_the_compositor_to_reload_and_then_the_shell(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.assertIn(['hyprctl', 'reload'], self.logged('hyprctl.log'))
        self.assertEqual([['noctalia', 'msg', 'config-reload']], self.logged('noctalia.log'))

    def test_the_report_carries_the_sibling_argv_in_order(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        _code, report, _err = self.run_json('on')
        tools = [step['tool'] for step in report['steps']]
        self.assertEqual(['iarch-theme', 'iarch-anim'], tools[:2])
        theme_argv = report['steps'][0]['argv']
        self.assertEqual(['apply', 'midnight-glass', '--intensity', 'performance',
                          '--config-home', str(self.config_home), '--no-reload'], theme_argv)
        anim_argv = report['steps'][1]['argv']
        self.assertEqual(['set', 'off', '--config-home', str(self.config_home), '--json'],
                         anim_argv)

    def test_the_theme_half_is_asked_not_to_reload_so_the_two_halves_reload_once(self):
        # Two reloads would mean two full re-parses of the config and two flickers;
        # game mode sends one, after both halves are on disk.
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertIn('--no-reload', report['steps'][0]['argv'])
        self.assertNotIn('--no-reload', report['steps'][1]['argv'])
        self.assertEqual([['hyprctl', 'reload']], self.reloads())

    def test_a_second_on_keeps_the_original_restore_point(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        first = self.record()
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual(first, self.record())

    def test_a_settings_file_from_before_part_3_still_works(self):
        self.settings_path.write_text(json.dumps(
            {'version': 1, 'preset': 'glass',
             'effects': {'blur': True, 'transparency': True, 'animations': True,
                         'shadows': True},
             'theme': {'colour_preset': 'midnight-glass', 'intensity': 'soft'},
             'animation': {'preset': 'bouncy', 'speed': 1.25, 'reduce_motion': False,
                           'event_overrides': {'fadeDim': False}}}), encoding='utf-8')
        self.session()
        self.running(PERFORMANCE_LEAVES)
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        record = self.record()
        self.assertEqual('soft', record['previous']['intensity'])
        self.assertEqual('bouncy', record['previous']['animation_preset'])
        # The keys the person chose survive: a mode that rewrote the file from the
        # repository defaults would silently undo their speed and their overrides.
        settings = self.settings()
        self.assertEqual(1.25, settings['animation']['speed'])
        self.assertEqual({'fadeDim': False}, settings['animation']['event_overrides'])

    def test_dry_run_writes_nothing_and_sends_nothing(self):
        self.session()
        code, out, _err = self.run_cli('on', '--dry-run')
        self.assertEqual(0, code)
        self.assertFalse(self.glass_path.exists())
        self.assertFalse(self.settings_path.exists())
        self.assertEqual([], self.logged('hyprctl.log'))
        self.assertEqual([], self.logged('noctalia.log'))
        self.assertIn('nothing was written', out)
        self.assertIn('performance', out)

    def test_dry_run_still_reads_the_session_it_would_replace(self):
        self.session()
        _code, report, _err = self.run_json('on', '--dry-run')
        self.assertTrue(report['dry_run'])
        self.assertEqual('frosted', report['previous']['intensity'])
        self.assertIs(False, report['applied'])

    def test_no_reload_writes_the_files_and_never_reloads_anything(self):
        self.session()
        code, out, _err = self.run_cli('on', '--no-reload')
        self.assertEqual(0, code)
        self.assertTrue(self.glass_path.is_file())
        # iarch-anim still reads `configerrors` once, because that read is the
        # baseline its own rollback compares against; reading is not reloading, and
        # it changes nothing. What must not happen is a reload of either half.
        self.assertEqual([], self.reloads())
        self.assertEqual([], self.logged('noctalia.log'))
        self.assertIn('unverified', out)
        self.assertIn('--no-reload', self.report_of('on', '--no-reload')['steps'][1]['argv'])

    def report_of(self, *argv: str) -> Dict[str, Any]:
        _code, report, _err = self.run_json(*argv)
        return report


class ReduceMotionIsNotAGameSetting(Sandbox):
    def turn_reduce_motion_on(self) -> None:
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'animation': {'preset': 'smooth', 'speed': 1.0,
                                                    'reduce_motion': True,
                                                    'event_overrides': {}}}, os.environ)

    def test_on_renders_minimal_instead_of_switching_an_accessibility_setting_off(self):
        self.turn_reduce_motion_on()
        self.session()
        self.running(PERFORMANCE_REDUCED_LEAVES)
        code, out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertTrue(self.settings()['animation']['reduce_motion'])
        self.assertIn('minimal', out)

    def test_the_report_says_which_preset_the_motion_half_really_rendered(self):
        self.turn_reduce_motion_on()
        self.session()
        self.running(PERFORMANCE_REDUCED_LEAVES)
        _code, report, _err = self.run_json('on')
        self.assertEqual('minimal', report['target']['rendered_preset'])
        self.assertEqual('off', report['target']['animation_preset'])
        self.assertTrue(report['previous']['reduce_motion'])

    def test_the_master_leaf_it_checks_is_the_one_minimal_renders(self):
        self.turn_reduce_motion_on()
        self.session()
        self.running(PERFORMANCE_REDUCED_LEAVES)
        _code, report, _err = self.run_json('on')
        master = [check for check in report['checks']
                  if check['leaf'] == 'animations:enabled'][0]
        self.assertEqual(cli.master_of('minimal'), master['expected'])

    def test_off_restores_the_preset_that_was_saved_and_keeps_reduce_motion(self):
        self.turn_reduce_motion_on()
        self.session()
        self.running(PERFORMANCE_REDUCED_LEAVES)
        self.run_cli('on')
        self.running(FROSTED_LEAVES)
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        settings = self.settings()
        self.assertEqual('smooth', settings['animation']['preset'])
        # `off` restores the preset that was saved, not the one that was rendered:
        # reduce-motion is still the person's, so the render still comes out minimal.
        self.assertTrue(settings['animation']['reduce_motion'])
        self.assertTrue(settings['animation']['reduce_motion'])


class SwitchingItOff(Sandbox):
    def test_off_restores_what_on_saved(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.running(FROSTED_LEAVES)
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        home = self.apply_directly('frosted', 'smooth')
        self.assertEqual((home / 'hypr' / 'generated' / 'glass.lua').read_text(encoding='utf-8'),
                         self.written_glass())
        self.assertEqual({'active': False}, self.record())
        self.assertEqual('frosted', self.settings()['theme']['intensity'])

    def test_off_restores_the_colour_preset_too(self):
        self.session()
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'theme': {'colour_preset': 'tokyo-night-glass',
                                                'intensity': 'crystal'}}, os.environ)
        self.running(PERFORMANCE_LEAVES)
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        # Game mode changes the intensity, never the palette: a person who chose a
        # colour scheme gets it back, and gets it in the same state it was left in.
        self.assertEqual('tokyo-night-glass', self.settings()['theme']['colour_preset'])
        self.assertEqual('performance', self.settings()['theme']['intensity'])
        self.running({'decoration:blur:enabled': True, 'decoration:glow:enabled': True,
                      'decoration:dim_inactive': True, 'animations:enabled': True})
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertEqual('tokyo-night-glass', self.settings()['theme']['colour_preset'])
        self.assertEqual('crystal', self.settings()['theme']['intensity'])

    def test_off_with_nothing_recorded_changes_nothing(self):
        self.session()
        code, out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertIn('already off', out)
        self.assertFalse(self.glass_path.exists())
        self.assertEqual([], self.logged('noctalia.log'))
        self.assertEqual([], self.reloads())

    def test_off_with_nothing_recorded_still_says_what_the_session_runs(self):
        # Reading is not changing. An `off` that finds nothing to undo is the one
        # moment a person is most likely to be wondering what the desktop is
        # actually doing, so it reports the four leaves anyway.
        self.session()
        _code, report, _err = self.run_json('off')
        self.assertEqual(4, len(report['checks']))
        self.assertIs(False, report['applied'])

    def test_off_refuses_a_record_it_cannot_honour(self):
        self.session()
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'modes': {'game': {'active': True}}}, os.environ)
        code, out, err = self.run_cli('off')
        self.assertEqual(2, code)
        self.assertIn('--forget', out + err)
        self.assertFalse(self.glass_path.exists())
        self.assertEqual([], self.logged('hyprctl.log'))
        # The record stays: clearing it would leave no way back to a state that
        # was never recorded in the first place.
        self.assertTrue(self.record()['active'])

    def test_forget_clears_the_record_and_sends_nothing(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.clear_logs()
        code, out, _err = self.run_cli('off', '--forget')
        self.assertEqual(0, code)
        self.assertIn('nothing was reloaded', out)
        self.assertEqual([], self.logged('noctalia.log'))
        self.assertEqual([], self.reloads())
        self.assertEqual({'active': False}, self.record())
        # The files still say performance: --forget is about a record, not a render.
        self.assertTrue(leaf_in(lua_block(self.written_glass(), 'decoration'),
                                'dim_inactive', False))

    def test_dry_run_off_writes_nothing(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        before = self.written_glass()
        self.clear_logs()
        code, out, _err = self.run_cli('off', '--dry-run')
        self.assertEqual(0, code)
        self.assertEqual(before, self.written_glass())
        self.assertTrue(self.record()['active'])
        self.assertEqual([], self.logged('hyprctl.log'))
        self.assertEqual([], self.logged('noctalia.log'))
        self.assertIn('frosted', out)

    def test_toggle_goes_there_and_back(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        code, out, _err = self.run_cli('toggle')
        self.assertEqual(0, code)
        self.assertIn('game mode on', out)
        self.assertTrue(self.record()['active'])
        self.running(FROSTED_LEAVES)
        code, out, _err = self.run_cli('toggle')
        self.assertEqual(0, code)
        self.assertIn('game mode off', out)
        self.assertEqual({'active': False}, self.record())

    def test_toggle_reports_which_way_it_went(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        _code, report, _err = self.run_json('toggle')
        self.assertIs(False, report['toggled_from'])
        self.assertEqual('toggle (on)', report['command'])


class WhenAToolRefuses(Sandbox):
    def test_a_render_luac_rejects_puts_the_intensity_back(self):
        self.session(LUAC_FAIL='1')
        code, out, err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertIn('was run again to put', out + err)
        self.assertIn('frosted', out + err)
        # The intensity half went back to what this run found, so the desktop is
        # the desktop it was, and the record says nothing happened.
        home = self.apply_directly('frosted', 'smooth')
        self.assertEqual((home / 'hypr' / 'generated' / 'glass.lua').read_text(encoding='utf-8'),
                         self.written_glass())
        self.assertEqual({'active': False}, self.record())
        self.assertEqual('frosted', self.settings()['theme']['intensity'])

    def test_the_report_names_the_rollback_and_why(self):
        self.session(LUAC_FAIL='1')
        code, report, _err = self.run_json('on')
        self.assertEqual(1, code)
        self.assertIs(False, report['ok'])
        self.assertIsNotNone(report['rollback'])
        self.assertEqual(['apply', 'midnight-glass', '--intensity', 'frosted',
                          '--config-home', str(self.config_home)],
                         report['rollback']['attempted'])
        self.assertIs(True, report['rollback']['restored'])
        self.assertIn('iarch-anim refused', report['error'])
        self.assertEqual(['iarch-theme', 'iarch-anim', 'iarch-theme (rollback)'],
                         [step['tool'] for step in report['steps']])

    def test_the_rollback_targets_the_state_this_run_found_not_the_saved_one(self):
        # The two are the same the first time game mode is switched on and
        # different the second. Rolling back to the saved restore point while game
        # mode is already on would leave the desktop somewhere it has not been
        # since before the first switch.
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.session(LUAC_FAIL='1')
        self.running(PERFORMANCE_LEAVES)
        code, report, _err = self.run_json('on')
        self.assertEqual(1, code)
        self.assertEqual(['apply', 'midnight-glass', '--intensity', 'performance',
                          '--config-home', str(self.config_home)],
                         report['rollback']['attempted'])
        self.assertTrue(leaf_in(lua_block(self.written_glass(), 'decoration'),
                                'dim_inactive', False))
        self.assertTrue(self.record()['active'])

    def test_the_rollback_reloads_once_and_game_mode_adds_no_second_reload(self):
        # The tool that put the files back is the one that asks the session to
        # re-read them, which is right: the desktop should match the disk again.
        # What must not happen is game mode's own shell reload on top of it, since
        # the bundle it belongs to never completed.
        self.session(LUAC_FAIL='1')
        _code, report, _err = self.run_json('on')
        self.assertEqual([['noctalia', 'msg', 'config-reload']], self.logged('noctalia.log'))
        self.assertEqual([], report['ran'])
        self.assertIn('iarch-anim refused', report['error'])


class WhatTheSessionSays(Sandbox):
    def test_a_session_that_took_the_config_verifies(self):
        self.session()
        self.reload_applies(PERFORMANCE_LEAVES)
        # "before" is the frosted session, and the reload is what flips it: the
        # check has to see a change, or it is not checking anything.
        code, report, _err = self.run_json('on')
        self.assertEqual(0, code)
        self.assertEqual('matches', report['verdict'])
        self.assertEqual([modes.MATCHES] * 4, [check['verdict'] for check in report['checks']])

    def test_a_session_that_said_ok_and_changed_nothing_is_reported_not_passed(self):
        self.session()
        code, out, err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertIn('does not run what was just applied', out + err)
        self.assertEqual(FROSTED_LEAVES, self.leaves_now())

    def test_the_files_and_the_record_are_kept_when_the_session_disagrees(self):
        # Rolling back here would leave the disk describing one state and the
        # compositor another, which is worse than the disagreement it was meant to
        # fix; the report says which leaf differs instead.
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertEqual('differs', report['verdict'])
        self.assertIs(False, report['ok'])
        self.assertTrue(report['applied'])
        self.assertIsNone(report['rollback'])
        self.assertTrue(self.record()['active'])
        self.assertTrue(leaf_in(lua_block(self.written_glass(), 'decoration'),
                                'dim_inactive', False))
        self.assertTrue(any('left as they are' in note for note in report['notes']))

    def test_a_differing_leaf_is_named_with_both_values(self):
        self.session()
        _code, report, _err = self.run_json('on')
        blur = [check for check in report['checks']
                if check['leaf'] == 'decoration:blur:enabled'][0]
        self.assertEqual('differs', blur['verdict'])
        self.assertIs(True, blur['actual'])
        self.assertIs(False, blur['expected'])
        self.assertIn('expected false', blur['detail'])

    def test_no_hyprctl_is_unverified_rather_than_a_failure(self):
        self.remove_binary('hyprctl')
        self.session()
        code, out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertIn('unverified', out)
        self.assertTrue(self.record()['active'])

    def test_no_hyprctl_leaves_four_unverified_checks_and_no_verdict_of_matches(self):
        self.remove_binary('hyprctl')
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertEqual('unverified', report['verdict'])
        self.assertEqual([modes.UNVERIFIED] * 4, [check['verdict'] for check in report['checks']])
        for check in report['checks']:
            self.assertIsNone(check['actual'])
            self.assertIn('not on PATH', check['detail'])

    def test_an_unknown_leaf_is_unverified_rather_than_read_as_false(self):
        # `getoption` answers the literal "no such option" even under -j, which is
        # not JSON and not a value: guessing at it would turn a renamed leaf into a
        # claim that the compositor is running something it never answered for.
        self.session(leaves={})
        code, report, _err = self.run_json('on')
        self.assertEqual('unverified', report['verdict'])
        for check in report['checks']:
            self.assertEqual(modes.UNVERIFIED, check['verdict'])
            self.assertIn('no such option', check['detail'])
        self.assertEqual(0, code)

    def test_a_float_leaf_is_compared_with_a_tolerance_not_equality(self):
        # dispatchGetOption prints floats with {:2f}, so 0.5 comes back as "0.50"
        # and an equality test against the recorded number would fail on a
        # compositor that is running exactly the right value.
        self.session(leaves={'decoration:blur:enabled': False,
                             'decoration:glow:enabled': False,
                             'decoration:dim_inactive': False,
                             'animations:enabled': False})
        (self.fake_bin / 'state').write_text(
            'decoration:blur:enabled=bool:false\n'
            'decoration:glow:enabled=bool:false\n'
            'decoration:dim_inactive=bool:false\n'
            'animations:enabled=bool:false\n'
            'decoration:dim_strength=float:0.50\n', encoding='utf-8')
        value, reply = modes.getoption('decoration:dim_strength')
        self.assertIsNotNone(reply)
        self.assertTrue(modes.same_value(0.5, value))

    def test_status_exits_zero_even_when_the_session_disagrees(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        self.session(leaves=FROSTED_LEAVES)
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('disagrees', out)

    def test_status_reports_the_record_the_settings_and_the_session(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('recorded:      on', out)
        self.assertIn('performance', out)
        self.assertIn('agrees', out)

    def test_status_says_when_the_record_and_the_rendered_state_disagree(self):
        # Something re-rendered the desktop after game mode was switched on, so the
        # record is a claim about a state that is no longer running.
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        configstore.save('settings', {**self.settings(),
                                      'theme': {'colour_preset': 'midnight-glass',
                                                'intensity': 'soft'}}, os.environ)
        code, out, err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('re-rendered the desktop since', out + err)
        _code, report, _err = self.run_json('status')
        self.assertEqual('differs', report['record_agreement'])

    def test_status_before_anything_ran_reports_the_repository_defaults(self):
        self.session()
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('recorded:      off', out)
        self.assertIn('frosted', out)

    def test_status_with_no_session_is_unverified_and_still_exits_zero(self):
        self.remove_binary('hyprctl')
        self.session()
        code, report, _err = self.run_json('status')
        self.assertEqual(0, code)
        self.assertEqual('unverified', report['verdict'])
        self.assertIsNone(report['record_agreement'])


class TheReport(Sandbox):
    def test_json_is_one_object_on_stdout_and_the_prose_is_not_in_it(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        code, out, err = self.run_cli('on', '--json')
        self.assertEqual(0, code)
        report = json.loads(out)
        self.assertEqual('iarch-gamemode', report['tool'])
        for key in ('command', 'mode', 'ok', 'previous', 'target', 'steps', 'checks',
                    'verdict', 'settings', 'exit'):
            self.assertIn(key, report)
        # The siblings' own prose is captured inside steps[].stdout as data, which
        # is the point of the report; what must not be there is this tool's prose.
        self.assertNotIn('game mode is on', out)
        self.assertTrue(out.startswith('{') and out.rstrip().endswith('}'))
        # A faked session that agrees produces no warnings at all, so stderr being
        # empty here is the clean case rather than a missing one; the test that
        # warnings reach stderr removes hyprctl and asserts it separately.
        self.assertEqual('', err)

    def test_a_parsed_sibling_report_is_not_also_kept_as_raw_lines(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        _code, report, _err = self.run_json('on')
        anim_step = [step for step in report['steps'] if step['tool'] == 'iarch-anim'][0]
        self.assertEqual([], anim_step['stdout'])
        self.assertEqual('iarch-anim', anim_step['report']['tool'])
        # The theme half runs without --json, so its prose is the only record of
        # what it did and has to stay.
        theme_step = [step for step in report['steps'] if step['tool'] == 'iarch-theme'][0]
        self.assertTrue(theme_step['stdout'])
        self.assertNotIn('report', theme_step)

    def test_warnings_go_to_stderr_so_a_pipe_still_gets_clean_json(self):
        self.remove_binary('hyprctl')
        self.session()
        _code, out, err = self.run_cli('status', '--json')
        json.loads(out)
        self.assertIn('warning:', err)

    def test_the_settings_block_names_the_file_it_wrote(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        _code, report, _err = self.run_json('on')
        self.assertEqual(str(self.settings_path), report['settings']['path'].replace(
            '~', str(Path.home()), 1) if report['settings']['path'].startswith('~')
            else report['settings']['path'])
        self.assertIs(True, report['settings']['changed'])

    def test_recording_the_same_state_twice_is_not_a_change(self):
        self.session()
        self.running(PERFORMANCE_LEAVES)
        self.run_cli('on')
        _code, report, _err = self.run_json('on')
        self.assertIs(False, report['settings']['changed'])

    def test_a_relative_config_home_is_a_usage_error(self):
        self.session()
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['on', '--config-home', 'relative/path'])
        self.assertEqual(2, code)
        self.assertIn('absolute', out.getvalue() + err.getvalue())
        self.assertFalse(self.glass_path.exists())

    def test_no_subcommand_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                cli.main([])
        self.assertEqual(2, caught.exception.code)


if __name__ == '__main__':
    unittest.main()
