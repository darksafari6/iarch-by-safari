"""Prove the startup module runs what the record says, and nothing else.

``.config/hypr/startup.lua`` is the only file in the payload that starts
programs, and it is the one place where a mistake is quiet: Hyprland's executor
forks ``/bin/sh -c`` with the child's stdout and stderr sent to ``/dev/null``
(``Executor.cpp:198-205`` at v0.57.2), so a command that fails leaves no trace
and a command nobody needed looks like one that worked. Hyprland does refuse an
unknown ``hl.on`` event name, but it refuses the *entire configuration* and it
does that at login, which is the wrong time for the person who edited it to find
out.

So these tests check the render against ``data/design/startup.json`` -- the
bindings, the event names and the reason beside every command -- and then check
the two things a renderer could get right and still break:

* the lines both installers rewrite with ``sed``. ``install.sh:1047-1049`` and
  ``fedora_install.sh:845-847`` flip ``local enable_nvidia_optional = false`` as a
  whole line, and ``fedora_install.sh:834`` replaces *every* line containing
  ``polkit-gnome-authentication-agent-1`` with a quoted table entry. A render that
  turned the command table into calls, or that quoted the agent's name in a
  comment, would leave the record valid and the Fedora install unparseable -- so
  the anchors are asserted in the rendered text, the Fedora rewrite is applied in
  memory and the result is parsed;
* what the module does *not* start. hypridle, hyprlock and a second notification
  daemon are each recorded with the reason they are absent, and a test asserts
  none of them is spawned, because a second daemon on one seat or one bus name is
  the failure that looks like a working session.

Six groups: the recorded surface, the render, the installer rewrites, the
refusals, the shipped file, and what it does not start.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_startup_lua as gen  # noqa: E402
from iarch.lib import configstore  # noqa: E402

RECORD_PATH = ROOT / 'data' / 'design' / 'startup.json'
SCHEMA_PATH = ROOT / 'data' / 'schemas' / 'startup.schema.json'
SHIPPED = ROOT / '.config' / 'hypr' / 'startup.lua'
HYPRLAND_LUA = ROOT / '.config' / 'hypr' / 'hyprland.lua'
TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
INSTALL_SH = ROOT / 'install.sh'
FEDORA_SH = ROOT / 'fedora_install.sh'

LUAC = next((name for name in ('luac', 'luac5.4', 'luac5.3', 'luac5.1')
             if shutil.which(name)), None)
try:
    from luaparser import ast as lua_ast  # noqa: E402

    HAVE_LUAPARSER = True
except ImportError:  # pragma: no cover - depends on the host
    lua_ast = None
    HAVE_LUAPARSER = False

try:
    import jsonschema  # noqa: E402

    HAVE_JSONSCHEMA = True
except ImportError:  # pragma: no cover - depends on the host
    HAVE_JSONSCHEMA = False

# The polkit agent's binary name: the string fedora_install.sh matches on, and the
# one string that may appear on exactly one line of the render.
POLKIT = 'polkit-gnome-authentication-agent-1'
NVIDIA_FLAG = 'local enable_nvidia_optional = false'


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def record() -> Dict[str, Any]:
    return read_json(RECORD_PATH)


def mutate(base: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """A deep copy of ``base`` with ``path`` (dotted, list indices allowed) replaced."""
    clone = json.loads(json.dumps(base))
    node = clone
    keys = path.split('.')

    def step(container, key):
        return container[int(key)] if isinstance(container, list) else container[key]

    for key in keys[:-1]:
        node = step(node, key)
    if isinstance(node, list):
        node[int(keys[-1])] = value
    else:
        node[keys[-1]] = value
    return clone


def code_only(text: str) -> str:
    """The render with its comment lines dropped, so prose cannot look like a call."""
    return '\n'.join(line for line in text.splitlines()
                     if not line.strip().startswith('--'))


def exec_block(text: str) -> List[str]:
    """The quoted commands inside ``local exec_once = { … }``, in order."""
    match = re.search(r'local exec_once = \{(.*?)\n\}', text, re.S)
    if match is None:
        return []
    body = '\n'.join(line for line in match.group(1).splitlines()
                     if not line.strip().startswith('--'))
    return re.findall(r'"((?:[^"\\]|\\.)*)"', body)


def env_calls(text: str) -> List[Tuple[str, ...]]:
    """Every ``hl.env`` argument list in the render, as strings."""
    return [tuple(part.strip() for part in body.split(','))
            for body in re.findall(r'hl\.env\(((?:[^()]*))\)', code_only(text))]


class Sandbox(unittest.TestCase):
    """A base that keeps writes and backups inside a temporary directory."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        state = self.tmp / 'state'
        state.mkdir()
        patch = {
            'IARCH_CONFIG_DIR': str(self.tmp / 'config'),
            'IARCH_STATE_DIR': str(state),
        }
        for key, value in patch.items():
            self.addCleanup(os.environ.pop, key, None)
            os.environ[key] = value

    def run_cli(self, argv: List[str]) -> Tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gen.main(argv)
        return code, out.getvalue(), err.getvalue()

    def write_record(self, document: Dict[str, Any]) -> Path:
        path = self.tmp / 'startup.json'
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False),
                        encoding='utf-8')
        return path


