# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove focus mode sends what the tokens say, and knows what it cannot read back.

Focus mode is three calls: a compositor eval that dims every unfocused window,
the shell's Do Not Disturb verb, and the shell's caffeine verb. Two of the three
can be read back and one cannot, and the tests here are mostly about that
asymmetry:

* the Lua it sends is the Lua the tokens describe -- the exact string, keys
  sorted, values typed, and a leaf that is not recorded is refused rather than
  guessed at;
* the spelling it sends is ``hyprctl eval``, never the ``hyprctl keyword`` the
  shipped manual still documents and v0.57.2 does not register;
* Do Not Disturb is read back and compared, because ``notification-dnd-status``
  answers exactly ``on`` or ``off``; caffeine is not, because no verb reports it,
  and the report says so instead of implying a check that never happened;
* a refusal undoes what was already sent and stops before sending more: when the
  compositor refuses the dim nothing else is sent at all, and when the shell
  refuses Do Not Disturb the dim goes back and caffeine is never enabled -- a
  caffeine nobody asked for would be the one part of a half-applied mode that
  nothing records and nothing switches off again;
* a missing binary is unverified, never a failure and never a pass, and
  ``getoption`` answering ``no such option`` is quoted rather than read as a value;
* the mode is runtime state, so ``status`` compares the record with what the
  session answers now and reports the drift a reload causes, instead of repeating
  what it wrote earlier.

