#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Hyprland glass renderer, ``iarch/cli/gen_glass_lua.py``.

The renderer's whole job is to emit configuration that Hyprland will accept, so
most of these tests assert against the upstream contract rather than against a
frozen snapshot of the output:

* every key it emits resolves to a leaf in ``tokens.hyprland.leaves`` -- the walk
  below mirrors ``hlConfig`` in ``LuaBindingsConfigRules.cpp``, which reports
  "unknown config key" for anything else instead of ignoring it;
* integer-typed leaves carry integer literals, because ``CLuaConfigInt::parse``
  accepts only ``lua_isinteger`` and rejects ``10.0`` outright;
* every number sits inside the min/max Hyprland itself enforces;
* rule effects and match properties come from the verified whitelists.

Syntax is checked with ``luac -p`` when a Lua toolchain is installed and with the
pure-Python ``luaparser`` when it is not; the test skips, saying which, when the
host has neither.
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
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_glass_lua as glass  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
PRESET_DIR = ROOT / 'data' / 'design' / 'presets'
SHIPPED = ROOT / '.config' / 'hypr' / 'generated' / 'glass.lua'
WINDOWRULES = ROOT / '.config' / 'hypr' / 'windowrules.lua'
THEME = ROOT / '.config' / 'hypr' / 'themes' / 'theme.lua'
ANIMATIONS = ROOT / '.config' / 'hypr' / 'animations.lua'

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


def lua_leaf_name(leaf: str) -> str:
    """``CConfigManager::luaConfigValueName``: ':' becomes '.', '-' becomes '_'."""
    return leaf.replace(':', '.').replace('-', '_')


def walk_config(table: Dict[str, Any], known: Dict[str, str],
                prefix: str = '') -> List[Tuple[str, Any]]:
    """Resolve a nested table to leaves exactly the way ``hlConfig`` does.

    ``hlConfig`` joins nested string keys with '.' and looks the result up in
    ``m_configValues``, whose keys are ``luaConfigValueName(leaf)``. A key that
    is neither a known leaf nor a table recursed into is reported upstream as
    "unknown config key", so this raises instead of silently passing.
    """
    resolved: List[Tuple[str, Any]] = []
    for key, value in table.items():
        full = f'{prefix}.{key}' if prefix else key
        if full in known:
            resolved.append((known[full], value))
        elif isinstance(value, dict):
            resolved.extend(walk_config(value, known, full))
        else:
            raise AssertionError(f'unknown config key {full!r}')
    return resolved


def emitted_config(tk: Optional[Dict[str, Any]] = None, preset_id: str = 'midnight-glass',
                   intensity: str = 'frosted') -> Dict[str, Any]:
    tk = tk or tokens()
    preset = glass.load_preset(tk, preset_id)
    warnings: List[str] = []
    return {
        'general': glass.general_block(tk, preset, warnings),
        'decoration': glass.decoration_block(tk, intensity, warnings),
    }


def resolved_leaves(tk: Optional[Dict[str, Any]] = None,
                    **kwargs: Any) -> Dict[str, Any]:
    tk = tk or tokens()
    known = {lua_leaf_name(leaf): leaf for leaf in tk['hyprland']['leaves']}
    return dict(walk_config(emitted_config(tk, **kwargs), known))


def top_level_keys(rule: str) -> set:
    """Keys of a rendered rule table, at its own indent level.

    ``name``, the effects and ``match`` are all emitted four spaces in; the
    properties inside ``match`` are eight. Selecting by indentation is what keeps
    ``namespace`` or ``class`` from being mistaken for a rule effect.
    """
    return set(re.findall(r'^    (\w+) =', rule, re.M))


def match_keys(rule: str) -> set:
    return set(re.findall(r'^        (\w+) =', rule, re.M))


def number_after(text: str, key: str) -> List[str]:
    """Every literal assigned to ``key`` in rendered Lua."""
    return re.findall(rf'(?<![\w.]){re.escape(key)}\s*=\s*(-?\d+(?:\.\d+)?)', text)


def parse_rgba(text: str) -> List[Tuple[int, int, int, float]]:
    return [(int(r), int(g), int(b), float(a)) for r, g, b, a
            in re.findall(r'rgba\((\d+), (\d+), (\d+), ([\d.]+)\)', text)]