class TheRecordedSurface(Sandbox):
    def test_the_record_validates_against_its_schema(self):
        if not HAVE_JSONSCHEMA:
            self.skipTest('jsonschema is not installed')
        schema = read_json(SCHEMA_PATH)
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(record()))
        self.assertEqual([], [e.message for e in errors])

    def test_every_event_the_module_registers_is_one_hyprland_dispatches(self):
        rec = record()
        known = set(rec['events']['known'])
        self.assertEqual([], [event for event in rec['events']['used'] if event not in known],
                         'an event Hyprland would refuse the whole configuration for')
        self.assertIn('hyprland.start', known)

    def test_the_known_events_are_the_pinned_release_list(self):
        # 36 names at v0.57.2 (LuaEventHandler.cpp:251-292). The count is asserted
        # so a future record cannot quietly shorten the list to whatever the render
        # happens to use: the list is what makes an unknown name checkable offline.
        rec = record()
        self.assertEqual(36, len(rec['events']['known']))
        self.assertEqual(len(set(rec['events']['known'])), len(rec['events']['known']))
        self.assertIn('src/config/lua/LuaEventHandler.cpp', rec['events']['source'])

    def test_the_render_uses_only_the_recorded_bindings(self):
        rec = record()
        used = {'hl.' + name for name in re.findall(r'\bhl\.([a-z_]+)\s*\(', code_only(gen.render(rec)))}
        self.assertEqual(set(rec['bindings']), used,
                         'a binding the record does not describe, or one it describes '
                         'that the render never uses')

    def test_the_record_pins_the_release_the_glass_tokens_pin(self):
        self.assertEqual(read_json(TOKENS_PATH)['hyprland']['verified_against'],
                         record()['verified_against'])

    def test_the_entry_point_is_the_file_that_ships(self):
        rec = record()
        self.assertEqual('.config/hypr/startup.lua', rec['entry_point']['file'])
        self.assertTrue(SHIPPED.is_file())
        self.assertEqual(SHIPPED, ROOT / rec['entry_point']['file'])

    def test_the_cited_require_line_is_the_one_that_requires_it(self):
        cited = record()['entry_point']['required_by']
        path, _, line = cited.partition(':')
        self.assertEqual('.config/hypr/hyprland.lua', path)
        text = (ROOT / path).read_text(encoding='utf-8').splitlines()
        self.assertIn('require("startup")', text[int(line) - 1],
                      f'{cited} no longer requires the startup module')

    def test_the_module_is_not_cleared_from_the_reload_cache(self):
        # hyprland.lua:9 clears package.loaded for the modules whose binds and rules
        # have to re-register on a reload. startup is not one of them, and the record
        # says so as a constant: were it cleared, every reload would re-export the
        # environment and register a second handler for an event that fires once.
        rec = record()
        self.assertFalse(rec['entry_point']['cache_cleared_on_reload'])
        clear_line = HYPRLAND_LUA.read_text(encoding='utf-8').splitlines()[8]
        self.assertIn('package.loaded[mod] = nil', HYPRLAND_LUA.read_text(encoding='utf-8'))
        self.assertIn('ipairs({', clear_line)
        self.assertNotIn('"startup"', clear_line)

    def test_the_executor_recorded_is_the_one_upstream_forks(self):
        executor = record()['executor']
        self.assertEqual('/bin/sh -c', executor['shell'])
        self.assertIn('src/config/supplementary/executor/Executor.cpp', executor['source'])
        self.assertTrue(executor['consequences'])