The compositor and the shell are faked the way tests/test_iarch_anim.py and
tests/test_iarch_doctor.py fake them: scripts on PATH, driven by environment
variables, logging every argument vector so a test asserts what was really sent.
The fake hyprctl does not pretend to understand Lua -- an eval applies whatever a
test wrote to ``$FAKE_BIN/on_eval`` first -- so the Lua itself is proved by the
unit tests below and the round trip by the ones after them.
"""
from __future__ import annotations

import json
import os
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

from iarch.cli import iarch_doctor as doctor  # noqa: E402
from iarch.cli import iarch_focus as cli  # noqa: E402
from iarch.lib import configstore, modes  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
SETTINGS_SCHEMA = ROOT / 'data' / 'schemas' / 'settings.schema.json'

FAKE_HYPRCTL = '''#!/bin/sh
# A stand-in for hyprctl at v0.57.2. getoption answers the way dispatchGetOption
# does (src/ipc/s1/Commands.cpp:1717-1800); eval answers ok, or "error: ..." with
# exit 7 the way CConfigManager::eval does when hl.config refuses a key or a value
# (src/config/lua/ConfigManager.cpp:900-918); reload answers ok (src/ipc/s1/
# Commands.cpp:1352-1370). It logs every eval verbatim, because the exact Lua a
# mode sends is the thing worth asserting, and applies the leaf values a test
# wrote to $FAKE_BIN/on_eval or $FAKE_BIN/on_reload rather than parsing Lua: a
# fake that understood the language would prove nothing about the real one.
#
# Builtins only. The sandbox PATH holds nothing but this directory, so grep, sed,
# cut, cat and mv are not there to use -- and putting /usr/bin back would let a
# real hyprctl answer for a fake a test deliberately removed.
LOG="$FAKE_BIN/hyprctl.log"
EVALLOG="$FAKE_BIN/eval.log"
STATE="$FAKE_BIN/state"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
[ -f "$STATE" ] || : > "$STATE"

read_leaf() {
  found=""
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$1="*) found="${line#*=}" ;;
    esac
  done < "$STATE"
  printf '%s' "$found"
}

set_leaf() {
  keep=""
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$1="*) ;;
      *) keep="${keep}${line}
" ;;
    esac
  done < "$STATE"
  printf '%s%s=%s\\n' "$keep" "$1" "$2" > "$STATE"
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
    if [ -z "$stored" ]; then printf 'no such option\\n'; exit 0; fi
    printf '{"option": "%s", "%s": %s, "set": true }\\n' "$2" "${stored%%:*}" "${stored#*:}"
    exit 0
    ;;
  eval)
    printf '%s\\n' "$2" >> "$EVALLOG"
    if [ -n "$EVAL_ERROR" ]; then printf 'error: %s\\n' "$EVAL_ERROR"; exit 7; fi
    if [ -z "$EVAL_IGNORES" ]; then
      # Honour the eval the way the compositor does: look for the keys it knows and
      # take the value assigned to each. This is not a Lua parser and does not
      # pretend to be one -- it stands in for hl.config looking a key up in its own
      # value map -- and it is what lets one run contain two evals that do different
      # things, the way a refusal and its rollback do.
      code="$2"
      for key in dim_inactive dim_strength; do
        case "$code" in
          *"$key = "*)
            rest="${code#*"$key = "}"
            # Cut at the first comma, then at the first space. A brace cannot go in
            # the pattern: dash ends the expansion at the first "}" it sees, which
            # is how this fake came to store a value with the rest of the Lua in it.
            # The two separators are what lua_table emits and what
            # test_the_dim_call_is_exactly_the_recorded_shape pins.
            value="${rest%%,*}"
            value="${value%% *}"
            [ -n "$value" ] || continue
            case "$value" in
              true|false) set_leaf "decoration:$key" "bool:$value" ;;
              *) set_leaf "decoration:$key" "float:$value" ;;
            esac
            ;;
        esac
      done
    fi
    apply_file "$FAKE_BIN/on_eval"
    printf 'ok\\n'
    exit 0
    ;;
  reload)
    apply_file "$FAKE_BIN/on_reload"
    printf 'ok\\n'
    exit 0
    ;;
  configerrors)
    if [ -n "$CONFIG_ERRORS" ]; then printf '%s\\n' "$CONFIG_ERRORS"; fi
    exit 0
    ;;
esac
printf 'unknown request\\n'
exit 0
'''

FAKE_NOCTALIA = '''#!/bin/sh
# A stand-in for `noctalia msg ...` at v5.4.1. notification-dnd-status prints
# exactly "on" or "off" (src/app/application_ipc.cpp:158-159); the setters print
# the literal "ok", or "error: ..." when a test says the handler refused. The
# caffeine verbs print "ok", or the inhibitor's own refusal when the protocol is
# missing (src/idle/idle_inhibitor.cpp:175-212) -- and there is deliberately no
# caffeine status verb to fake, because upstream has none.
LOG="$FAKE_BIN/noctalia.log"
DND="$FAKE_BIN/dnd"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
[ -f "$DND" ] || printf 'off\\n' > "$DND"

read_dnd() {
  found=""
  while IFS= read -r line || [ -n "$line" ]; do found="$line"; done < "$DND"
  printf '%s' "$found"
}

case "$*" in
  *notification-dnd-status*)
    if [ -n "$DND_STATUS_ANSWER" ]; then printf '%s\\n' "$DND_STATUS_ANSWER"; exit 0; fi
    printf '%s\\n' "$(read_dnd)"
    exit 0
    ;;
  *notification-dnd-set*)
    if [ -n "$DND_ERROR" ]; then printf 'error: %s\\n' "$DND_ERROR"; exit 0; fi
    case "$*" in
      *' on'*) printf 'on\\n' > "$DND" ;;
      *' off'*) printf 'off\\n' > "$DND" ;;
    esac
    printf 'ok\\n'
    exit 0
    ;;
  *caffeine-*)
    if [ -n "$CAFFEINE_ERROR" ]; then printf 'error: %s\\n' "$CAFFEINE_ERROR"; exit 0; fi
    printf 'ok\\n'
    exit 0
    ;;
esac
printf 'ok\\n'
exit 0
'''

# What an unfocused session runs at the shipped default intensity, and what focus
# mode asks for. Both come out of the tokens; they are spelled out here so a test
# asserts the promise rather than re-deriving it from the same file the tool reads.
UNFOCUSED_LEAVES = {
    'decoration:dim_inactive': True,
    'decoration:dim_strength': 0.08,
}
FOCUSED_LEAVES = {
    'decoration:dim_inactive': True,
    'decoration:dim_strength': 0.5,
}
FOCUSED_LUA = ("hl.config({ decoration = { dim_inactive = true, dim_strength = 0.5 } })")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def tokens() -> Dict[str, Any]:
    return read_json(TOKENS_PATH)


def focus_block() -> Dict[str, Any]:
    return tokens()['modes']['focus']


class TheRecordedSurface(unittest.TestCase):
    """What the tokens say, before any call is sent."""

    def test_every_leaf_focus_mode_sets_is_one_the_surface_record_vouches_for(self):
        recorded = set(tokens()['hyprland']['leaves'])
        for leaf in focus_block()['leaves']:
            self.assertIn(leaf, recorded, f'{leaf} is not in tokens.hyprland.leaves')

    def test_every_leaf_it_sets_has_a_value_recorded_beside_it(self):
        focus = focus_block()
        for leaf in focus['leaves']:
            key = leaf.split(':')[-1]
            self.assertIn(key, focus, f'modes.focus names {leaf} but records no {key}')

    def test_the_dim_strength_is_inside_the_range_upstream_declares(self):
        low, high = tokens()['hyprland']['ranges']['decoration:dim_strength']
        self.assertEqual([0, 1], [low, high])
        self.assertLessEqual(low, focus_block()['dim_strength'])
        self.assertLessEqual(focus_block()['dim_strength'], high)

    def test_the_dim_strength_is_upstreams_own_default_and_the_note_says_where(self):
        # 0.5 is MS<Float>("decoration:dim_strength", ..., 0.5, {.min = 0, .max = 1})
        # at src/config/values/ConfigValues.cpp:228 in v0.57.2. A mode that invented
        # a number here would be a second source of truth for a value the compositor
        # already has an opinion about.
        self.assertEqual(0.5, focus_block()['dim_strength'])
        self.assertIn('ConfigValues.cpp:228', focus_block()['_note'])
        self.assertIs(True, focus_block()['dim_inactive'])

    def test_focusing_hands_back_a_stronger_dim_than_any_intensity_ships(self):
        focus_strength = focus_block()['dim_strength']
        for name, block in tokens()['intensities'].items():
            window = block['window']
            if window['dim_inactive']:
                self.assertLess(window['dim_strength'], focus_strength,
                                f'{name} dims harder than focus mode would')
        self.assertIs(False, tokens()['intensities']['performance']['window']['dim_inactive'])

    def test_the_runtime_record_names_eval_and_keeps_the_rejected_keyword(self):
        runtime = tokens()['modes']['runtime']
        self.assertTrue(runtime['set_via'].startswith('hyprctl eval '))
        self.assertEqual('hyprctl keyword <leaf> <value>', runtime['rejected_spelling'])
        self.assertIn('src/ipc/s1/Commands.cpp:2084-2126', runtime['rejected_note'])

    def test_the_tool_sends_the_call_the_record_describes(self):
        runtime = tokens()['modes']['runtime']
        verb, _separator, shape = runtime['set_via'].partition(' ')
        self.assertEqual('hyprctl', verb)
        self.assertTrue(cli.eval_code(FOCUSED_LEAVES).startswith('hl.config('))
        self.assertEqual(runtime['read_via'], 'hyprctl getoption <leaf> -j')
        self.assertEqual(runtime['errors_via'], 'hyprctl configerrors')

    def test_the_settings_schema_records_a_state_it_can_compare(self):
        schema = read_json(SETTINGS_SCHEMA)['properties']['modes']['properties']['focus']
        self.assertFalse(schema['additionalProperties'])
        previous = schema['properties']['previous']
        self.assertEqual(['do_not_disturb', 'leaves'], sorted(previous['required']))
        # Null is a first-class answer: it means "the shell could not be asked",
        # which is not the same as "it was off".
        self.assertEqual(['boolean', 'null'], previous['properties']['do_not_disturb']['type'])
        self.assertEqual(['boolean', 'number', 'null'],
                         previous['properties']['leaves']['additionalProperties']['type'])


class TheLuaItSends(unittest.TestCase):
    """The eval string, proved without a compositor anywhere near it."""

    def test_the_dim_call_is_exactly_the_recorded_shape(self):
        self.assertEqual(FOCUSED_LUA, cli.eval_code(FOCUSED_LEAVES))

    def test_the_keys_are_sorted_so_the_string_is_reproducible(self):
        one = cli.eval_code({'decoration:dim_inactive': True, 'decoration:dim_strength': 0.5})
        other = cli.eval_code({'decoration:dim_strength': 0.5, 'decoration:dim_inactive': True})
        self.assertEqual(one, other)

    def test_a_leaf_nests_the_way_hl_config_walks_it(self):
        # hl.config joins each level with a dot and looks the result up in the
        # compositor's value map (LuaBindingsConfigRules.cpp:955-975).
        self.assertEqual({'decoration': {'dim_inactive': True}},
                         cli.leaf_tree({'decoration:dim_inactive': True}))
        self.assertEqual({'general': {'col': {'active_border': 1}}},
                         cli.leaf_tree({'general:col.active_border': 1}))

    def test_a_hyphen_becomes_an_underscore_the_way_the_compositor_keys_it(self):
        # luaConfigValueName replaces ':' with '.' and '-' with '_'
        # (src/config/lua/ConfigManager.cpp:1114-1119). No leaf this repository
        # records has a hyphen, so the rule is proved with a shape rather than a
        # value the tokens vouch for.
        self.assertEqual({'misc': {'disable_hyprland_logo': True}},
                         cli.leaf_tree({'misc:disable-hyprland-logo': True}))

    def test_a_key_that_is_not_a_lua_name_is_bracketed(self):
        self.assertEqual('{ ["odd-key"] = true }', cli.lua_table({'odd-key': True}))

    def test_booleans_and_numbers_are_lua_literals_not_python_ones(self):
        self.assertEqual('true', cli.lua_value(True))
        self.assertEqual('false', cli.lua_value(False))
        self.assertEqual('0.5', cli.lua_value(0.5))
        self.assertEqual('3', cli.lua_value(3))
        self.assertNotIn('True', cli.lua_table({'a': True}))
        self.assertNotIn('None', cli.lua_table({'a': 0.0}))

    def test_a_small_float_keeps_every_digit_it_needs(self):
        # repr() is the shortest string that round-trips, and Lua reads 1e-05.
        self.assertEqual('1e-05', cli.lua_value(1e-05))
        self.assertEqual('0.06', cli.lua_value(0.06))

    def test_a_value_lua_cannot_hold_is_refused_rather_than_sent(self):
        for value in ('0.5', None, [1], {'a': 1}):
            with self.assertRaises(cli.FocusError):
                cli.lua_value(value)

    def test_a_leaf_that_collides_with_a_value_is_refused(self):
        with self.assertRaises(cli.FocusError):
            cli.leaf_tree({'decoration:dim_inactive': True,
                           'decoration:dim_inactive:x': 1})

    def test_a_leaf_with_no_recorded_value_is_refused(self):
        mutated = tokens()
        mutated['modes']['focus']['leaves'].append('decoration:dim_modal')
        with mock.patch.object(cli.modes, 'load_tokens', return_value=mutated):
            with self.assertRaises(cli.FocusError):
                cli.focus_tokens(mutated)


class Sandbox(unittest.TestCase):
    """A temporary settings dir and a PATH holding a faked compositor and shell."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.state_dir = root / 'iarch'
        self.config_home = root / 'config'
        self.fake_bin = root / 'bin'
        for path in (self.state_dir, self.config_home, self.fake_bin):
            path.mkdir(parents=True)

        for name, body in (('hyprctl', FAKE_HYPRCTL), ('noctalia', FAKE_NOCTALIA)):
            script = self.fake_bin / name
            script.write_text(body, encoding='utf-8')
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

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

    def session(self, leaves: Optional[Dict[str, Any]] = None,
                do_not_disturb: Optional[bool] = None, **variables: str) -> None:
        """Point the fakes at a scenario, and clear their logs."""
        self.set_leaves(UNFOCUSED_LEAVES if leaves is None else leaves)
        self.set_dnd(False if do_not_disturb is None else do_not_disturb)
        for name in ('hyprctl.log', 'noctalia.log', 'eval.log', 'on_eval', 'on_reload'):
            (self.fake_bin / name).unlink(missing_ok=True)
        os.environ.update(variables)
        for key in ('EVAL_ERROR', 'EVAL_IGNORES', 'DND_ERROR', 'CAFFEINE_ERROR',
                    'CONFIG_ERRORS', 'DND_STATUS_ANSWER'):
            if key not in variables:
                os.environ.pop(key, None)

    @staticmethod
    def encode(leaves: Dict[str, Any]) -> str:
        lines = []
        for leaf, value in leaves.items():
            if isinstance(value, bool):
                lines.append(f'{leaf}=bool:{"true" if value else "false"}')
            else:
                lines.append(f'{leaf}=float:{value}')
        return '\n'.join(lines) + ('\n' if lines else '')

    def set_leaves(self, leaves: Dict[str, Any]) -> None:
        (self.fake_bin / 'state').write_text(self.encode(leaves), encoding='utf-8')

    def eval_applies(self, leaves: Dict[str, Any]) -> None:
        """Force the leaves an eval leaves behind, whatever it asked for.

        The fake already honours an eval by looking up the keys it knows, so this
        is only for overriding that: a test that wants one outcome no matter what
        was sent.
        """
        (self.fake_bin / 'on_eval').write_text(self.encode(leaves), encoding='utf-8')

    def ignores_evals(self) -> None:
        """A compositor that answers ok and changes nothing."""
        os.environ['EVAL_IGNORES'] = '1'

    def focuses(self) -> None:
        """A session that is already focused, without focus mode having been run."""
        self.set_leaves(FOCUSED_LEAVES)

    def set_dnd(self, state: bool) -> None:
        (self.fake_bin / 'dnd').write_text('on\n' if state else 'off\n', encoding='utf-8')

    def dnd_now(self) -> str:
        return (self.fake_bin / 'dnd').read_text(encoding='utf-8').strip()

    def leaves_now(self) -> Dict[str, Any]:
        found: Dict[str, Any] = {}
        for line in (self.fake_bin / 'state').read_text(encoding='utf-8').splitlines():
            leaf, _, stored = line.partition('=')
            kind, _, value = stored.partition(':')
            if kind == 'bool':
                found[leaf] = value == 'true'
            elif kind == 'float':
                found[leaf] = float(value)
            else:
                found[leaf] = value
        return found

    def evals_sent(self) -> List[str]:
        path = self.fake_bin / 'eval.log'
        return path.read_text(encoding='utf-8').splitlines() if path.is_file() else []

    def remove_binary(self, name: str) -> None:
        (self.fake_bin / name).unlink()

    def logged(self, name: str) -> List[List[str]]:
        """Every logged invocation of one fake, as the argument vector it was called with."""
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
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *argv: str) -> Tuple[int, Dict[str, Any], str]:
        code, out, err = self.run_cli(*argv, '--json')
        return code, json.loads(out), err

    @property
    def settings_path(self) -> Path:
        return configstore.user_path('settings', os.environ)

    def settings(self) -> Dict[str, Any]:
        return read_json(self.settings_path)

    def record(self) -> Dict[str, Any]:
        return self.settings().get('modes', {}).get('focus', {})


