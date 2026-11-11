"""Prove the generated Hyprland animation set is the one the tokens describe.

The generator drives compositor animation, which Hyprland validates loudly: an
unknown leaf, an unregistered curve or a style a leaf does not accept is a config
error that stops the session. So these tests assert the render against
``data/design/animations.json`` -- the animation API read out of Hyprland v0.57.2
-- the same way test_glass_lua.py asserts against ``hyprland.leaves``.

Four things are checked:

* the render is Lua at all (``luac -p`` / ``luaparser`` when the host has them,
  plus the structural fallback that needs no interpreter);
* every leaf, curve and style it emits is one the surface says Hyprland accepts,
  and every ``speed`` equals ``duration_ms / 100`` (the hyprutils
  ``AnimatedVariable::getPercent`` relationship), inside the binding's
  ``(0, 100]``;
* the Performance intensity turns the master switch off and emits no curve or
  leaf -- the warp path that lowers compositor work;
* an invented leaf, a bad style, a spring value at or below 0.5 or an
  out-of-range speed is refused before anything is written.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_animations_lua as anim  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
SURFACE_PATH = ROOT / 'data' / 'design' / 'animations.json'
SHIPPED = ROOT / '.config' / 'hypr' / 'generated' / 'animations.lua'
ANIMATIONS_LUA = ROOT / '.config' / 'hypr' / 'animations.lua'
HYPRLAND_LUA = ROOT / '.config' / 'hypr' / 'hyprland.lua'

LUAC = next((name for name in ('luac', 'luac5.4', 'luac5.3', 'luac5.1')
             if shutil.which(name)), None)
try:
    from luaparser import ast as lua_ast  # noqa: E402

    HAVE_LUAPARSER = True
except ImportError:  # pragma: no cover - depends on the host
    lua_ast = None
    HAVE_LUAPARSER = False


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def tokens() -> Dict[str, Any]:
    return read_json(TOKENS_PATH)


def surface() -> Dict[str, Any]:
    return read_json(SURFACE_PATH)


def mutate(base: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """A deep copy of ``base`` with ``path`` (dotted) replaced."""
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


def render(tk: Optional[Dict[str, Any]] = None, sf: Optional[Dict[str, Any]] = None,
           intensity: str = 'frosted') -> str:
    """The full generated text (header + body) for one intensity."""
    return anim.build(tk or tokens(), sf or surface(), intensity)


def body_only(tk: Optional[Dict[str, Any]] = None, sf: Optional[Dict[str, Any]] = None,
              intensity: str = 'frosted') -> str:
    """The Lua body without the generated header, as anim.render returns it."""
    body, _warnings = anim.render(tk or tokens(), sf or surface(), intensity)
    return body


def hl_animation_calls(text: str) -> List[Dict[str, Any]]:
    """Parse every ``hl.animation({ ... })`` into a dict of its flat fields."""
    calls = []
    for inner in re.findall(r'hl\.animation\(\{(.*?)\}\)', text, re.S):
        fields: Dict[str, Any] = {}
        for key, value in re.findall(r'(\w+)\s*=\s*("[^"]*"|[\w.+-]+)', inner):
            if value.startswith('"'):
                fields[key] = value[1:-1]
            elif value in ('true', 'false'):
                fields[key] = value == 'true'
            else:
                fields[key] = float(value)
        calls.append(fields)
    return calls


def hl_curve_calls(text: str) -> Dict[str, str]:
    """Map every registered curve name to its type ("bezier" or "spring")."""
    curves = {}
    for name, body in re.findall(r'hl\.curve\(\s*"([^"]+)"\s*,\s*\{(.*?)\}\s*\)', text, re.S):
        match = re.search(r'type\s*=\s*"([^"]+)"', body)
        curves[name] = match.group(1) if match else '?'
    return curves


def master_enabled(text: str) -> Optional[bool]:
    match = re.search(r'animations\s*=\s*\{\s*enabled\s*=\s*(true|false)', text, re.S)
    return None if not match else match.group(1) == 'true'


class LuaSyntax(unittest.TestCase):
    """Is the rendered file Lua at all? Skips when the host has no Lua tooling."""

    def write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile('w', suffix='.lua', delete=False, encoding='utf-8')
        tmp.write(text)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return Path(tmp.name)

    def test_luac_accepts_the_shipped_file(self):
        if not LUAC:
            self.skipTest('luac is not installed')
        result = subprocess.run([LUAC, '-p', str(SHIPPED)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_luac_accepts_a_render_of_every_intensity(self):
        if not LUAC:
            self.skipTest('luac is not installed')
        tk, sf = tokens(), surface()
        for name in tk['intensities']:
            with self.subTest(intensity=name):
                path = self.write(render(tk, sf, name))
                result = subprocess.run([LUAC, '-p', str(path)], capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)

    @unittest.skipUnless(HAVE_LUAPARSER, 'luaparser is not installed')
    def test_luaparser_accepts_the_shipped_file(self):
        lua_ast.parse(SHIPPED.read_text(encoding='utf-8'))

    @unittest.skipUnless(HAVE_LUAPARSER, 'luaparser is not installed')
    def test_luaparser_accepts_a_render_of_every_intensity(self):
        tk, sf = tokens(), surface()
        for name in tk['intensities']:
            with self.subTest(intensity=name):
                lua_ast.parse(render(tk, sf, name))

    def test_the_render_is_a_sequence_of_hl_calls_and_comments(self):
        # Every non-blank, non-comment line must be an hl.* call: nothing else is
        # valid at the top level of a Hyprland Lua config fragment.
        for line in body_only().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('--'):
                continue
            self.assertTrue(re.match(r'hl\.(config|curve|animation)\b', stripped)
                            or stripped.startswith(('animations =', 'enabled =', '})', '{', '}')),
                            f'unexpected top-level line: {line!r}')

    def test_the_structural_fallback_accepts_the_shipped_file(self):
        self.assertEqual([], anim.sanity_check_lua(SHIPPED.read_text(encoding='utf-8')))

    def test_the_structural_fallback_catches_an_unbalanced_brace(self):
        self.assertTrue(anim.sanity_check_lua('hl.animation({ leaf = "windows" }'))

    def test_the_structural_fallback_catches_an_unterminated_string(self):
        self.assertTrue(anim.sanity_check_lua('hl.curve("iarch-standard, {})'))


class HeaderAndCheck(unittest.TestCase):
    def test_the_shipped_file_starts_with_the_generated_header(self):
        first = SHIPPED.read_text(encoding='utf-8').splitlines()[0]
        self.assertTrue(configstore.is_header_line(first), first)

    def test_the_header_names_the_intensity_and_the_verified_release(self):
        text = SHIPPED.read_text(encoding='utf-8')
        self.assertIn('intensity=frosted', text)
        self.assertIn(surface()['verified_against'], text)
        self.assertIn('speed = duration_ms / 100', text)

    def test_the_committed_default_matches_a_fresh_render(self):
        # The same comparison --check makes, so a stale committed file fails here
        # even if the workflow step is skipped.
        tk, sf = tokens(), surface()
        intensity = tk['default_intensity']
        expected = anim.rendered_text(SHIPPED, anim.build(tk, sf, intensity).rstrip('\n'))
        self.assertEqual(expected, SHIPPED.read_text(encoding='utf-8'))

    def test_check_passes_on_the_committed_default(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = anim.main(['--check'])
        self.assertEqual(0, code, err.getvalue())

    def test_check_fails_when_the_tokens_move(self):
        # A different duration token changes every speed, so a file rendered from
        # the old tokens no longer matches; --check must report it rather than pass
        # silently. ROOT is fixed at import, so the two paths the CLI reads are
        # pointed at temp copies in-process instead of via a subprocess cwd.
        with tempfile.TemporaryDirectory() as tmp:
            moved_tokens = Path(tmp) / 'tokens.json'
            moved_tokens.write_text(json.dumps(mutate(tokens(), 'motion.normal_ms', 999)),
                                    encoding='utf-8')
            stale = Path(tmp) / 'animations.lua'
            shutil.copy(SHIPPED, stale)  # rendered from the real tokens
            original = (anim.TOKENS_PATH, anim.REPO_DEFAULT)
            anim.TOKENS_PATH, anim.REPO_DEFAULT = moved_tokens, stale
            self.addCleanup(setattr, anim, 'TOKENS_PATH', original[0])
            self.addCleanup(setattr, anim, 'REPO_DEFAULT', original[1])
            err = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(err):
                code = anim.main(['--check'])
            self.assertEqual(1, code, err.getvalue())


class MasterSwitch(unittest.TestCase):
    def test_an_enabled_intensity_turns_animations_on(self):
        self.assertIs(True, master_enabled(body_only(intensity='frosted')))

    def test_the_performance_intensity_turns_animations_off(self):
        self.assertIs(False, master_enabled(body_only(intensity='performance')))

    def test_the_performance_intensity_emits_no_curve_and_no_leaf(self):
        # The warp path: with the master switch off Hyprland jumps every animated
        # variable to its final value, so registering curves or leaves would be
        # dead work the generator must not emit.
        body = body_only(intensity='performance')
        self.assertEqual({}, hl_curve_calls(body))
        self.assertEqual([], hl_animation_calls(body))

    def test_the_performance_render_carries_the_warp_warning(self):
        text = render(intensity='performance')
        self.assertIn('animations disabled', text)
        self.assertIn('warps', text)

    def test_every_intensity_has_a_motion_enabled_switch(self):
        for name, intensity in tokens()['intensities'].items():
            with self.subTest(intensity=name):
                self.assertIn('enabled', intensity['motion'])

    def test_only_performance_disables_motion(self):
        motions = {n: i['motion']['enabled'] for n, i in tokens()['intensities'].items()}
        self.assertFalse(motions['performance'])
        self.assertTrue(all(v for k, v in motions.items() if k != 'performance'))


class CurvesAreTheTokenEasings(unittest.TestCase):
    def test_it_registers_the_four_easings_and_the_spring(self):
        curves = hl_curve_calls(body_only())
        self.assertEqual({
            'iarch-standard': 'bezier',
            'iarch-emphasized': 'bezier',
            'iarch-decelerate': 'bezier',
            'iarch-accelerate': 'bezier',
            'iarch-spring': 'spring',
        }, curves)

    def test_the_bezier_points_are_the_token_easing_points(self):
        body = body_only()
        for name, curve in tokens()['motion']['easing'].items():
            with self.subTest(easing=name):
                call = re.search(rf'hl\.curve\("iarch-{name}", \{{(.*?)\}}\)', body, re.S).group(1)
                points = re.findall(r'\{\s*([\d.+-]+),\s*([\d.+-]+)\s*\}', call)
                self.assertEqual([(float(x), float(y)) for x, y in points],
                                 [(float(p[0]), float(p[1])) for p in curve['points']])

    def test_the_spring_carries_the_token_stiffness_damping_and_mass(self):
        body = body_only()
        call = re.search(r'hl\.curve\("iarch-spring", \{(.*?)\}\)', body, re.S).group(1)
        spring = tokens()['motion']['spring']
        for key in ('stiffness', 'damping', 'mass'):
            value = float(re.search(rf'{key}\s*=\s*([\d.+-]+)', call).group(1))
            self.assertAlmostEqual(spring[key], value, places=6)

    def test_curve_names_are_prefixed_so_they_cannot_collide(self):
        # The static default.lua registers wind/winIn/winOut/liner and Hyprland
        # has built-in default/linear; the generated names must not shadow any.
        forbidden = {'wind', 'winIn', 'winOut', 'liner', 'default', 'linear'}
        for name in hl_curve_calls(body_only()):
            self.assertNotIn(name, forbidden)
            self.assertTrue(name.startswith(anim.CURVE_PREFIX), name)


class EveryLeafIsOneHyprlandKnows(unittest.TestCase):
    def setUp(self):
        self.surface = surface()
        self.leaves = self.surface['leaves']

    def test_every_emitted_leaf_is_in_the_verified_tree(self):
        for call in hl_animation_calls(body_only()):
            with self.subTest(leaf=call['leaf']):
                self.assertIn(call['leaf'], self.leaves)

    def test_the_plan_covers_exactly_the_leaves_that_are_emitted(self):
        planned = {leaf for leaf, _c, _d, _s in anim.LEAF_PLAN}
        emitted = {call['leaf'] for call in hl_animation_calls(body_only())}
        self.assertEqual(planned, emitted)

    def test_no_duplicate_leaf_is_emitted(self):
        emitted = [call['leaf'] for call in hl_animation_calls(body_only())]
        self.assertEqual(len(emitted), len(set(emitted)), 'a leaf is animated twice')

    def test_every_style_is_one_that_leaf_accepts(self):
        for call in hl_animation_calls(body_only()):
            leaf, style = call['leaf'], call.get('style')
            allowed = self.leaves[leaf]['styles']
            with self.subTest(leaf=leaf):
                if style is None:
                    self.assertEqual([], allowed,
                                     f'{leaf} accepts {allowed} but the plan omitted a style')
                else:
                    self.assertIn(style, allowed)

    def test_a_leaf_with_no_styles_is_emitted_without_one(self):
        # fade and border take no style upstream; emitting one would be a config
        # error ("animation has no styles").
        for call in hl_animation_calls(body_only()):
            if self.leaves[call['leaf']]['styles'] == []:
                self.assertNotIn('style', call, call['leaf'])

    def test_an_unknown_leaf_in_the_plan_is_refused(self):
        plan = anim.LEAF_PLAN
        anim.LEAF_PLAN = (('notARealLeaf', ('bezier', 'standard'), 'normal_ms', None),)
        self.addCleanup(setattr, anim, 'LEAF_PLAN', plan)
        with self.assertRaises(anim.AnimationError):
            render()

    def test_a_bad_style_in_the_plan_is_refused(self):
        plan = anim.LEAF_PLAN
        # 'fade' takes no style upstream, so naming one must be refused.
        anim.LEAF_PLAN = (('fade', ('bezier', 'standard'), 'fast_ms', 'slide'),)
        self.addCleanup(setattr, anim, 'LEAF_PLAN', plan)
        with self.assertRaises(anim.AnimationError):
            render()

    def test_a_style_the_leaf_does_not_accept_is_refused(self):
        plan = anim.LEAF_PLAN
        # windows accepts slide/gnome/gnomed/popin, never 'fade'.
        anim.LEAF_PLAN = (('windows', ('bezier', 'standard'), 'normal_ms', 'fade'),)
        self.addCleanup(setattr, anim, 'LEAF_PLAN', plan)
        with self.assertRaises(anim.AnimationError):
            render()

    def test_omitting_a_required_style_is_refused(self):
        plan = anim.LEAF_PLAN
        # windows accepts styles, so the plan must name one.
        anim.LEAF_PLAN = (('windows', ('bezier', 'standard'), 'normal_ms', None),)
        self.addCleanup(setattr, anim, 'LEAF_PLAN', plan)
        with self.assertRaises(anim.AnimationError):
            render()


class SpeedsAreDurationsOverOneHundred(unittest.TestCase):
    def setUp(self):
        self.motion = tokens()['motion']
        self.calls = {c['leaf']: c for c in hl_animation_calls(body_only())}

    def test_every_speed_equals_its_duration_token_over_one_hundred(self):
        for leaf, curve, duration_token, _style in anim.LEAF_PLAN:
            with self.subTest(leaf=leaf):
                expected = round(self.motion[duration_token] / 100.0, 4)
                self.assertAlmostEqual(expected, self.calls[leaf]['speed'], places=4)

    def test_the_three_durations_map_to_the_three_speeds(self):
        self.assertAlmostEqual(1.2, self.calls['fade']['speed'], places=4)   # fast_ms 120
        self.assertAlmostEqual(2.2, self.calls['windows']['speed'], places=4)  # normal_ms 220
        self.assertAlmostEqual(3.8, self.calls['workspaces']['speed'], places=4)  # slow_ms 380

    def test_every_speed_is_inside_the_binding_range(self):
        # hl.animation rejects speed <= 0 and CLuaConfigFloat clamps to [0, 100].
        for leaf, call in self.calls.items():
            with self.subTest(leaf=leaf):
                self.assertGreater(call['speed'], 0.0)
                self.assertLessEqual(call['speed'], 100.0)

    def test_a_zero_duration_is_refused_before_it_is_written(self):
        tk = mutate(tokens(), 'motion.fast_ms', 0)
        with self.assertRaises(anim.AnimationError):
            render(tk)

    def test_a_duration_above_the_binding_ceiling_is_refused(self):
        # 10001ms -> speed 100.01, above the 100 the binding clamps to.
        tk = mutate(tokens(), 'motion.slow_ms', 10001)
        with self.assertRaises(anim.AnimationError):
            render(tk)

    def test_the_formula_matches_the_recorded_surface(self):
        self.assertEqual('duration_ms = 100 * speed', surface()['speed_formula']['equation'])


class EveryLeafNamesACurveThatExists(unittest.TestCase):
    def test_every_bezier_leaf_references_a_registered_curve(self):
        body = body_only()
        curves = hl_curve_calls(body)
        for call in hl_animation_calls(body):
            if 'bezier' in call:
                with self.subTest(leaf=call['leaf']):
                    self.assertIn(call['bezier'], curves)
                    self.assertEqual('bezier', curves[call['bezier']])

    def test_the_spring_leaf_references_the_registered_spring(self):
        body = body_only()
        curves = hl_curve_calls(body)
        spring_leaves = [c for c in hl_animation_calls(body) if 'spring' in c]
        self.assertTrue(spring_leaves, 'the spring token must drive at least one leaf')
        for call in spring_leaves:
            self.assertIn(call['spring'], curves)
            self.assertEqual('spring', curves[call['spring']])

    def test_a_leaf_names_either_a_bezier_or_a_spring_never_both_neither(self):
        for call in hl_animation_calls(body_only()):
            with self.subTest(leaf=call['leaf']):
                self.assertEqual(1, ('bezier' in call) + ('spring' in call),
                                 'hl.animation requires exactly one curve reference')

    def test_an_unregistered_easing_in_the_plan_is_refused(self):
        plan = anim.LEAF_PLAN
        anim.LEAF_PLAN = (('windows', ('bezier', 'noSuchEasing'), 'normal_ms', 'slide'),)
        self.addCleanup(setattr, anim, 'LEAF_PLAN', plan)
        # The curve name would be iarch-noSuchEasing, which render_curves never
        # registers; the leaf then references a curve that does not exist.
        with self.assertRaises(anim.AnimationError):
            render()


class SpringsAreInsideTheBindingBounds(unittest.TestCase):
    def test_the_token_spring_is_above_the_strict_half_bound(self):
        # hl.curve rejects stiffness/damping/mass <= 0.5 with a config error.
        for key, value in tokens()['motion']['spring'].items():
            with self.subTest(key=key):
                self.assertGreater(value, 0.5)

    def test_a_spring_value_at_half_is_refused(self):
        tk = mutate(tokens(), 'motion.spring.damping', 0.5)
        with self.assertRaises(anim.AnimationError):
            render(tk)

    def test_a_spring_value_below_half_is_refused(self):
        tk = mutate(tokens(), 'motion.spring.mass', 0.2)
        with self.assertRaises(anim.AnimationError):
            render(tk)

    def test_a_bezier_without_two_points_is_refused(self):
        tk = mutate(tokens(), 'motion.easing.standard.points', [[0.4, 0.0]])
        with self.assertRaises(anim.AnimationError):
            render(tk)


class LoadGraph(unittest.TestCase):
    def test_animations_lua_requires_the_generated_file_through_a_pcall(self):
        text = ANIMATIONS_LUA.read_text(encoding='utf-8')
        self.assertIn('require("animations.default")', text)
        self.assertIn('require("generated.animations")', text)
        # The static default must load first so the generated curves win.
        self.assertLess(text.index('require("animations.default")'),
                        text.index('require("generated.animations")'))
        self.assertIn('pcall', text)

    def test_hyprland_lua_clears_the_generated_module_on_reload(self):
        # If generated.animations is not in the package.loaded clear-list it will
        # not re-execute when the config reloads, so an intensity change would not
        # take effect until a full restart.
        text = HYPRLAND_LUA.read_text(encoding='utf-8')
        clear = re.search(r'ipairs\(\{(.*?)\}\)', text, re.S).group(1)
        self.assertIn('"generated.animations"', clear)
        self.assertIn('"animations"', clear)

    def test_the_generated_module_resolves_to_a_shipped_file(self):
        # module_paths in test_payload_map resolves 'generated.animations' here.
        self.assertTrue(SHIPPED.is_file())
        self.assertEqual(SHIPPED, ROOT / '.config' / 'hypr' / 'generated' / 'animations.lua')


class CommandLine(unittest.TestCase):
    def run_cli(self, args: List[str], expect: int = 0) -> str:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = anim.main(args)
        self.assertEqual(expect, code, err.getvalue())
        return out.getvalue() + err.getvalue()

    def test_print_writes_the_render_to_stdout_and_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'animations.lua'
            printed = self.run_cli(['--intensity', 'performance', '--print'])
            self.assertIn('enabled = false', printed)
            self.assertFalse(target.exists())

    def test_output_writes_to_an_explicit_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.lua'
            self.run_cli(['--output', str(target)])
            self.assertTrue(target.is_file())
            self.assertTrue(configstore.is_header_line(
                target.read_text(encoding='utf-8').splitlines()[0]))

    def test_an_unknown_intensity_is_refused(self):
        self.run_cli(['--intensity', 'nope', '--print'], expect=2)

    def test_write_then_check_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / '.config' / 'hypr' / 'generated').mkdir(parents=True)
            target = repo / '.config' / 'hypr' / 'generated' / 'animations.lua'
            # Point the module's REPO_DEFAULT at the temp copy for --write-repo-default.
            original = anim.REPO_DEFAULT
            anim.REPO_DEFAULT = target
            self.addCleanup(setattr, anim, 'REPO_DEFAULT', original)
            self.run_cli(['--write-repo-default'])
            self.assertTrue(target.is_file())
            self.run_cli(['--check'])


class WriteGeneratedContract(unittest.TestCase):
    def test_the_generator_writes_through_configstore_write_generated(self):
        # The contract in docs/ARCHITECTURE.md: emit through write_generated so the
        # header is stamped, the previous file is backed up and the rename is atomic.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'animations.lua'
            written = configstore.write_generated(target, body_only())
            self.assertEqual(target, written)
            self.assertTrue(configstore.is_header_line(
                target.read_text(encoding='utf-8').splitlines()[0]))

    def test_target_path_lands_in_the_hypr_generated_dir(self):
        # config_dir reads IARCH_CONFIG_DIR (falling back to ~/.config/iarch); the
        # generated file must land in its hypr/generated subdir, exactly like glass.
        with tempfile.TemporaryDirectory() as tmp:
            path = anim.target_path({'IARCH_CONFIG_DIR': tmp})
            self.assertEqual(Path(tmp) / 'hypr' / 'generated' / 'animations.lua', path)

    def test_rendered_text_matches_what_write_generated_produces(self):
        body = body_only().rstrip('\n')
        expected = anim.rendered_text(SHIPPED, body)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'animations.lua'
            configstore.write_generated(target, body)
            self.assertEqual(expected, target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