class TheRender(Sandbox):
    def rendered(self, rec: Optional[Dict[str, Any]] = None) -> str:
        return gen.render(rec if rec is not None else record())

    def test_every_recorded_variable_is_exported_in_order(self):
        rec = record()
        text = self.rendered(rec)
        names = [call[0] for call in env_calls(text) if call]
        expected = [entry['name'] for entry in rec['env']]
        for group in rec['optional_groups']:
            expected += [entry['name'] for entry in group['env']]
        self.assertEqual([f'"{name}"' for name in expected], names[:len(expected)])

    def test_the_dbus_flag_is_passed_exactly_where_the_record_asks(self):
        rec = record()
        text = self.rendered(rec)
        for entry in rec['env']:
            with self.subTest(variable=entry['name']):
                call = next((call for call in env_calls(text)
                             if call and call[0] == f'"{entry["name"]}"'), None)
                self.assertIsNotNone(call, f'{entry["name"]} is not exported')
                self.assertEqual(3 if entry.get('dbus') else 2, len(call),
                                 'hl.env treats a missing third argument as false, so an '
                                 'explicit false would only restate the binding')

    def test_the_session_variables_are_exported_to_dbus_and_the_vendor_ones_are_not(self):
        rec = record()
        exported = {entry['name'] for entry in rec['env'] if entry.get('dbus')}
        self.assertEqual({'XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE'}, exported)
        for group in rec['optional_groups']:
            for entry in group['env']:
                self.assertNotIn('dbus', entry,
                                 'a vendor variable is read by the driver, not by a '
                                 'dbus-activated helper')

    def test_every_recorded_command_is_emitted_once_in_order(self):
        rec = record()
        emitted = exec_block(self.rendered(rec))
        self.assertEqual([entry['command'] for entry in rec['exec_once']], emitted)

    def test_no_command_is_emitted_that_the_record_does_not_carry(self):
        rec = record()
        allowed = {entry['command'] for entry in rec['exec_once']}
        self.assertEqual([], [command for command in exec_block(self.rendered(rec))
                              if command not in allowed])

    def test_the_handler_registers_the_recorded_event_and_spawns_the_table(self):
        rec = record()
        code = code_only(self.rendered(rec))
        for event in rec['events']['used']:
            self.assertIn(f'hl.on("{event}", function()', code)
        self.assertIn('for _, cmd in ipairs(exec_once) do', code)
        self.assertIn('hl.exec_cmd(cmd)', code)

    def test_nothing_in_the_render_reloads_the_compositor(self):
        # The startup reload the v4 session carried is recorded as removed. It is
        # asserted here because the cost is not cosmetic: a second parse discards
        # runtime state no file records, and a focus mode switched on at login would
        # have its dim undone by the generated glass.lua two seconds later.
        code = code_only(self.rendered())
        self.assertNotIn('hyprctl reload', code)
        self.assertNotIn('hl.config(', code)
        self.assertNotIn('reload', code)

    def test_the_removed_entry_is_named_in_a_comment_with_its_legacy_source(self):
        text = self.rendered()
        for removed in record()['removed']:
            legacy = removed['legacy'].split(' ')[0]
            self.assertIn(legacy, text)
        self.assertIn('removed', text)

    def test_the_optional_group_is_behind_its_flag_and_off(self):
        rec = record()
        text = self.rendered(rec)
        for group in rec['optional_groups']:
            with self.subTest(group=group['name']):
                flag = group['flag']
                self.assertIn(f'local {flag} = false', text.splitlines())
                self.assertIn(f'if {flag} then', text)
                body = text.split(f'if {flag} then', 1)[1].split('\nend', 1)[0]
                self.assertEqual(len(group['env']),
                                 len(re.findall(r'hl\.env\(', body)))

    def test_the_module_returns_true_like_its_siblings(self):
        self.assertEqual('return true', self.rendered().splitlines()[-1])
        self.assertEqual('return true',
                         (ROOT / '.config' / 'hypr' / 'keybind.lua').read_text(
                             encoding='utf-8').strip().splitlines()[-1])

    @unittest.skipUnless(HAVE_LUAPARSER, 'luaparser is not installed')
    def test_luaparser_accepts_the_render(self):
        lua_ast.parse(gen.rendered_text(SHIPPED, self.rendered()))

    def test_the_render_is_stable(self):
        self.assertEqual(self.rendered(), self.rendered())