class SwitchingItOn(Sandbox):
    def test_on_sends_exactly_the_recorded_eval(self):
        self.session()
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual([FOCUSED_LUA], self.evals_sent())

    def test_the_eval_argv_is_the_documented_one(self):
        self.session()
        self.run_cli('on')
        self.assertIn(['hyprctl', 'eval', FOCUSED_LUA], self.logged('hyprctl.log'))

    def test_it_never_sends_the_keyword_command_the_manual_still_documents(self):
        self.session()
        self.run_cli('on')
        for call in self.logged('hyprctl.log'):
            self.assertNotEqual('keyword', call[1] if len(call) > 1 else None)

    def test_on_sets_do_not_disturb_through_the_shells_own_verb(self):
        self.session()
        self.run_cli('on')
        self.assertIn(['noctalia', 'msg', 'notification-dnd-set', 'on'],
                      self.logged('noctalia.log'))
        self.assertEqual('on', self.dnd_now())

    def test_on_enables_caffeine_through_the_allowlisted_verb(self):
        self.session()
        self.run_cli('on')
        self.assertIn(['noctalia', 'msg', 'caffeine-enable'], self.logged('noctalia.log'))

    def test_no_caffeine_sends_no_caffeine_verb_at_all(self):
        self.session()
        code, out, _err = self.run_cli('on', '--no-caffeine')
        self.assertEqual(0, code)
        self.assertEqual([], [call for call in self.logged('noctalia.log')
                              if 'caffeine' in ' '.join(call)])
        self.assertIn('caffeine left alone', out)

    def test_on_records_the_state_it_replaced(self):
        self.session(do_not_disturb=True)
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual({'active': True,
                          'previous': {'do_not_disturb': True,
                                       'leaves': UNFOCUSED_LEAVES}}, self.record())

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

    def test_it_writes_no_file_anywhere(self):
        # Focus mode is runtime state. A renderer would make it survive a relogin,
        # and a mode that re-armed itself at login would suppress notifications
        # nobody asked it to suppress.
        self.session()
        self.run_cli('on')
        self.assertEqual([], sorted(self.config_home.rglob('*')))
        self.assertEqual(['settings.json'], [path.name for path in self.state_dir.iterdir()])

    def test_on_verifies_against_what_the_session_answers(self):
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertEqual('matches', report['verdict'])
        self.assertEqual(['do not disturb', 'decoration:dim_inactive',
                          'decoration:dim_strength'],
                         [check['check'] for check in report['checks']])

    def test_a_second_on_keeps_the_original_restore_point(self):
        self.session()
        self.run_cli('on')
        first = self.record()
        self.run_cli('on')
        self.assertEqual(first, self.record())

    def test_a_second_on_says_it_was_already_on(self):
        self.session()
        self.run_cli('on')
        code, out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertIn('still on', out)

    def test_dry_run_reads_the_session_and_sends_nothing(self):
        self.session()
        code, out, _err = self.run_cli('on', '--dry-run')
        self.assertEqual(0, code)
        self.assertEqual([], self.evals_sent())
        # Reading is not sending: the dry run has to read the state it would
        # replace, or it could not report it. What must not happen is a verb that
        # changes anything.
        self.assertEqual([], [call for call in self.logged('noctalia.log')
                              if 'notification-dnd-status' not in ' '.join(call)])
        self.assertIn(['noctalia', 'msg', 'notification-dnd-status'],
                      self.logged('noctalia.log'))
        self.assertFalse(self.settings_path.exists())
        self.assertIn(FOCUSED_LUA, out)
        self.assertIn('nothing was sent', out)

    def test_dry_run_still_reports_the_state_it_would_replace(self):
        self.session(do_not_disturb=True)
        _code, report, _err = self.run_json('on', '--dry-run')
        self.assertTrue(report['dry_run'])
        self.assertIs(True, report['previous']['do_not_disturb'])
        self.assertEqual(UNFOCUSED_LEAVES, report['previous']['leaves'])
        self.assertIs(False, report['applied'])

    def test_a_settings_file_from_before_part_3_still_works(self):
        self.settings_path.write_text(json.dumps(
            {'version': 1, 'preset': 'glass',
             'effects': {'blur': True, 'transparency': True, 'animations': True,
                         'shadows': True},
             'theme': {'colour_preset': 'midnight-glass', 'intensity': 'soft'},
             'animation': {'preset': 'bouncy', 'speed': 1.5, 'reduce_motion': False,
                           'event_overrides': {'fadeDim': False}}}), encoding='utf-8')
        self.session()
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        settings = self.settings()
        self.assertEqual('soft', settings['theme']['intensity'])
        self.assertEqual(1.5, settings['animation']['speed'])
        self.assertEqual({'fadeDim': False}, settings['animation']['event_overrides'])
        self.assertTrue(settings['modes']['focus']['active'])