class LuaSyntax(unittest.TestCase):
    """Is the rendered file Lua at all? Skips when the host has no Lua tooling."""

    def setUp(self):
        self.assertTrue(SHIPPED.is_file(), f'{SHIPPED} is missing; run the generator')
        self.source = SHIPPED.read_text(encoding='utf-8')

    def skip_reason(self) -> Optional[str]:
        if LUAC or HAVE_LUAPARSER:
            return None
        return ('no Lua syntax checker on this host: install Lua (luac) or '
                '`pip install luaparser` to run this test')

    def test_luac_accepts_the_shipped_file(self):
        if not LUAC:
            self.skipTest(f'luac is not installed ({self.skip_reason()})')
        for path in (SHIPPED,):
            with self.subTest(path=path.name):
                result = subprocess.run([LUAC, '-p', str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_luac_accepts_a_render_of_every_intensity(self):
        if not LUAC:
            self.skipTest('luac is not installed')
        tk = tokens()
        with tempfile.TemporaryDirectory() as tmp:
            for name in tk['intensities']:
                with self.subTest(intensity=name):
                    source = glass.build(tk, glass.load_preset(tk, None), name)
                    path = Path(tmp) / f'glass-{name}.lua'
                    path.write_text(source, encoding='utf-8')
                    result = subprocess.run([LUAC, '-p', str(path)],
                                            capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_luaparser_accepts_the_shipped_file(self):
        if not HAVE_LUAPARSER:
            self.skipTest('luaparser is not installed')
        tree = lua_ast.parse(self.source)  # raises on a syntax error
        self.assertGreater(len(tree.body.body), 0)

    def test_luaparser_accepts_a_render_of_every_preset_and_intensity(self):
        if not HAVE_LUAPARSER:
            self.skipTest('luaparser is not installed')
        tk = tokens()
        for preset_path in sorted(PRESET_DIR.glob('*.json')):
            for intensity in tk['intensities']:
                with self.subTest(preset=preset_path.stem, intensity=intensity):
                    source = glass.build(tk, glass.load_preset(tk, preset_path.stem),
                                         intensity)
                    lua_ast.parse(source)

    def test_the_render_is_a_sequence_of_hl_calls_and_nothing_else(self):
        if not HAVE_LUAPARSER:
            self.skipTest('luaparser is not installed')
        tree = lua_ast.parse(self.source)

        def dotted(node):
            parts = []
            while isinstance(node, lua_ast.Index):
                parts.append(node.idx.id)
                node = node.value
            parts.append(getattr(node, 'id', '?'))
            return '.'.join(reversed(parts))

        targets = {dotted(call.func) for call in tree.body.body}
        self.assertEqual({'hl.config', 'hl.layer_rule', 'hl.window_rule'}, targets)

    def test_the_structural_fallback_catches_an_unbalanced_brace(self):
        # The fallback exists for hosts with no Lua at all; prove it is not a
        # no-op by feeding it the three mistakes a table emitter makes.
        for broken in ('hl.config({ general = { gaps_in = 6 }',
                       'hl.config({ general = { gaps_in = 6 } }) )',
                       'hl.config({ name = "unterminated })'):
            with self.subTest(broken=broken[:40]):
                self.assertTrue(glass.sanity_check_lua(broken))

    def test_the_structural_fallback_accepts_a_trailing_comma(self):
        # A trailing comma before a closing brace is legal Lua and the emitter
        # always writes one, so the fallback must not flag it.
        self.assertEqual([], glass.sanity_check_lua('hl.config({ general = { gaps_in = 6, }, })\n'))

    def test_the_structural_fallback_accepts_the_shipped_file(self):
        self.assertEqual([], glass.sanity_check_lua(self.source))


class EveryLeafIsOneHyprlandKnows(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()
        self.known = {lua_leaf_name(leaf): leaf for leaf in self.tk['hyprland']['leaves']}

    def test_every_emitted_key_resolves_to_a_whitelisted_leaf(self):
        leaves = resolved_leaves(self.tk)
        self.assertTrue(leaves)
        for leaf in leaves:
            with self.subTest(leaf=leaf):
                self.assertIn(leaf, self.tk['hyprland']['leaves'])

    def test_the_dotted_border_leaves_resolve_the_way_upstream_names_them(self):
        # general:col.active_border is one leaf whose *name* contains a dot, so
        # the Lua table nests general -> col -> active_border. Emitting
        # general:col:active_border instead would be an unknown config key.
        leaves = resolved_leaves(self.tk)
        self.assertIn('general:col.active_border', leaves)
        self.assertIn('general:col.inactive_border', leaves)
        self.assertNotIn('general:col:active_border', self.tk['hyprland']['leaves'])

    def test_an_unknown_key_anywhere_in_the_table_is_caught(self):
        table = emitted_config(self.tk)
        table['decoration']['corner_radius'] = 12  # invented, and not a table
        with self.assertRaises(AssertionError):
            walk_config(table, self.known)

    def test_checked_refuses_a_leaf_outside_the_whitelist(self):
        with self.assertRaises(glass.GlassError) as caught:
            glass.checked(self.tk, 'decoration:blur:amount', 8, [])
        self.assertIn('hyprland.leaves', str(caught.exception))

    def test_checked_refuses_a_value_outside_the_upstream_range(self):
        with self.assertRaises(glass.GlassError) as caught:
            glass.checked(self.tk, 'decoration:blur:size', 999, [])
        self.assertIn('range', str(caught.exception))

    def test_the_render_refuses_a_preset_with_an_invented_accent_role(self):
        tk = mutate(self.tk, 'layout.border.active.from_role', 'neon')
        with self.assertRaises(glass.GlassError):
            glass.general_block(tk, glass.load_preset(tk, None), [])


class IntegersStayIntegers(unittest.TestCase):
    """``CLuaConfigInt::parse`` takes only ``lua_isinteger``: 10.0 is an error."""

    def setUp(self):
        self.tk = tokens()
        self.source = SHIPPED.read_text(encoding='utf-8')
        self.last_segment = {leaf.rsplit(':', 1)[-1]: leaf
                             for leaf in self.tk['hyprland']['integer_leaves']}

    def test_the_integer_leaves_are_the_ones_upstream_declares_ms_int(self):
        # Grounded in ConfigValues.cpp at the verified version: these seven are
        # MS<Int>. rounding_power looks integral but is MS<Float>, and the gaps
        # are MS<CssGap>, so none of them belong in this list.
        self.assertEqual({
            'decoration:rounding', 'decoration:blur:variant', 'decoration:blur:size',
            'decoration:blur:passes', 'decoration:shadow:range',
            'decoration:shadow:render_power', 'general:border_size',
        }, set(self.tk['hyprland']['integer_leaves']))

    def test_every_integer_leaf_is_a_declared_leaf(self):
        for leaf in self.tk['hyprland']['integer_leaves']:
            with self.subTest(leaf=leaf):
                self.assertIn(leaf, self.tk['hyprland']['leaves'])

    def test_no_integer_leaf_is_rendered_with_a_fraction(self):
        for key, leaf in self.last_segment.items():
            if key == 'variant':
                continue  # an enum: rendered as its string key, not a number
            literals = number_after(self.source, key)
            with self.subTest(leaf=leaf):
                self.assertTrue(literals, f'{key} was not rendered at all')
                for literal in literals:
                    self.assertNotIn('.', literal,
                                     f'{leaf} rendered as {literal}; Hyprland wants an integer')

    def test_the_blur_variant_is_rendered_as_a_known_string_key(self):
        # MS<Int> with an OptionMap, so LuaConfigInt accepts the name as a string.
        match = re.search(r'variant\s*=\s*"([a-z_]+)"', self.source)
        self.assertIsNotNone(match, 'blur variant was not rendered')
        self.assertIn(match.group(1), self.tk['hyprland']['blur_variants'])

    def test_a_fractional_token_for_an_integer_leaf_is_refused(self):
        tk = mutate(self.tk, 'intensities.frosted.blur.size', 10.5)
        with self.assertRaises(glass.GlassError) as caught:
            glass.decoration_block(tk, 'frosted', [])
        self.assertIn('integer', str(caught.exception))

    def test_an_integral_float_token_is_coerced_rather_than_rejected(self):
        tk = mutate(self.tk, 'intensities.frosted.blur.size', 10.0)
        warnings: List[str] = []
        block = glass.decoration_block(tk, 'frosted', warnings)
        self.assertEqual(10, block['blur']['size'])
        self.assertIsInstance(block['blur']['size'], int)

    def test_rounding_power_may_carry_a_fraction_because_it_is_a_float_leaf(self):
        self.assertNotIn('decoration:rounding_power', self.tk['hyprland']['integer_leaves'])
        literals = number_after(self.source, 'rounding_power')
        self.assertTrue(literals)
        self.assertIn('.', literals[0],
                      'rounding_power is MS<Float> upstream; rendering it as a bare '
                      'integer would lose the distinction the note documents')

    def test_the_gaps_are_rendered_as_integers_the_css_gap_type_accepts(self):
        for key in ('gaps_in', 'gaps_out', 'float_gaps'):
            with self.subTest(key=key):
                literals = number_after(self.source, key)
                self.assertTrue(literals)
                for literal in literals:
                    self.assertNotIn('.', literal)


class ValuesStayInsideUpstreamRanges(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()
        self.ranges = self.tk['hyprland']['ranges']

    def test_every_ranged_token_in_every_intensity_is_inside_its_bounds(self):
        for name, intensity in self.tk['intensities'].items():
            for leaf, (low, high) in self.ranges.items():
                value = self.dig(intensity, leaf)
                if value is None:
                    continue
                with self.subTest(intensity=name, leaf=leaf):
                    self.assertGreaterEqual(value, low)
                    self.assertLessEqual(value, high)

    @staticmethod
    def dig(intensity: Dict[str, Any], leaf: str) -> Optional[Any]:
        """Find a leaf's value inside one intensity, by its trailing segments."""
        tail = leaf.split(':')[-1]
        section = leaf.split(':')[-2] if leaf.count(':') > 1 else None

        def walk(node: Any) -> Any:
            if isinstance(node, dict):
                if tail in node and not isinstance(node[tail], dict):
                    return node[tail]
                if section and section in node:
                    return walk(node[section])
                for value in node.values():
                    found = walk(value)
                    if found is not None:
                        return found
            return None

        return walk(intensity)

    def test_an_out_of_range_token_is_refused_before_it_is_written(self):
        for path, bad in (('intensities.frosted.blur.size', 999),
                          ('intensities.frosted.shadow.range', 4000),
                          ('intensities.frosted.window.inactive_opacity', 1.4),
                          ('layout.border_size', 90)):
            with self.subTest(path=path):
                tk = mutate(self.tk, path, bad)
                with self.assertRaises(glass.GlassError):
                    emitted_config(tk)

    def test_window_rounding_is_clamped_to_what_the_compositor_accepts(self):
        # radius.pill is 999 by CSS convention; decoration:rounding tops out at
        # 100, so the clamp has to be loud rather than silent.
        tk = mutate(self.tk, 'radius.window', 'pill')
        warnings: List[str] = []
        value = glass.clamped_radius(tk, 'window', warnings)
        low, high = self.ranges['decoration:rounding']
        self.assertEqual(high, value)
        self.assertTrue(warnings, 'a clamp must be reported')
        self.assertIn('clamped', warnings[0])

    def test_the_shipped_render_warns_about_nothing_it_should_have_clamped(self):
        header = self_source_header()
        self.assertNotIn('clamped', header,
                         'the shipped default uses radius.md, so a clamp warning '
                         'would mean the tokens changed without a re-render')


class ColoursAndGradients(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()
        self.source = SHIPPED.read_text(encoding='utf-8')

    def test_every_colour_is_emitted_in_a_form_hyprland_parses(self):
        colours = parse_rgba(self.source)
        self.assertGreater(len(colours), 3)
        for red, green, blue, alpha in colours:
            for channel in (red, green, blue):
                self.assertTrue(0 <= channel <= 255)
            self.assertTrue(0.0 <= alpha <= 1.0)

    def test_no_bare_hex_colour_leaks_into_the_lua(self):
        # ParserUtils::parseColor does accept #rrggbb, but the tokens carry hex
        # and the renderer owns the conversion; a leaked '#' means a preset value
        # was passed through unconverted and its alpha was silently dropped.
        assignments = re.findall(r'=\s*"([^"]*)"', self.source)
        for value in assignments:
            with self.subTest(value=value):
                self.assertFalse(value.startswith('#'),
                                 f'{value} reached the Lua unconverted')

    def test_the_active_border_is_a_gradient_with_two_colours_and_an_angle(self):
        leaves = resolved_leaves(self.tk)
        gradient = leaves['general:col.active_border']
        self.assertIsInstance(gradient, dict)
        self.assertEqual(2, len(gradient['colors']),
                         'CLuaConfigGradient::parse rejects an empty or single '
                         'colour list where a gradient is intended')
        self.assertEqual(self.tk['layout']['border']['angle_deg'], gradient['angle'])
        for colour in gradient['colors']:
            self.assertRegex(colour, r'^rgba\(\d+, \d+, \d+, [\d.]+\)$')

    def test_the_inactive_border_is_a_single_colour_not_a_gradient(self):
        leaves = resolved_leaves(self.tk)
        self.assertRegex(leaves['general:col.inactive_border'],
                         r'^rgba\(\d+, \d+, \d+, [\d.]+\)$')

    def test_the_shadow_colours_carry_the_intensity_alpha(self):
        shadow = resolved_leaves(self.tk)['decoration:shadow:color']
        alpha = self.tk['intensities']['frosted']['glass']['shadow_alpha']
        self.assertTrue(shadow.endswith(f'{alpha})'), shadow)

    def test_an_alpha_outside_zero_to_one_is_refused(self):
        with self.assertRaises(glass.GlassError):
            glass.rgba('#101010', 1.4, 'test.alpha')
        with self.assertRaises(glass.GlassError):
            glass.rgba('#101010', -0.2, 'test.alpha')

    def test_a_malformed_hex_colour_is_refused_with_its_location(self):
        for bad in ('101010', '#12345', '#gggggg', 'rgb(1,2,3)'):
            with self.subTest(bad=bad):
                with self.assertRaises(glass.GlassError) as caught:
                    glass.rgba(bad, 0.5, 'palette.accent.primary')
                self.assertIn('palette.accent.primary', str(caught.exception))

    def test_the_preset_accent_reaches_the_border(self):
        preset = glass.load_preset(self.tk, 'aurora')
        accent = preset['palette']['accent']
        border = self.tk['layout']['border']['active']
        expected = glass.rgba(accent[border['from_role']], border['from_alpha'], 'x')
        leaves = resolved_leaves(self.tk, preset_id='aurora')
        self.assertIn(expected, leaves['general:col.active_border']['colors'])


class LayerRulesFollowTheSurfaces(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()
        self.entries = self.tk['surfaces']['entries']
        self.rules = glass.layer_rules(self.tk, 'frosted')

    def test_every_surface_gets_exactly_one_named_rule(self):
        self.assertEqual(len(self.entries), len(self.rules))
        names = re.findall(r'name = "([^"]+)"', ' '.join(self.rules))
        self.assertEqual(len(set(names)), len(names), 'rule names must be unique')
        for entry in self.entries:
            self.assertIn(f'iarch-glass-{entry["id"]}', names)

    def test_every_rule_matches_on_its_namespace_and_nothing_invented(self):
        allowed = set(self.tk['hyprland']['rule_match_properties'])
        for entry, rule in zip(self.entries, self.rules):
            with self.subTest(surface=entry['id']):
                self.assertIn(f'namespace = "{entry["namespace"]}"', rule)
                keys = match_keys(rule)
                self.assertEqual({'namespace'}, keys)
                self.assertTrue(keys <= allowed, f'unknown match properties: {keys}')

    def test_every_effect_is_one_the_rule_engine_knows(self):
        allowed = set(self.tk['hyprland']['layer_rule_effects'])
        for rule in self.rules:
            keys = top_level_keys(rule) - {'name', 'match'}
            with self.subTest(rule=sorted(keys)):
                self.assertTrue(keys, 'a rule with no effect does nothing')
                self.assertTrue(keys <= allowed, f'unknown layer effects: {keys - allowed}')

    def test_blur_follows_the_intensity(self):
        off = glass.layer_rules(self.tk, 'performance')
        self.assertNotIn('blur = true', ' '.join(off),
                         'the Performance intensity must not blur any layer')
        self.assertIn('blur = true', ' '.join(self.rules))

    def test_ignore_alpha_survives_a_disabled_blur(self):
        # ignore_alpha is what stops a translucent panel from punching a hole in
        # the blur; it is independent of whether blur is on.
        off = ' '.join(glass.layer_rules(self.tk, 'performance'))
        self.assertIn('ignore_alpha', off)

    def test_an_unknown_layer_effect_is_refused(self):
        tk = mutate(self.tk, 'surfaces.entries.0.glass', True)
        with self.assertRaises(glass.GlassError) as caught:
            glass.layer_rules(tk, 'frosted')
        self.assertIn('glass', str(caught.exception))

    def test_the_unverified_namespaces_are_disclosed_in_the_header(self):
        self.assertFalse(self.tk['surfaces']['verified'])
        header = self_source_header()
        self.assertIn('SES-02', header)
        self.assertIn('iarch-doctor layers', header)


class WindowRulesFollowTheClassGroups(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()
        self.rules = glass.window_rules(self.tk, 'frosted')
        self.groups = {group: patterns for group, patterns
                       in self.tk['app_classes'].items() if group != '_note'}
        self.opacity = self.tk['window_opacity']

    def test_every_class_pattern_gets_a_rule(self):
        joined = '\n'.join(self.rules)
        for group, patterns in self.groups.items():
            for pattern in patterns:
                with self.subTest(group=group, pattern=pattern):
                    escaped = pattern.replace('\\', '\\\\')
                    self.assertIn(f'class = "{escaped}"', joined)

    def test_each_group_carries_the_opacity_the_tokens_assign_it(self):
        for group, patterns in self.groups.items():
            expected = self.opacity[group]
            for pattern in patterns:
                rule = next(r for r in self.rules
                            if pattern.replace('\\', '\\\\') in r)
                with self.subTest(group=group, pattern=pattern):
                    self.assertIn(f'opacity = {expected}', rule)

    def test_terminals_are_the_most_translucent_and_browsers_are_not(self):
        self.assertLess(self.opacity['terminal'], self.opacity['file_manager'])
        self.assertLess(self.opacity['file_manager'], self.opacity['editor'])
        self.assertEqual(1.0, self.opacity['browser'])
        self.assertEqual(1.0, self.opacity['video'])

    def test_opaque_always_windows_lose_blur_and_dimming(self):
        for pattern in self.groups['opaque_always']:
            rule = next(r for r in self.rules if pattern.replace('\\', '\\\\') in r)
            with self.subTest(pattern=pattern):
                self.assertIn('no_blur = true', rule)
                self.assertIn('no_dim = true', rule)
                self.assertIn(f'opacity = {self.opacity["opaque_always"]}', rule)

    def test_the_fullscreen_override_is_registered_last_so_it_wins(self):
        # WindowRuleApplicator::readStaticRules walks rules in registration order
        # and assigns opacity unconditionally, so the last matching rule wins.
        self.assertIn('iarch-glass-fullscreen', self.rules[-1])
        self.assertIn('fullscreen = true', self.rules[-1])
        self.assertIn('no_blur = true', self.rules[-1])
        self.assertIn(f'opacity = {self.opacity["fullscreen_override"]}', self.rules[-1])

    def test_every_effect_and_match_property_is_one_upstream_knows(self):
        allowed = set(self.tk['hyprland']['window_rule_effects'])
        properties = set(self.tk['hyprland']['rule_match_properties'])
        for rule in self.rules:
            keys = top_level_keys(rule) - {'name', 'match'}
            matched = match_keys(rule)
            with self.subTest(rule=sorted(keys)):
                self.assertTrue(keys <= allowed, f'unknown window effects: {keys - allowed}')
                self.assertTrue(matched <= properties,
                                f'unknown match properties: {matched - properties}')
                self.assertTrue(matched, 'a rule that matches nothing matches everything')

    def test_an_unknown_window_effect_is_refused(self):
        tk = mutate(self.tk, 'window_opacity.terminal', 0.8)
        tk['hyprland']['window_rule_effects'] = ['opacity']  # no_blur/no_dim now unknown
        with self.assertRaises(glass.GlassError) as caught:
            glass.window_rules(tk, 'frosted')
        self.assertIn('no_blur', str(caught.exception))

    def test_no_animation_is_emitted_because_that_is_part_three(self):
        source = glass.build(self.tk, glass.load_preset(self.tk, None), 'frosted')
        self.assertNotIn('hl.animation', source)
        self.assertNotIn('animation =', source,
                         'animations.lua owns motion; this renderer must not touch it')

    def test_animations_lua_is_left_alone(self):
        self.assertTrue(ANIMATIONS.is_file())
        source = ANIMATIONS.read_text(encoding='utf-8')
        self.assertNotIn('glass', source.lower())


class ThePerformanceIntensityCostsNothing(unittest.TestCase):
    """Every effect must be switchable, and one preset must cost nothing."""

    def setUp(self):
        self.tk = tokens()
        self.block = glass.decoration_block(self.tk, 'performance', [])
        self.source = glass.build(self.tk, glass.load_preset(self.tk, None), 'performance')

    def test_blur_is_off_and_carries_no_passes(self):
        self.assertFalse(self.block['blur']['enabled'])
        self.assertEqual(0, self.block['blur']['size'])
        self.assertEqual(0, self.block['blur']['passes'])
        self.assertNotIn('enabled = true,\n            variant', self.source,
                         'the blur block must be disabled under Performance')

    def test_shadows_are_off_and_have_no_range(self):
        self.assertFalse(self.block['shadow']['enabled'])
        self.assertEqual(0, self.block['shadow']['range'])

    def test_the_shadow_colour_is_fully_transparent(self):
        self.assertTrue(self.block['shadow']['color'].endswith('0.0)}')
                        or self.block['shadow']['color'].endswith(', 0.0)'),
                        self.block['shadow']['color'])

    def test_inactive_dimming_is_off(self):
        self.assertFalse(self.block['dim_inactive'])
        self.assertEqual(0.0, self.block['dim_strength'])

    def test_no_layer_is_blurred_under_performance(self):
        self.assertNotIn('blur = true', ' '.join(glass.layer_rules(self.tk, 'performance')))

    def test_the_frosted_default_does_blur(self):
        block = glass.decoration_block(self.tk, 'frosted', [])
        self.assertTrue(block['blur']['enabled'])
        self.assertTrue(block['shadow']['enabled'])
        self.assertGreater(block['blur']['size'], 0)

    def test_every_intensity_renders_without_a_warning_about_cost_except_the_animated(self):
        for name, intensity in self.tk['intensities'].items():
            warnings: List[str] = []
            glass.decoration_block(self.tk, name, warnings)
            animated = intensity['blur']['variant'] in self.tk['hyprland']['animated_blur_variants']
            with self.subTest(intensity=name):
                self.assertEqual(animated, any('animates' in w for w in warnings))


class TheShippedFileMatchesItsSource(unittest.TestCase):
    def setUp(self):
        self.tk = tokens()

    def test_check_passes_on_the_committed_default(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = glass.main(['--check'])
        self.assertEqual(0, code, err.getvalue())

    def test_check_fails_when_the_committed_file_drifts(self):
        original = glass.REPO_DEFAULT
        with tempfile.TemporaryDirectory() as tmp:
            drifted = Path(tmp) / 'glass.lua'
            drifted.write_text(original.read_text(encoding='utf-8')
                               .replace('gaps_in = 6', 'gaps_in = 7'), encoding='utf-8')
            glass.REPO_DEFAULT = drifted
            try:
                err = StringIO()
                with redirect_stdout(StringIO()), redirect_stderr(err):
                    code = glass.main(['--check'])
                self.assertEqual(1, code)
                self.assertIn('does not match', err.getvalue())
            finally:
                glass.REPO_DEFAULT = original

    def test_check_fails_when_the_committed_file_is_missing(self):
        original = glass.REPO_DEFAULT
        with tempfile.TemporaryDirectory() as tmp:
            glass.REPO_DEFAULT = Path(tmp) / 'absent.lua'
            try:
                err = StringIO()
                with redirect_stdout(StringIO()), redirect_stderr(err):
                    self.assertEqual(1, glass.main(['--check']))
                self.assertIn('missing', err.getvalue())
            finally:
                glass.REPO_DEFAULT = original

    def test_rendering_is_deterministic(self):
        first = glass.build(self.tk, glass.load_preset(self.tk, None), 'frosted')
        second = glass.build(self.tk, glass.load_preset(self.tk, None), 'frosted')
        self.assertEqual(first, second)

    def test_the_shipped_file_carries_the_generated_header(self):
        text = SHIPPED.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(configstore.header_for(SHIPPED)),
                        'a generated file must say so on its first line')
        self.assertIn('GENERATED', text.splitlines()[0].upper())

    def test_the_header_names_its_sources_and_the_verified_version(self):
        header = self_source_header()
        self.assertIn('data/design/tokens.json', header)
        self.assertIn('midnight-glass.json', header)
        self.assertIn(self.tk['hyprland']['verified_against'], header)

    def test_writing_the_default_again_changes_nothing(self):
        before = SHIPPED.read_bytes()
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = glass.main(['--write-repo-default'])
        self.assertEqual(0, code, err.getvalue())
        self.assertEqual(before, SHIPPED.read_bytes())

    def test_the_static_theme_falls_back_when_the_generated_file_is_absent(self):
        # theme.lua must require the generated file through pcall, so a session
        # with no design system applied still starts.
        text = THEME.read_text(encoding='utf-8')
        self.assertIn('pcall(function()', text)
        self.assertIn('require("generated.glass")', text)
        self.assertLess(text.index('hl.config({'), text.index('require("generated.glass")'),
                        'the generated file must be required after the static '
                        'values, because the last rule registered wins')


class TheCliBehaves(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._env = {key: os.environ.get(key) for key in
                     ('IARCH_CONFIG_DIR', 'IARCH_STATE_DIR')}
        os.environ['IARCH_CONFIG_DIR'] = str(Path(self.tmp) / 'config')
        os.environ['IARCH_STATE_DIR'] = str(Path(self.tmp) / 'state')
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def run_cli(self, argv: List[str]) -> Tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = glass.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_print_writes_the_render_to_stdout_and_nothing_to_disk(self):
        code, out, err = self.run_cli(['--print'])
        self.assertEqual(0, code, err)
        self.assertIn('hl.config(', out)
        self.assertEqual([], list(Path(self.tmp).rglob('glass.lua')))

    def test_the_default_destination_is_inside_the_user_config_dir(self):
        self.assertEqual(Path(self.tmp) / 'config' / 'hypr' / 'generated' / 'glass.lua',
                         glass.target_path())

    def test_a_bare_run_writes_the_user_file_with_the_generated_header(self):
        code, out, err = self.run_cli([])
        self.assertEqual(0, code, err)
        written = glass.target_path()
        self.assertTrue(written.is_file())
        text = written.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(configstore.header_for(written)))
        self.assertIn('hl.layer_rule(', text)
        self.assertIn(str(written), out)

    def test_a_second_run_keeps_a_backup_of_the_first(self):
        self.run_cli([])
        first = glass.target_path().read_text(encoding='utf-8')
        self.run_cli(['--intensity', 'performance'])
        backups = sorted(configstore.backup_dir().glob('*.bak'))
        self.assertTrue(backups, 'overwriting a generated file must back it up')
        self.assertEqual(first, backups[-1].read_text(encoding='utf-8'))

    def test_an_explicit_output_path_is_honoured(self):
        destination = Path(self.tmp) / 'elsewhere' / 'glass.lua'
        code, out, err = self.run_cli(['--output', str(destination)])
        self.assertEqual(0, code, err)
        self.assertTrue(destination.is_file())
        self.assertEqual([], list(glass.target_path().parent.glob('*.lua')),
                         '--output must not also write the user config')

    def test_every_preset_and_intensity_combination_renders(self):
        for preset_path in sorted(PRESET_DIR.glob('*.json')):
            for intensity in tokens()['intensities']:
                with self.subTest(preset=preset_path.stem, intensity=intensity):
                    code, out, err = self.run_cli(['--preset', preset_path.stem,
                                                   '--intensity', intensity, '--print'])
                    self.assertEqual(0, code, err)
                    self.assertIn('hl.config(', out)

    def test_an_unknown_preset_exits_two_and_says_why(self):
        code, out, err = self.run_cli(['--preset', 'vaporwave'])
        self.assertEqual(2, code)
        self.assertIn('vaporwave', err)
        self.assertEqual('', out)

    def test_an_unknown_intensity_exits_two(self):
        code, _, err = self.run_cli(['--intensity', 'ultra'])
        self.assertEqual(2, code)
        self.assertIn('ultra', err)

    def test_a_preset_file_that_declares_the_wrong_id_exits_two(self):
        original = glass.PRESET_DIR
        shadow = Path(self.tmp) / 'presets'
        shadow.mkdir()
        preset = read_json(original / 'aurora.json')
        preset['id'] = 'someone-else'
        (shadow / 'aurora.json').write_text(json.dumps(preset), encoding='utf-8')
        glass.PRESET_DIR = shadow
        try:
            code, _, err = self.run_cli(['--preset', 'aurora', '--print'])
            self.assertEqual(2, code)
            self.assertIn('someone-else', err)
        finally:
            glass.PRESET_DIR = original

    def test_a_missing_tokens_file_exits_two_rather_than_raising(self):
        original = glass.TOKENS_PATH
        glass.TOKENS_PATH = Path(self.tmp) / 'absent.json'
        try:
            code, _, err = self.run_cli(['--print'])
            self.assertEqual(2, code)
            self.assertIn('absent.json', err)
        finally:
            glass.TOKENS_PATH = original

    def test_the_intensity_defaults_to_the_preset_then_to_the_tokens(self):
        _, out, _ = self.run_cli(['--print'])
        self.assertIn(f"intensity={tokens()['default_intensity']}", out)

    def test_a_rendered_file_never_contains_a_python_artefact(self):
        _, out, _ = self.run_cli(['--print'])
        for artefact in ('None', 'True', 'False', "{'", 'nan'):
            with self.subTest(artefact=artefact):
                self.assertNotIn(artefact, out,
                                 'a Python repr leaked into the Lua')


class StaticPinsDoNotContradictTheDesignSystem(unittest.TestCase):
    """windowrules.lua and the generator must not both own one window's opacity."""

    def setUp(self):
        self.tk = tokens()
        self.groups = {group: patterns for group, patterns
                       in self.tk['app_classes'].items() if group != '_note'}
        self.pins = self.read_pins()

    def read_pins(self) -> List[Tuple[str, str]]:
        text = WINDOWRULES.read_text(encoding='utf-8')
        block = text[text.index('-- Opacity rules'):]
        return re.findall(r'match = \{ (class|initial_title) = "([^"]+)" \},\s+opacity = 1\.0',
                          block)

    @staticmethod
    def variants(pattern: str) -> List[str]:
        """^[Cc]ode$ stands for both Code and code."""
        body = pattern.strip('^$').replace('\\.', '.')

        def expand(text: str) -> List[str]:
            match = re.search(r'\[([A-Za-z])([A-Za-z])\]', text)
            if not match:
                return [text]
            out = []
            for pick in (match.group(1), match.group(2)):
                out += expand(text[:match.start()] + pick + text[match.end():])
            return out

        return expand(body)

    def test_no_pinned_class_is_one_the_design_system_classifies(self):
        compiled = {group: [re.compile(p) for p in patterns]
                    for group, patterns in self.groups.items()}
        contradictions = []
        for kind, literal in self.pins:
            raw = literal.replace('\\\\', '\\')
            for candidate in self.variants(raw):
                for group, regexes in compiled.items():
                    if any(r.fullmatch(candidate) for r in regexes):
                        contradictions.append((candidate, group))
        self.assertEqual([], contradictions,
                         'windowrules.lua pins opacity 1.0 for a class the design '
                         'system owns; remove the pin or the classification, not both')

    def test_the_generator_really_does_cover_every_classified_pattern(self):
        source = SHIPPED.read_text(encoding='utf-8')
        for group, patterns in self.groups.items():
            for pattern in patterns:
                with self.subTest(group=group, pattern=pattern):
                    self.assertIn(pattern.replace('\\', '\\\\'), source)

    def test_the_pin_block_explains_why_the_owned_classes_are_absent(self):
        text = WINDOWRULES.read_text(encoding='utf-8')
        block = text[text.index('-- Opacity rules'):text.index('hl.window_rule', text.index('-- Opacity rules'))]
        self.assertIn('generated/glass.lua', block)
        self.assertIn('app_classes', block)


def self_source_header() -> str:
    """The comment header of the shipped render."""
    lines = SHIPPED.read_text(encoding='utf-8').splitlines()
    return '\n'.join(line for line in lines if line.startswith('--'))


if __name__ == '__main__':
    unittest.main()
