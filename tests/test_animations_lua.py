"""Prove the generated Hyprland animation set is the one the presets describe.

The generator drives compositor animation, which Hyprland validates loudly: an
unknown leaf, an unregistered curve or a style a leaf does not accept is a config
error that stops the session. So these tests assert the render against
``data/design/animations.json`` -- the animation API read out of Hyprland v0.57.2
-- the same way test_glass_lua.py asserts against ``hyprland.leaves``. Since Part
3 the plan lives in data/design/animations/<preset>.json rather than in a table in
the generator, so the refusal tests hand the renderer a mutated preset document
instead of monkeypatching a module global: same guarantees, checked against the
thing a person actually edits.

Six things are checked:

* the render is Lua at all (``luac -p`` / ``luaparser`` when the host has them,
  plus the structural fallback that needs no interpreter);
* every leaf, curve and style it emits is one the surface says Hyprland accepts,
  and every ``speed`` equals ``duration_ms / 100`` (the hyprutils
  ``AnimatedVariable::getPercent`` relationship), inside the binding's
  ``(0, 100]``;
* every curve number is inside the band the binding parses it against -- bezier
  components in ``[-1, 2]``, spring values strictly above 0.5 -- and the edges of
  the band are accepted, so the check is the real range and not a narrower guess;
* the global multiplier divides the duration (above 1 is faster), clamps to the
  token bounds and says so when it clamps, and reduce-motion renders one forced
  preset with every duration capped, at any multiplier;
* the Performance intensity and the ``off`` preset turn the master switch off and
  emit no curve and no leaf -- the warp path that lowers compositor work -- while
  a disabled event in any other preset is emitted as an explicit ``enabled =
  false``, because an absent leaf keeps inheriting its parent;
* an invented leaf, a bad style, an unregistered curve, a spring value at or below
  0.5, an out-of-range speed or duration, dead data on a disabled event, or an
  override asking for motion reduce-motion removes is refused or reported before
  anything is written.
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


def drop(base: Dict[str, Any], path: str) -> Dict[str, Any]:
    """A deep copy of ``base`` with ``path`` (dotted) removed.

    Needed because half of what a preset must not do is *omit* something: a leaf
    Hyprland gives no styles to must carry no style key at all, and a disabled
    event must carry no duration, curve or style.
    """
    clone = json.loads(json.dumps(base))
    node = clone
    keys = path.split('.')
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    del node[keys[-1]]
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


def preset(name: str = 'smooth') -> Dict[str, Any]:
    """One preset document as a dict, so a test can break it on purpose.

    Part 3 moved the animation plan out of this module's LEAF_PLAN and into
    data/design/animations/, so the refusal tests that used to monkeypatch a plan
    now hand the renderer a mutated preset instead -- the same guarantees, checked
    against the thing a person actually edits.
    """
    return anim.load_preset(name)


def render_preset(ps: Optional[Dict[str, Any]] = None, tk: Optional[Dict[str, Any]] = None,
                  sf: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """The full generated text (header + body) for one preset document."""
    return anim.build_preset(tk or tokens(), sf or surface(), ps or preset(), **kwargs)


def body_preset(ps: Optional[Dict[str, Any]] = None, tk: Optional[Dict[str, Any]] = None,
                sf: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """The Lua body without the generated header, for one preset document."""
    body, _warnings = anim.render_preset(tk or tokens(), sf or surface(), ps or preset(), **kwargs)
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

    def test_check_fails_when_the_preset_moves(self):
        # A different duration changes every speed, so a file rendered from the old
        # preset no longer matches; --check must report it rather than pass
        # silently. ROOT is fixed at import, so the directory the CLI reads and the
        # file it compares against are pointed at temp copies in-process instead of
        # via a subprocess cwd.
        with tempfile.TemporaryDirectory() as tmp:
            presets = Path(tmp) / 'animations'
            presets.mkdir()
            # The whole family has to be there: preset_names refuses a name the
            # tokens list with no file behind it, which is the check that would
            # otherwise turn this into an exit 2 for the wrong reason.
            for path in sorted(anim.PRESET_DIR.glob('*.json')):
                shutil.copy(path, presets / path.name)
            moved = mutate(preset(), 'events.windows.duration_ms', 999)
            (presets / 'smooth.json').write_text(json.dumps(moved), encoding='utf-8')
            stale = Path(tmp) / 'animations.lua'
            shutil.copy(SHIPPED, stale)  # rendered from the real preset
            original = (anim.PRESET_DIR, anim.REPO_DEFAULT)
            anim.PRESET_DIR, anim.REPO_DEFAULT = presets, stale
            self.addCleanup(setattr, anim, 'PRESET_DIR', original[0])
            self.addCleanup(setattr, anim, 'REPO_DEFAULT', original[1])
            err = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(err):
                code = anim.main(['--check'])
            self.assertEqual(1, code, err.getvalue())

    def test_check_still_passes_when_an_unused_token_moves(self):
        # The render reads durations out of the preset, not out of motion.fast_ms,
        # so moving a token the compositor no longer consumes must not make --check
        # fail -- and must not make it pass for the wrong reason either. The GTK
        # and Noctalia renderers still read those tokens; tests/test_animation_presets.py
        # is what keeps smooth and the tokens telling the same story.
        with tempfile.TemporaryDirectory() as tmp:
            moved_tokens = Path(tmp) / 'tokens.json'
            moved_tokens.write_text(json.dumps(mutate(tokens(), 'motion.normal_ms', 999)),
                                    encoding='utf-8')
            original = anim.TOKENS_PATH
            anim.TOKENS_PATH = moved_tokens
            self.addCleanup(setattr, anim, 'TOKENS_PATH', original)
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = anim.main(['--check'])
            self.assertEqual(0, code, err.getvalue())


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

    def test_the_preset_covers_exactly_the_leaves_that_are_emitted(self):
        declared = set(preset()['events'])
        emitted = {call['leaf'] for call in hl_animation_calls(body_only())}
        self.assertEqual(declared, emitted)

    def test_every_preset_covers_exactly_the_leaves_it_emits(self):
        # Including the presets that turn events off: a disabled event is still
        # emitted, as an explicit enabled = false, because an absent leaf would
        # keep inheriting its parent's animation. A preset with the master switch
        # off is the exception and is asserted separately -- it emits nothing at
        # all, which is the whole point of the warp path.
        for name in anim.preset_names(tokens()):
            ps = preset(name)
            if not ps['master']:
                continue
            with self.subTest(preset=name):
                declared = set(ps['events'])
                emitted = {c['leaf'] for c in hl_animation_calls(body_preset(ps))}
                self.assertEqual(declared, emitted)

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

    def test_an_unknown_leaf_in_a_preset_is_refused(self):
        broken = mutate(preset(), 'events.notARealLeaf',
                        {'enabled': True, 'duration_ms': 220, 'curve': 'standard'})
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_an_unknown_leaf_is_refused_even_when_the_event_is_disabled(self):
        # A typo is a typo whether or not the event does anything: hl.animation
        # answers "no such animation leaf" before it ever looks at enabled.
        broken = mutate(preset('minimal'), 'events.notARealLeaf', {'enabled': False})
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_style_on_a_leaf_that_takes_none_is_refused(self):
        # 'fade' takes no style upstream, so naming one must be refused.
        broken = mutate(preset(), 'events.fade.style', 'slide')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_style_the_leaf_does_not_accept_is_refused(self):
        # windows accepts slide/gnome/gnomed/popin, never 'fade'.
        broken = mutate(preset(), 'events.windows.style', 'fade')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_the_style_the_brief_suggests_for_workspaces_is_refused(self):
        # 'slidefade 20%' reads like a plausible Hyprland style and is not one:
        # workspaces takes slide, slidevert or fade, and only 'slide' accepts a
        # ' NN%' suffix. This is the exact invention the surface file exists to
        # stop, so it is asserted rather than left to a reviewer to notice.
        broken = mutate(preset(), 'events.workspaces.style', 'slidefade 20%')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_omitting_a_required_style_is_refused(self):
        # windows accepts styles, so the preset must name one.
        broken = drop(preset(), 'events.windows.style')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)


class SpeedsAreDurationsOverOneHundred(unittest.TestCase):
    def setUp(self):
        self.preset = preset()
        self.events = self.preset['events']
        self.calls = {c['leaf']: c for c in hl_animation_calls(body_only())}

    def test_every_speed_equals_its_preset_duration_over_one_hundred(self):
        for leaf, call in self.calls.items():
            with self.subTest(leaf=leaf):
                expected = round(self.events[leaf]['duration_ms'] / 100.0, 4)
                self.assertAlmostEqual(expected, call['speed'], places=4)

    def test_every_preset_derives_every_speed_the_same_way(self):
        for name in anim.preset_names(tokens()):
            ps = preset(name)
            calls = {c['leaf']: c for c in hl_animation_calls(body_preset(ps))}
            for leaf, event in ps['events'].items():
                if not event['enabled']:
                    continue
                with self.subTest(preset=name, leaf=leaf):
                    expected = round(event['duration_ms'] / 100.0, 4)
                    self.assertAlmostEqual(expected, calls[leaf]['speed'], places=4)

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
        broken = mutate(self.preset, 'events.fade.duration_ms', 0)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_duration_above_the_binding_ceiling_is_refused(self):
        # 10001ms -> speed 100.01, above the 100 the binding parses speed against.
        # CLuaConfigFloat returns PARSE_ERROR_OUT_OF_RANGE rather than clamping, so
        # this would stop the session, not quietly shorten the animation.
        broken = mutate(self.preset, 'events.workspaces.duration_ms', 10001)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_the_longest_duration_any_preset_declares_is_inside_the_ceiling(self):
        ceiling = surface()['speed_formula']['speed_max'] * 100
        for name in anim.preset_names(tokens()):
            for leaf, event in preset(name)['events'].items():
                if not event['enabled']:
                    continue
                with self.subTest(preset=name, leaf=leaf):
                    self.assertLessEqual(event['duration_ms'], ceiling)


class TheGlobalMultiplierIsClampedNotTrusted(unittest.TestCase):
    """``iarch-anim speed`` divides the duration and clamps to the token bounds."""

    def setUp(self):
        self.tokens = tokens()
        self.low, self.high, self.default = anim.multiplier_bounds(self.tokens)

    def calls(self, **kwargs):
        return {c['leaf']: c for c in hl_animation_calls(body_preset(preset(), **kwargs))}

    def test_the_bounds_are_the_documented_ones(self):
        self.assertEqual(0.5, self.low)
        self.assertEqual(2.0, self.high)
        self.assertEqual(1.0, self.default)

    def test_a_multiplier_above_one_shortens_the_animation(self):
        # 220ms at 2.0 is 110ms, i.e. speed 1.1: faster means less time, the
        # direction render_noctalia.py already uses for shell.animation.
        self.assertAlmostEqual(1.1, self.calls(multiplier=2.0)['windows']['speed'], places=4)

    def test_a_multiplier_below_one_lengthens_the_animation(self):
        self.assertAlmostEqual(4.4, self.calls(multiplier=0.5)['windows']['speed'], places=4)

    def test_one_changes_nothing(self):
        self.assertEqual(hl_animation_calls(body_preset(preset())),
                         hl_animation_calls(body_preset(preset(), multiplier=1.0)))

    def test_every_event_is_scaled_not_just_the_first(self):
        slow = self.calls(multiplier=0.5)
        fast = self.calls(multiplier=2.0)
        for leaf in slow:
            with self.subTest(leaf=leaf):
                self.assertAlmostEqual(slow[leaf]['speed'] / 4.0, fast[leaf]['speed'], places=3)

    def test_a_multiplier_past_the_ceiling_is_clamped_and_reported(self):
        value, clamped = anim.clamp_multiplier(self.tokens, 99.0)
        self.assertEqual(self.high, value)
        self.assertTrue(clamped)
        _body, warnings = anim.render_preset(self.tokens, surface(), preset(), multiplier=99.0)
        self.assertTrue(any('outside' in w for w in warnings), warnings)
        self.assertAlmostEqual(1.1, self.calls(multiplier=99.0)['windows']['speed'], places=4)

    def test_a_multiplier_below_the_floor_is_clamped_and_reported(self):
        value, clamped = anim.clamp_multiplier(self.tokens, 0.01)
        self.assertEqual(self.low, value)
        self.assertTrue(clamped)
        _body, warnings = anim.render_preset(self.tokens, surface(), preset(), multiplier=0.01)
        self.assertTrue(any('outside' in w for w in warnings), warnings)

    def test_a_multiplier_inside_the_bounds_is_not_reported_as_clamped(self):
        value, clamped = anim.clamp_multiplier(self.tokens, 1.25)
        self.assertEqual(1.25, value)
        self.assertFalse(clamped)

    def test_the_slowest_setting_stays_inside_the_binding_range(self):
        # 3000ms borderangle at 0.5 is 6000ms -> speed 60, still inside (0, 100].
        for leaf, call in self.calls(multiplier=self.low).items():
            with self.subTest(leaf=leaf):
                self.assertGreater(call['speed'], 0.0)
                self.assertLessEqual(call['speed'], surface()['speed_formula']['speed_max'])

    def test_a_non_numeric_multiplier_is_refused(self):
        with self.assertRaises(anim.AnimationError):
            anim.clamp_multiplier(self.tokens, 'fast')

    def test_a_multiplier_cannot_round_a_duration_away_to_nothing(self):
        # A hand-edited preset with a 1ms event at the slowest multiplier would
        # round to 2ms, but a preset that small at the fastest setting has to be
        # refused rather than emitted as speed 0, which the binding rejects.
        broken = mutate(preset(), 'events.fade.duration_ms', 1)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken, multiplier=2.0)


class ReduceMotionIsDeterministic(unittest.TestCase):
    """Reduce-motion forces one preset and caps every duration."""

    def setUp(self):
        self.tokens = tokens()
        self.forced = anim.reduce_motion_preset(self.tokens)
        self.cap = anim.reduce_motion_cap_ms(self.tokens)

    def test_the_tokens_name_minimal_and_a_cap_under_a_hundred_milliseconds(self):
        self.assertEqual('minimal', self.forced)
        self.assertLess(self.cap, 100)

    def test_it_renders_the_forced_preset_whatever_was_selected(self):
        body = body_preset(preset(self.forced), reduce_motion=True)
        self.assertTrue(master_enabled(body))
        emitted = {c['leaf'] for c in hl_animation_calls(body) if c['enabled']}
        self.assertTrue(emitted, 'reduce-motion must still fade something')

    def test_it_caps_every_duration(self):
        for call in hl_animation_calls(body_preset(preset(self.forced), reduce_motion=True)):
            if not call['enabled']:
                continue
            with self.subTest(leaf=call['leaf']):
                self.assertLessEqual(call['speed'] * 100, self.cap)

    def test_the_cap_holds_at_the_slowest_multiplier_too(self):
        # The cap is applied after the multiplier, so slowing everything down
        # cannot push a fade back over the reduce-motion ceiling.
        body = body_preset(preset(self.forced), reduce_motion=True, multiplier=0.5)
        for call in hl_animation_calls(body):
            if call['enabled']:
                self.assertLessEqual(call['speed'] * 100, self.cap)

    def test_rendering_reduce_motion_from_another_preset_is_refused(self):
        # The guarantee lives in the renderer, not in the caller, so no tool can
        # render a reduce-motion session that still slides windows.
        with self.assertRaises(anim.AnimationError):
            render_preset(preset('smooth'), reduce_motion=True)

    def test_an_override_that_would_add_motion_back_is_ignored_and_reported(self):
        _body, warnings = anim.render_preset(self.tokens, surface(), preset(self.forced),
                                             reduce_motion=True, overrides={'windows': True})
        self.assertTrue(any('reduce-motion removes' in w for w in warnings), warnings)
        calls = {c['leaf']: c for c in hl_animation_calls(_body)}
        self.assertFalse(calls['windows']['enabled'])

    def test_an_override_that_removes_motion_is_still_honoured(self):
        body = body_preset(preset(self.forced), reduce_motion=True, overrides={'fade': False})
        calls = {c['leaf']: c for c in hl_animation_calls(body)}
        self.assertFalse(calls['fade']['enabled'])

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

    def test_an_event_naming_a_curve_the_preset_does_not_declare_is_refused(self):
        # The name would be registered as iarch-noSuchCurve by nobody; hl.animation
        # looks it up with bezierExists/springExists and errors on a miss.
        broken = mutate(preset(), 'events.windows.curve', 'noSuchCurve')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_curve_of_an_unknown_type_is_refused(self):
        # hl.curve accepts exactly 'bezier' and 'spring'; anything else is a config
        # error, and a preset that invented a third kind must not reach the file.
        broken = mutate(preset(), 'curves.standard.type', 'easeInOut')
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)


class CurvesAreInsideTheBindingBounds(unittest.TestCase):
    """Every number a curve carries is one hl.curve will accept.

    The bounds are read out of data/design/animations.json rather than repeated
    here, so this class fails if the recorded surface and the generator ever
    disagree about what Hyprland enforces.
    """

    def setUp(self):
        self.surface = surface()
        self.bezier_limits = self.surface['curve_types']['bezier']
        self.spring_floor = self.surface['curve_types']['spring']['value_min_exclusive']

    def test_the_surface_records_the_bounds_as_numbers(self):
        self.assertEqual(-1.0, self.bezier_limits['component_min'])
        self.assertEqual(2.0, self.bezier_limits['component_max'])
        self.assertEqual(0.5, self.spring_floor)

    def test_every_declared_spring_is_above_the_strict_half_bound(self):
        for name in anim.preset_names(tokens()):
            for curve_name, curve in preset(name)['curves'].items():
                if curve.get('type') != 'spring':
                    continue
                for key, value in curve.items():
                    if key in ('stiffness', 'damping', 'mass'):
                        with self.subTest(preset=name, curve=curve_name, key=key):
                            self.assertGreater(value, self.spring_floor)

    def test_every_declared_bezier_component_is_inside_the_recorded_band(self):
        low, high = self.bezier_limits['component_min'], self.bezier_limits['component_max']
        for name in anim.preset_names(tokens()):
            for curve_name, curve in preset(name)['curves'].items():
                if curve.get('type') != 'bezier':
                    continue
                for point in curve['points']:
                    for component in point:
                        with self.subTest(preset=name, curve=curve_name):
                            self.assertGreaterEqual(component, low)
                            self.assertLessEqual(component, high)

    def test_the_bouncy_preset_really_does_overshoot(self):
        # The point of the wider band: a y above 1 arrives past the target and
        # comes back. If no curve in bouncy exceeds 1 the preset is misnamed.
        curves = preset('bouncy')['curves']
        peaks = [max(y for _x, y in c['points']) for c in curves.values()
                 if c['type'] == 'bezier']
        self.assertTrue(any(peak > 1.0 for peak in peaks), peaks)

    def test_no_shared_easing_token_overshoots(self):
        # tokens.motion.easing is shared with the GTK CSS renderer, where
        # cubic-bezier() requires the unit square, so the overshoot lives in the
        # compositor-only preset files and never in the tokens.
        for name, curve in tokens()['motion']['easing'].items():
            for point in curve['points']:
                for component in point:
                    with self.subTest(easing=name):
                        self.assertGreaterEqual(component, 0.0)
                        self.assertLessEqual(component, 1.0)

    def test_a_spring_value_at_half_is_refused(self):
        broken = mutate(preset(), 'curves.spring.damping', self.spring_floor)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_spring_value_below_half_is_refused(self):
        broken = mutate(preset(), 'curves.spring.mass', 0.2)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_bezier_without_two_points_is_refused(self):
        broken = mutate(preset(), 'curves.standard.points', [[0.4, 0.0]])
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_bezier_component_above_the_band_is_refused(self):
        # 2.1 is past the CLuaConfigFloat(0, -1, 2) maximum, which returns
        # PARSE_ERROR_OUT_OF_RANGE instead of clamping, so it has to fail here.
        broken = mutate(preset(), 'curves.standard.points', [[0.4, 0.0], [2.1, 1.0]])
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_a_bezier_component_below_the_band_is_refused(self):
        broken = mutate(preset(), 'curves.standard.points', [[-1.5, 0.0], [0.2, 1.0]])
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_the_band_edges_themselves_are_accepted(self):
        # -1 and 2 are inside the range the parser allows, so the check is a band
        # and not a smaller guess at one.
        edge = mutate(preset(), 'curves.standard.points', [[-1.0, 0.0], [2.0, 1.0]])
        self.assertIn('iarch-standard', hl_curve_calls(body_preset(edge)))


class DisabledEventsSayOnlyThatTheyAreOff(unittest.TestCase):
    def test_a_disabled_event_is_emitted_with_no_speed_curve_or_style(self):
        body = body_preset(preset('minimal'))
        for call in hl_animation_calls(body):
            if call['enabled']:
                continue
            with self.subTest(leaf=call['leaf']):
                self.assertEqual({'leaf', 'enabled'}, set(call))

    def test_a_preset_that_declares_an_event_off_may_not_give_it_a_duration(self):
        # Dead data: hl.animation returns early on enabled = false, so a duration,
        # curve or style on a disabled event is never read and only misleads.
        broken = mutate(preset('minimal'), 'events.windows.duration_ms', 220)
        with self.assertRaises(anim.AnimationError):
            render_preset(broken)

    def test_an_override_turning_an_event_off_leaves_the_preset_data_alone(self):
        # The other direction is not dead data: smooth declares borderangle with a
        # duration and curve, and a person toggling it off should be able to
        # toggle it back on without editing the preset.
        body = body_preset(preset(), overrides={'borderangle': False})
        calls = {c['leaf']: c for c in hl_animation_calls(body)}
        self.assertEqual({'leaf', 'enabled'}, set(calls['borderangle']))
        self.assertTrue(calls['windows']['enabled'])

    def test_an_override_can_turn_a_live_event_back_on(self):
        body = body_preset(preset(), overrides={'borderangle': False})
        self.assertFalse({c['leaf']: c for c in hl_animation_calls(body)}['borderangle']['enabled'])
        body = body_preset(preset(), overrides={'borderangle': True})
        self.assertTrue({c['leaf']: c for c in hl_animation_calls(body)}['borderangle']['enabled'])

    def test_an_override_cannot_turn_on_an_event_the_preset_declares_off(self):
        # minimal gives 'windows' no duration or curve, so there is nothing to
        # turn it on with; the refusal has to say that instead of failing on a
        # missing style or duration deep in the render.
        with self.assertRaises(anim.AnimationError) as caught:
            render_preset(preset('minimal'), overrides={'windows': True})
        self.assertIn('switch to a preset', str(caught.exception))

    def test_an_override_naming_an_event_the_preset_does_not_declare_is_refused(self):
        with self.assertRaises(anim.AnimationError):
            render_preset(preset(), overrides={'fadePopups': False})

    def test_the_master_switch_off_emits_no_curve_and_no_event(self):
        body = body_preset(preset('off'))
        self.assertIs(False, master_enabled(body))
        self.assertEqual({}, hl_curve_calls(body))
        self.assertEqual([], hl_animation_calls(body))


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