class SwitchingItOff(Sandbox):
    def focus_first(self) -> None:
        """Switch focus mode on against a session that was not focused."""
        self.run_cli('on')

    def test_off_restores_the_dim_it_replaced(self):
        self.session()
        self.focus_first()
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertEqual([FOCUSED_LUA,
                          'hl.config({ decoration = { dim_inactive = true, '
                          'dim_strength = 0.08 } })'], self.evals_sent())
        self.assertEqual(UNFOCUSED_LEAVES, self.leaves_now())

    def test_off_restores_a_do_not_disturb_that_was_already_on(self):
        # Restoring is not the same as turning off: a person who had Do Not Disturb
        # on before focusing has it on afterwards, and the record is what says so.
        self.session(do_not_disturb=True)
        self.focus_first()
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertEqual('on', self.dnd_now())
        self.assertIn(['noctalia', 'msg', 'notification-dnd-set', 'on'],
                      self.logged('noctalia.log'))

    def test_off_turns_do_not_disturb_off_when_it_was_off(self):
        self.session()
        self.focus_first()
        self.run_cli('off')
        self.assertEqual('off', self.dnd_now())

    def test_off_disables_caffeine_and_says_it_cannot_read_it_back(self):
        self.session()
        self.focus_first()
        code, out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertIn(['noctalia', 'msg', 'caffeine-disable'], self.logged('noctalia.log'))
        self.assertIn('no verb that reports it', out)

    def test_off_after_no_caffeine_leaves_caffeine_alone(self):
        self.session()
        self.run_cli('on', '--no-caffeine')
        code, _out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertEqual([], [call for call in self.logged('noctalia.log')
                              if 'caffeine-disable' in ' '.join(call)])

    def test_off_clears_the_record(self):
        self.session()
        self.focus_first()
        self.run_cli('off')
        self.assertEqual({'active': False}, self.record())

    def test_off_with_nothing_recorded_sends_nothing_but_still_reports(self):
        self.session()
        code, out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertIn('already off', out)
        self.assertEqual([], self.evals_sent())
        self.assertEqual([], self.logged('noctalia.log'))

    def test_off_refuses_a_record_it_cannot_honour(self):
        self.session()
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'modes': {'focus': {'active': True}}}, os.environ)
        code, out, err = self.run_cli('off')
        self.assertEqual(2, code)
        self.assertIn('--forget', out + err)
        self.assertEqual([], self.evals_sent())
        self.assertTrue(self.record()['active'])

    def test_forget_clears_the_record_and_sends_nothing(self):
        self.session()
        self.focus_first()
        code, out, _err = self.run_cli('off', '--forget')
        self.assertEqual(0, code)
        self.assertIn('nothing was sent', out)
        self.assertEqual({'active': False}, self.record())
        # The session is left exactly as it was: --forget is about a record.
        self.assertEqual(FOCUSED_LEAVES, self.leaves_now())
        self.assertEqual('on', self.dnd_now())

    def test_forget_with_nothing_recorded_is_not_an_error(self):
        self.session()
        code, out, _err = self.run_cli('off', '--forget')
        self.assertEqual(0, code)
        self.assertIn('nothing recorded', out)

    def test_a_leaf_that_could_not_be_read_before_is_left_alone_and_said_so(self):
        self.set_leaves({'decoration:dim_inactive': True})   # dim_strength unreadable
        code, out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertIsNone(self.record()['previous']['leaves']['decoration:dim_strength'])
        code, out, err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertIn('decoration:dim_strength', out + err)
        self.assertIn('left as it is', out + err)

    def test_a_leaf_that_was_never_read_is_unverified_rather_than_a_difference(self):
        # Blaming the session for the one leaf the tool said it could not restore
        # would be a difference nobody caused, and it would push the exit code to 1
        # on a run that did everything it could.
        self.set_leaves({'decoration:dim_inactive': True})
        self.run_cli('on')
        _code, report, _err = self.run_json('off')
        strength = [check for check in report['checks']
                    if check['check'] == 'decoration:dim_strength'][0]
        self.assertEqual(modes.UNVERIFIED, strength['verdict'])
        self.assertIsNone(strength['expected'])
        self.assertEqual(0, report['exit'])

    def test_dry_run_off_sends_nothing(self):
        self.session()
        self.focus_first()
        before = self.evals_sent()
        code, out, _err = self.run_cli('off', '--dry-run')
        self.assertEqual(0, code)
        self.assertEqual(before, self.evals_sent())
        self.assertTrue(self.record()['active'])
        self.assertIn('nothing was sent', out)

    def test_toggle_goes_there_and_back(self):
        self.session()
        code, out, _err = self.run_cli('toggle')
        self.assertEqual(0, code)
        self.assertIn('focus mode on', out)
        self.assertTrue(self.record()['active'])
        code, out, _err = self.run_cli('toggle')
        self.assertEqual(0, code)
        self.assertIn('focus mode off', out)
        self.assertEqual({'active': False}, self.record())

    def test_toggle_reports_which_way_it_went(self):
        self.session()
        _code, report, _err = self.run_json('toggle')
        self.assertIs(False, report['toggled_from'])
        self.assertEqual('toggle (on)', report['command'])