class WhatTheInstallersRewrite(Sandbox):
    def shipped_lines(self, text: Optional[str] = None) -> List[str]:
        return (text if text is not None else SHIPPED.read_text(encoding='utf-8')).splitlines()

    def test_the_nvidia_flag_is_one_whole_line(self):
        for text, where in ((gen.render(record()), 'the render'),
                            (SHIPPED.read_text(encoding='utf-8'), 'the shipped file')):
            with self.subTest(where=where):
                hits = [line for line in self.shipped_lines(text) if line == NVIDIA_FLAG]
                self.assertEqual(1, len(hits),
                                 'install.sh and fedora_install.sh sed this line as a '
                                 'whole line; a second copy or a changed spelling means '
                                 'the installer warns and ships a session without it')

    def test_the_polkit_command_is_on_exactly_one_line(self):
        for text, where in ((gen.render(record()), 'the render'),
                            (SHIPPED.read_text(encoding='utf-8'), 'the shipped file')):
            with self.subTest(where=where):
                hits = [number for number, line in enumerate(self.shipped_lines(text), 1)
                        if POLKIT in line]
                self.assertEqual(1, len(hits),
                                 'fedora_install.sh replaces every line containing the '
                                 'agent name with a quoted table entry, so a second '
                                 'mention -- in a comment -- would produce a file that '
                                 'does not parse')

    def test_the_record_cites_the_installer_lines_that_still_say_what_it_claims(self):
        for anchor in record()['installer_anchors']:
            with self.subTest(anchor=f"{anchor['file']}:{anchor['lines']}"):
                path = ROOT / anchor['file']
                self.assertTrue(path.is_file(), f'{anchor["file"]} is missing')
                start, _, end = anchor['lines'].partition('-')
                lines = path.read_text(encoding='utf-8').splitlines()
                window = '\n'.join(lines[int(start) - 1:int(end or start)])
                self.assertIn(anchor['anchor'], window,
                              'the anchor is no longer on the cited lines')
                # A sed expression escapes what it replaces -- fedora_install.sh:834
                # carries \\& and \\/ -- so the replacement is looked for both as
                # written and with the escapes taken out.
                unescaped = window.replace('\\', '')
                self.assertIn(anchor['replacement'].strip(), unescaped,
                              'the replacement is no longer on the cited lines')

    def test_the_fedora_replacement_is_a_lua_table_entry(self):
        replacement = next(anchor['replacement'] for anchor in record()['installer_anchors']
                           if not anchor['whole_line'])
        self.assertTrue(replacement.startswith('    "'), replacement)
        self.assertTrue(replacement.endswith('",'), replacement)

    @unittest.skipUnless(HAVE_LUAPARSER, 'luaparser is not installed')
    def test_the_fedora_rewrite_leaves_a_file_that_still_parses(self):
        # The real check behind the two above: apply fedora_install.sh:834 to the
        # render, in memory, and parse the result. A renderer that moved the polkit
        # command out of a table, or quoted the agent name in a comment, fails here
        # rather than on somebody's Fedora install.
        replacement = next(anchor['replacement'] for anchor in record()['installer_anchors']
                           if not anchor['whole_line'])
        rewritten = [replacement if POLKIT in line else line
                     for line in self.shipped_lines(gen.render(record()))]
        text = '\n'.join(rewritten)
        self.assertEqual(1, sum(1 for line in rewritten if 'xfce-polkit' in line))
        self.assertNotIn(POLKIT, text)
        lua_ast.parse(text)

    @unittest.skipUnless(HAVE_LUAPARSER, 'luaparser is not installed')
    def test_the_nvidia_rewrite_leaves_a_file_that_still_parses(self):
        rewritten = ['local enable_nvidia_optional = true' if line == NVIDIA_FLAG else line
                     for line in self.shipped_lines(gen.render(record()))]
        text = '\n'.join(rewritten)
        lua_ast.parse(text)
        group = record()['optional_groups'][0]
        body = text.split(f"if {group['flag']} then", 1)[1].split('\nend', 1)[0]
        self.assertEqual(len(group['env']), len(re.findall(r'hl\.env\(', body)))

    def test_a_comment_naming_the_agent_is_refused(self):
        rec = mutate(record(), 'exec_once.2.note',
                     'Start this before the polkit-gnome-authentication-agent-1 entry.')
        with self.assertRaises(gen.StartupError) as caught:
            gen.render(rec)
        self.assertIn(POLKIT, str(caught.exception))
        self.assertIn('2 times', str(caught.exception))

    def test_a_second_copy_of_the_flag_line_is_refused(self):
        # A second group with its own variables but the same flag: check_record has
        # nothing to say about it, and only the rendered text shows that the line both
        # installers sed now appears twice.
        rec = record()
        clone = json.loads(json.dumps(rec['optional_groups'][0]))
        clone['name'] = 'nvidia_second'
        clone['env'] = [{'name': 'IARCH_SECOND_GROUP', 'value': '1',
                         'why': 'a second group reusing the first group\'s flag'}]
        rec['optional_groups'].append(clone)
        with self.assertRaises(gen.StartupError) as caught:
            gen.render(rec)
        self.assertIn(NVIDIA_FLAG, str(caught.exception))
        self.assertIn('2 times', str(caught.exception))