class WhenSomethingRefuses(Sandbox):
    def test_a_compositor_that_refuses_the_dim_stops_everything_else(self):
        self.session(EVAL_ERROR="unknown config key 'dim_strength'")
        code, out, err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertIn('unknown config key', out + err)
        # The one call that reached the shell is the read focus mode does before it
        # changes anything; no verb that sets something was sent.
        self.assertEqual([['noctalia', 'msg', 'notification-dnd-status']],
                         self.logged('noctalia.log'))
        self.assertFalse(self.settings_path.exists())
        self.assertEqual('off', self.dnd_now())

    def test_the_refusal_quotes_the_compositor_and_reads_its_error_list(self):
        self.session(EVAL_ERROR="unknown config key 'dim_strength'",
                     CONFIG_ERRORS='Config error: unknown config key')
        _code, report, _err = self.run_json('on')
        self.assertIs(False, report['ok'])
        self.assertIn('refused the dim', report['error'])
        self.assertIn('after_failed_eval', report['configerrors'])
        self.assertIn('unknown config key', report['configerrors']['after_failed_eval'][0])

    def test_a_shell_that_refuses_do_not_disturb_puts_the_dim_back(self):
        self.session(DND_ERROR='bad verb')
        code, out, err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertEqual(UNFOCUSED_LEAVES, self.leaves_now())
        self.assertEqual(2, len(self.evals_sent()))
        self.assertIn('was put back', out + err)
        self.assertFalse(self.settings_path.exists())

    def test_a_refused_do_not_disturb_never_enables_a_caffeine_nobody_can_switch_off(self):
        self.session(DND_ERROR='bad verb')
        _code, report, _err = self.run_json('on')
        self.assertEqual([], [call for call in self.logged('noctalia.log')
                              if 'caffeine' in ' '.join(call)])
        self.assertIs(False, report['rollback']['caffeine_sent'])
        self.assertIn('undo the focus dim',
                      [step.get('label') for step in report['steps']])

    def test_a_compositor_that_says_ok_and_changes_nothing_is_reported_not_passed(self):
        self.session()
        self.ignores_evals()
        code, out, err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertIn('does not run it', out + err)
        self.assertEqual(UNFOCUSED_LEAVES, self.leaves_now())

    def test_the_dim_and_the_record_stay_when_the_session_disagrees(self):
        # Rolling back here would leave the record describing one state and the
        # compositor another, which is worse than the disagreement it was meant to
        # fix; the report says which leaf differs and the exit code says the request
        # did not take.
        self.session()
        self.ignores_evals()
        _code, report, _err = self.run_json('on')
        self.assertEqual('differs', report['verdict'])
        self.assertIs(False, report['ok'])
        self.assertIs(True, report['applied'])
        self.assertTrue(self.record()['active'])
        self.assertTrue(any('left as they are' in note for note in report['notes']))

    def test_a_compositor_that_sets_something_else_is_a_difference_too(self):
        self.session()
        self.eval_applies({'decoration:dim_inactive': True, 'decoration:dim_strength': 0.3})
        code, _out, _err = self.run_cli('on')
        self.assertEqual(1, code)
        self.assertEqual(0.3, self.leaves_now()['decoration:dim_strength'])

    def test_caffeine_that_is_unavailable_still_leaves_the_rest_of_the_mode_on(self):
        # The inhibitor answers "error: caffeine protocol unavailable" when neither
        # the Wayland protocol nor logind inhibition is there. That is a missing
        # capability, not a refused mode: the dim and Do Not Disturb still work.
        self.session(CAFFEINE_ERROR='caffeine protocol unavailable')
        code, out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual('on', self.dnd_now())
        self.assertEqual(FOCUSED_LEAVES, self.leaves_now())
        self.assertTrue(self.record()['active'])
        self.assertIn('caffeine protocol unavailable', out)

    def test_the_report_says_caffeine_may_not_be_held(self):
        self.session(CAFFEINE_ERROR='caffeine protocol unavailable')
        _code, report, _err = self.run_json('on')
        self.assertTrue(any('may not be held off' in note for note in report['notes']))
        self.assertEqual('matches', report['verdict'])

    def test_no_compositor_is_unverified_and_still_sets_the_shell_half(self):
        self.remove_binary('hyprctl')
        self.session()
        code, out, err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual('on', self.dnd_now())
        self.assertIn('could not be checked', err)
        # The closing line has to sound like what was confirmed, not like what was
        # intended: only the shell half of this mode could be checked.
        self.assertIn('as far as this tool could tell', out)
        self.assertNotIn('and the session agrees', out)

    def test_no_compositor_leaves_the_dim_checks_unverified_not_failed(self):
        self.remove_binary('hyprctl')
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertEqual('unverified', report['verdict'])
        dim_checks = [check for check in report['checks'] if check['check'].startswith('decoration')]
        self.assertEqual(2, len(dim_checks))
        for check in dim_checks:
            self.assertEqual(modes.UNVERIFIED, check['verdict'])
            self.assertIsNone(check['actual'])
            self.assertIn('not on PATH', check['detail'])
        self.assertEqual(modes.MATCHES,
                         [check for check in report['checks']
                          if check['check'] == 'do not disturb'][0]['verdict'])

    def test_no_shell_is_unverified_and_still_sets_the_dim(self):
        self.remove_binary('noctalia')
        self.session()
        code, _out, _err = self.run_cli('on')
        self.assertEqual(0, code)
        self.assertEqual(FOCUSED_LEAVES, self.leaves_now())
        self.assertTrue(self.record()['active'])

    def test_no_shell_records_a_null_it_can_honour_later(self):
        # A null do_not_disturb means "never read", so `off` says it is turning Do
        # Not Disturb off rather than claiming it restored a state it never saw.
        self.remove_binary('noctalia')
        self.session()
        self.run_cli('on')
        self.assertIsNone(self.record()['previous']['do_not_disturb'])
        self.add_binary_back()
        self.set_dnd(True)
        code, out, _err = self.run_cli('off')
        self.assertEqual(0, code)
        self.assertIn('never read', out)
        self.assertEqual('off', self.dnd_now())

    def add_binary_back(self) -> None:
        script = self.fake_bin / 'noctalia'
        script.write_text(FAKE_NOCTALIA, encoding='utf-8')
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


class DriftIsReportedNotHidden(Sandbox):
    def focus_first(self) -> None:
        """Switch focus mode on against a session that was not focused."""
        self.run_cli('on')

    def test_status_agrees_when_the_session_runs_what_was_asked(self):
        self.session()
        self.focus_first()
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('recorded:      on', out)
        self.assertIn('agrees', out)

    def test_status_reports_the_drift_a_reload_causes(self):
        # Any reload re-parses the generated glass.lua, which puts the intensity's
        # own dim back. The record still says focus mode is on, and the honest
        # answer is that the session disagrees.
        self.session()
        self.focus_first()
        self.set_leaves(UNFOCUSED_LEAVES)
        code, out, err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('disagrees', out)
        self.assertIn('which is what a reload does', out + err)

    def test_the_drift_names_both_values(self):
        self.session()
        self.focus_first()
        self.set_leaves(UNFOCUSED_LEAVES)
        _code, report, _err = self.run_json('status')
        self.assertEqual('differs', report['verdict'])
        strength = [check for check in report['checks']
                    if check['check'] == 'decoration:dim_strength'][0]
        self.assertEqual(0.5, strength['expected'])
        self.assertEqual(0.08, strength['actual'])

    def test_do_not_disturb_switched_off_behind_its_back_is_drift_too(self):
        self.session()
        self.focus_first()
        self.set_dnd(False)
        _code, report, _err = self.run_json('status')
        self.assertEqual('differs', report['verdict'])
        dnd = [check for check in report['checks'] if check['check'] == 'do not disturb'][0]
        self.assertIs(False, dnd['actual'])

    def test_status_when_off_compares_against_the_intensitys_own_dim(self):
        # This is how a dim left behind shows up: nothing is recorded, and the
        # session is running the focus value anyway.
        self.session()
        self.focuses()
        code, out, err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('recorded:      off', out)
        self.assertIn('disagrees', out)
        self.assertIn('left behind', out + err)

    def test_status_when_off_and_unfocused_agrees(self):
        self.session()
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('agrees', out)
        self.assertIn('frosted', out)

    def test_status_names_the_intensity_it_compared_against(self):
        configstore.save('settings', {'version': 1, 'preset': 'glass',
                                      'effects': {'blur': True, 'transparency': True,
                                                  'animations': True, 'shadows': True},
                                      'theme': {'colour_preset': 'midnight-glass',
                                                'intensity': 'soft'}}, os.environ)
        self.session(leaves={'decoration:dim_inactive': True, 'decoration:dim_strength': 0.1})
        code, out, _err = self.run_cli('status')
        self.assertEqual(0, code)
        self.assertIn('soft', out)
        self.assertIn('agrees', out)

    def test_an_unknown_leaf_is_unverified_rather_than_read_as_a_value(self):
        self.session()
        self.focus_first()
        self.set_leaves({})
        code, report, _err = self.run_json('status')
        self.assertEqual(0, code)
        self.assertEqual('unverified', report['verdict'])
        for check in report['checks']:
            if check['check'].startswith('decoration'):
                self.assertEqual(modes.UNVERIFIED, check['verdict'])
                self.assertIn('no such option', check['detail'])

    def test_a_shell_that_answers_garbage_is_unverified_not_guessed(self):
        # notification-dnd-status prints exactly "on" or "off"; anything else means
        # the shell could not be asked, and guessing would turn a version mismatch
        # into a claim about the person's notifications.
        self.session(DND_STATUS_ANSWER='enabled (by policy)')
        self.focus_first()
        _code, report, _err = self.run_json('status')
        dnd = [check for check in report['checks'] if check['check'] == 'do not disturb'][0]
        self.assertEqual(modes.UNVERIFIED, dnd['verdict'])
        self.assertIsNone(dnd['actual'])

    def test_no_compositor_at_all_is_unverified_and_still_exits_zero(self):
        self.remove_binary('hyprctl')
        self.session()
        code, report, _err = self.run_json('status')
        self.assertEqual(0, code)
        self.assertEqual('unverified', report['verdict'])

    def test_status_exits_zero_even_when_the_session_disagrees(self):
        # A status command that exits non-zero because the session disagrees cannot
        # be told apart from one that could not run; its siblings' `current`
        # subcommands exit 0 whatever they find.
        self.session()
        self.focus_first()
        self.set_leaves(UNFOCUSED_LEAVES)
        code, _out, _err = self.run_cli('status')
        self.assertEqual(0, code)