class Refusals(Sandbox):
    def refuses(self, rec: Dict[str, Any], needle: str) -> str:
        with self.assertRaises(gen.StartupError) as caught:
            gen.render(rec)
        message = str(caught.exception)
        self.assertIn(needle, message)
        return message

    def test_an_event_hyprland_does_not_dispatch_is_refused(self):
        message = self.refuses(mutate(record(), 'events.used.0', 'hyprland.started'),
                               'hyprland.started')
        self.assertIn('36', message, 'the refusal should say how many names are known')

    def test_a_variable_exported_twice_is_refused(self):
        rec = mutate(record(), 'optional_groups.0.env.0.name', 'XDG_SESSION_TYPE')
        message = self.refuses(rec, 'XDG_SESSION_TYPE')
        self.assertIn('twice', message)

    def test_an_empty_command_is_refused(self):
        self.refuses(mutate(record(), 'exec_once.1.command', '   '), 'empty')

    def test_a_command_that_would_be_parsed_as_an_exec_rule_is_refused(self):
        message = self.refuses(mutate(record(), 'exec_once.1.command', '[float] noctalia'),
                               "starts with '['")
        self.assertIn('Executor.cpp', message)

    def test_a_command_with_a_newline_is_refused(self):
        self.refuses(mutate(record(), 'exec_once.1.command', 'noctalia\nreboot'), 'newline')

    def test_an_optional_group_enabled_by_default_is_refused(self):
        self.refuses(mutate(record(), 'optional_groups.0.enabled_by_default', True),
                     'enabled by default')

    def test_a_record_that_cannot_be_read_is_refused(self):
        with self.assertRaises(gen.StartupError):
            gen.load_record(self.tmp / 'absent.json')
        broken = self.tmp / 'broken.json'
        broken.write_text('{', encoding='utf-8')
        with self.assertRaises(gen.StartupError):
            gen.load_record(broken)