class TheReport(Sandbox):
    def test_json_is_one_object_and_the_prose_is_not_in_it(self):
        self.session()
        code, out, err = self.run_cli('on', '--json')
        self.assertEqual(0, code)
        report = json.loads(out)
        self.assertEqual('iarch-focus', report['tool'])
        for key in ('command', 'mode', 'ok', 'previous', 'target', 'steps', 'checks',
                    'verdict', 'settings', 'rollback', 'error', 'exit'):
            self.assertIn(key, report)
        self.assertNotIn('focus mode is on', out)
        self.assertEqual('', err)

    def test_warnings_go_to_stderr_so_a_pipe_still_gets_clean_json(self):
        self.remove_binary('hyprctl')
        self.session()
        _code, out, err = self.run_cli('status', '--json')
        json.loads(out)
        self.assertIn('warning:', err)

    def test_the_steps_carry_the_exact_vectors_that_were_sent(self):
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertEqual(['hyprctl', 'eval', FOCUSED_LUA], report['steps'][0]['argv'])
        verbs = [step['verb'] for step in report['steps'] if 'verb' in step]
        self.assertEqual(['notification-dnd-set on', 'caffeine-enable'], verbs)

    def test_the_settings_block_names_the_file_it_wrote(self):
        self.session()
        _code, report, _err = self.run_json('on')
        self.assertIs(True, report['settings']['changed'])
        self.assertIn('settings.json', report['settings']['path'])

    def test_recording_the_same_state_twice_is_not_a_change(self):
        self.session()
        self.run_cli('on')
        _code, report, _err = self.run_json('on')
        self.assertIs(False, report['settings']['changed'])

    def test_no_subcommand_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                cli.main([])
        self.assertEqual(2, caught.exception.code)

    def test_an_unknown_subcommand_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                cli.main(['dim'])
        self.assertEqual(2, caught.exception.code)


if __name__ == '__main__':
    unittest.main()