class TheShippedFile(Sandbox):
    def test_check_passes_on_the_committed_default(self):
        code, out, err = self.run_cli(['--check'])
        self.assertEqual(0, code, out + err)
        self.assertIn('matches a fresh render', out)

    def test_the_shipped_file_starts_with_the_generated_header(self):
        first = SHIPPED.read_text(encoding='utf-8').splitlines()[0]
        self.assertTrue(configstore.is_header_line(first), first)

    def test_the_shipped_file_is_the_render(self):
        self.assertEqual(gen.rendered_text(SHIPPED, gen.render(record())),
                         SHIPPED.read_text(encoding='utf-8'))

    def test_print_writes_what_check_compares(self):
        code, out, err = self.run_cli(['--print'])
        self.assertEqual(0, code, err)
        self.assertEqual(SHIPPED.read_text(encoding='utf-8'), out)

    def test_output_writes_the_module_and_reports_what_it_emitted(self):
        target = self.tmp / 'live' / 'startup.lua'
        target.parent.mkdir()
        code, out, err = self.run_cli(['--output', str(target)])
        self.assertEqual(0, code, out + err)
        self.assertEqual(SHIPPED.read_text(encoding='utf-8'),
                         target.read_text(encoding='utf-8'))
        rec = record()
        self.assertIn(f"{len(rec['env'])} variables", out)
        self.assertIn(f"{len(rec['exec_once'])} commands", out)

    def test_the_default_target_is_under_the_config_dir(self):
        path = gen.target_path({'IARCH_CONFIG_DIR': str(self.tmp / 'elsewhere')})
        self.assertEqual(self.tmp / 'elsewhere' / 'hypr' / 'startup.lua', path)

    def test_a_refused_record_exits_two_and_writes_nothing(self):
        target = self.tmp / 'never.lua'
        bad = self.write_record(mutate(record(), 'events.used.0', 'hyprland.started'))
        code, out, err = self.run_cli(['--record', str(bad), '--output', str(target)])
        self.assertEqual(2, code)
        self.assertIn('hyprland.started', err)
        self.assertFalse(target.exists())

    def test_a_missing_record_exits_two(self):
        code, out, err = self.run_cli(['--record', str(self.tmp / 'absent.json'), '--check'])
        self.assertEqual(2, code)
        self.assertIn('startup-lua:', err)

    def test_check_fails_when_the_committed_default_drifts(self):
        original = SHIPPED.read_text(encoding='utf-8')
        self.addCleanup(SHIPPED.write_text, original, encoding='utf-8')
        SHIPPED.write_text(original.replace('"noctalia",', '"noctalia --replace",', 1),
                           encoding='utf-8')
        code, out, err = self.run_cli(['--check'])
        self.assertEqual(1, code)
        self.assertIn('--write-repo-default', err)


class WhatItDoesNotStart(Sandbox):
    def test_no_recorded_absent_daemon_is_spawned(self):
        commands = exec_block(gen.render(record()))
        joined = '\n'.join(commands)
        for name, needle in (('hypridle', 'hypridle'), ('hyprlock', 'hyprlock'),
                             ('a second notification daemon', 'mako'),
                             ('a second notification daemon', 'dunst'),
                             ('a second notification daemon', 'swaync'),
                             ('a welcome wizard', 'center.py')):
            with self.subTest(daemon=name):
                self.assertNotIn(needle, joined)

    def test_no_command_depends_on_a_checkout_path(self):
        # The v4 session started a first-login wizard from a path inside one user's
        # home directory. A startup command that only works in this checkout fails
        # for every install that is not this checkout, and fails silently.
        for command in exec_block(gen.render(record())):
            with self.subTest(command=command[:40]):
                self.assertNotIn('$HOME', command)
                self.assertNotIn('iarch-by-safari', command)
                self.assertNotIn(str(ROOT), command)

    def test_every_absent_daemon_points_at_a_record_that_exists(self):
        for name, entry in record()['not_shipped'].items():
            with self.subTest(daemon=name):
                path = ROOT / entry['recorded_in']
                self.assertTrue(path.is_file(), entry['recorded_in'])
                node = read_json(path)
                for key in entry['where'].split('.'):
                    self.assertIn(key, node, f"{entry['where']} does not resolve")
                    node = node[key]

    def test_the_polkit_agent_is_the_only_agent_started(self):
        agents = [command for command in exec_block(gen.render(record()))
                  if 'polkit' in command or 'pkexec' in command]
        self.assertEqual(1, len(agents))
        self.assertIn(POLKIT, agents[0])

    def test_the_shell_is_started_exactly_once(self):
        commands = exec_block(gen.render(record()))
        self.assertEqual(1, sum(1 for command in commands if command.strip() == 'noctalia'))


if __name__ == '__main__':
    unittest.main()
