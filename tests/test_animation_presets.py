# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove the animation presets are the ones Hyprland accepts and the brief asks for.

tests/test_animations_lua.py proves the *render*: that what lands in the generated
file is Lua, and that every value in it is inside the bounds the pinned release
enforces. This file proves the *data* behind it, which is the part a person edits:

* every preset is one of the five the tokens name, is the file its name says it is,
  and declares the same eighteen events, so ``iarch-anim current`` and ``list``
  never have to special-case a preset;
* every leaf exists in the recorded surface, every style is one that leaf accepts,
  every curve an event names is one the preset declares, and every declared curve
  is used by something — no dead data in either direction;
* the numbers sit inside the bounds the surface records, read from the surface
  rather than repeated here, so this file fails if the record and the data ever
  disagree;
* the presets mean what their names say: smooth mirrors the shared motion tokens,
  snappy is never slower than smooth, bouncy overshoots only where an overshoot is
  a position and not an opacity, minimal moves nothing, and off turns the master
  switch off;
* the two switches that say the same thing — an intensity's ``motion.enabled`` and
  its ``motion.preset`` — agree, and the settings schema's multiplier bounds are
  the tokens' bounds.

The vocabulary checks cannot live in the preset schema: whether a leaf exists, or
whether that leaf takes the style named for it, is recorded in a second document,
and a schema cannot read another file. That is what this file is for.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_animations_lua as anim  # noqa: E402

TOKENS_PATH = ROOT / 'data' / 'design' / 'tokens.json'
SURFACE_PATH = ROOT / 'data' / 'design' / 'animations.json'
PRESET_DIR = ROOT / 'data' / 'design' / 'animations'
PRESET_SCHEMA = ROOT / 'data' / 'schemas' / 'animations_preset.schema.json'
TOKENS_SCHEMA = ROOT / 'data' / 'schemas' / 'tokens.schema.json'
SETTINGS_SCHEMA = ROOT / 'data' / 'schemas' / 'settings.schema.json'
SETTINGS_DEFAULT = ROOT / 'data' / 'settings.default.json'

# The eighteen events the design brief names, which every preset declares so that
# a caller in Part 4 or Part 5 sees the same event set whatever is active.
BRIEF_EVENTS: Set[str] = {
    'windows', 'windowsIn', 'windowsOut', 'windowsMove',
    'fade', 'fadeIn', 'fadeOut', 'fadeSwitch', 'fadeShadow', 'fadeDim', 'fadeLayers',
    'border', 'borderangle',
    'workspaces', 'specialWorkspace',
    'layers', 'layersIn', 'layersOut',
}

# Leaves that move something rather than fading it: the window transform set, the
# workspace slides and the looping gradient sweep. These are what a reduce-motion
# mode has to remove, and what minimal removes.
TRANSFORM_EVENTS: Set[str] = {
    'windows', 'windowsIn', 'windowsOut', 'windowsMove',
    'workspaces', 'specialWorkspace', 'borderangle',
}

PRESET_NAMES = ('smooth', 'snappy', 'bouncy', 'minimal', 'off')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def tokens() -> Dict[str, Any]:
    return read_json(TOKENS_PATH)


def surface() -> Dict[str, Any]:
    return read_json(SURFACE_PATH)


def preset(name: str) -> Dict[str, Any]:
    return read_json(PRESET_DIR / f'{name}.json')


def all_presets() -> Dict[str, Dict[str, Any]]:
    return {name: preset(name) for name in PRESET_NAMES}


def leaves() -> Dict[str, Any]:
    return surface()['leaves']


def enabled_events(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {leaf: event for leaf, event in doc['events'].items() if event['enabled']}


def bezier_components(doc: Dict[str, Any]) -> List[float]:
    return [component
            for curve in doc['curves'].values() if curve['type'] == 'bezier'
            for point in curve['points'] for component in point]


class TheFamilyIsTheOneTheTokensName(unittest.TestCase):
    def test_the_five_files_exist_and_nothing_else_is_in_the_directory(self):
        on_disk = {path.stem for path in PRESET_DIR.glob('*.json')}
        self.assertEqual(set(PRESET_NAMES), on_disk)

    def test_the_tokens_name_exactly_those_five(self):
        self.assertEqual(list(PRESET_NAMES), list(tokens()['motion']['animation']['presets']))

    def test_the_generator_resolves_the_same_five(self):
        self.assertEqual(PRESET_NAMES, anim.preset_names(tokens()))

    def test_the_default_preset_is_one_of_them(self):
        self.assertIn(anim.default_preset(tokens()), PRESET_NAMES)
        self.assertEqual('smooth', anim.default_preset(tokens()))

    def test_the_settings_schema_allows_exactly_those_five(self):
        schema = read_json(SETTINGS_SCHEMA)
        allowed = schema['properties']['animation']['properties']['preset']['enum']
        self.assertEqual(list(PRESET_NAMES), allowed)

    def test_the_tokens_schema_allows_exactly_those_five(self):
        schema = read_json(TOKENS_SCHEMA)
        block = schema['properties']['motion']['properties']['animation']['properties']
        self.assertEqual(list(PRESET_NAMES), block['default_preset']['enum'])
        self.assertEqual(list(PRESET_NAMES), block['presets']['items']['enum'])
        for intensity in schema['definitions']['intensity']['properties']['motion']['properties']:
            if intensity == 'preset':
                self.assertEqual(list(PRESET_NAMES),
                                 schema['definitions']['intensity']['properties']['motion']
                                 ['properties']['preset']['enum'])

    def test_the_shipped_settings_default_selects_the_default_preset(self):
        self.assertEqual(anim.default_preset(tokens()),
                         read_json(SETTINGS_DEFAULT)['animation']['preset'])

    def test_each_file_is_the_preset_it_is_named_after(self):
        for name in PRESET_NAMES:
            with self.subTest(preset=name):
                self.assertEqual(name, preset(name)['name'])
                self.assertEqual(name, anim.load_preset(name)['name'])

    def test_every_preset_validates_against_the_preset_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest('jsonschema not installed; CI validates with the library')
        schema = read_json(PRESET_SCHEMA)
        for name in PRESET_NAMES:
            with self.subTest(preset=name):
                jsonschema.validate(preset(name), schema)


class EveryEventIsOneHyprlandKnows(unittest.TestCase):
    def setUp(self):
        self.leaves = leaves()

    def test_every_preset_declares_the_eighteen_events_the_brief_names(self):
        for name, doc in all_presets().items():
            with self.subTest(preset=name):
                self.assertEqual(BRIEF_EVENTS, set(doc['events']))

    def test_every_event_leaf_exists_in_the_recorded_tree(self):
        for name, doc in all_presets().items():
            for leaf in doc['events']:
                with self.subTest(preset=name, leaf=leaf):
                    self.assertIn(leaf, self.leaves)

    def test_every_enabled_event_names_a_style_only_where_one_is_accepted(self):
        for name, doc in all_presets().items():
            for leaf, event in enabled_events(doc).items():
                allowed = self.leaves[leaf]['styles']
                with self.subTest(preset=name, leaf=leaf):
                    if allowed:
                        self.assertIn(event.get('style'), allowed)
                    else:
                        self.assertNotIn('style', event)

    def test_no_preset_uses_the_style_the_brief_invented(self):
        # 'slidefade 20%' is not a Hyprland style: workspaces takes slide,
        # slidevert or fade, and only 'slide' accepts a ' NN%' suffix.
        for name, doc in all_presets().items():
            for leaf, event in doc['events'].items():
                with self.subTest(preset=name, leaf=leaf):
                    self.assertNotEqual('slidefade 20%', event.get('style'))

    def test_a_disabled_event_carries_nothing_but_the_fact_that_it_is_off(self):
        for name, doc in all_presets().items():
            for leaf, event in doc['events'].items():
                if event['enabled']:
                    continue
                with self.subTest(preset=name, leaf=leaf):
                    self.assertEqual({'enabled'}, set(event) - {'_note'})

    def test_an_enabled_event_carries_a_duration_and_a_curve(self):
        for name, doc in all_presets().items():
            for leaf, event in enabled_events(doc).items():
                with self.subTest(preset=name, leaf=leaf):
                    self.assertIn('duration_ms', event)
                    self.assertIn('curve', event)


class CurvesAreDeclaredUsedAndInsideTheBounds(unittest.TestCase):
    def setUp(self):
        self.bezier = surface()['curve_types']['bezier']
        self.floor = surface()['curve_types']['spring']['value_min_exclusive']

    def test_every_event_names_a_curve_the_same_file_declares(self):
        for name, doc in all_presets().items():
            for leaf, event in enabled_events(doc).items():
                with self.subTest(preset=name, leaf=leaf):
                    self.assertIn(event['curve'], doc['curves'])

    def test_every_declared_curve_is_used_by_at_least_one_event(self):
        # Dead data reads like a setting that does something.
        for name, doc in all_presets().items():
            used = {event['curve'] for event in enabled_events(doc).values()}
            with self.subTest(preset=name):
                self.assertEqual(set(doc['curves']), used)

    def test_every_bezier_component_is_inside_the_recorded_band(self):
        low, high = self.bezier['component_min'], self.bezier['component_max']
        for name, doc in all_presets().items():
            for component in bezier_components(doc):
                with self.subTest(preset=name):
                    self.assertGreaterEqual(component, low)
                    self.assertLessEqual(component, high)

    def test_every_bezier_has_two_points_of_two_numbers(self):
        for name, doc in all_presets().items():
            for curve_name, curve in doc['curves'].items():
                if curve['type'] != 'bezier':
                    continue
                with self.subTest(preset=name, curve=curve_name):
                    self.assertEqual(2, len(curve['points']))
                    for point in curve['points']:
                        self.assertEqual(2, len(point))
                        self.assertTrue(all(isinstance(c, (int, float)) for c in point))

    def test_every_spring_value_is_strictly_above_the_floor(self):
        for name, doc in all_presets().items():
            for curve_name, curve in doc['curves'].items():
                if curve['type'] != 'spring':
                    continue
                for key in ('stiffness', 'damping', 'mass'):
                    with self.subTest(preset=name, curve=curve_name, key=key):
                        self.assertGreater(curve[key], self.floor)

    def test_only_the_presets_that_need_a_spring_declare_one(self):
        springs = {name for name, doc in all_presets().items()
                   if any(c['type'] == 'spring' for c in doc['curves'].values())}
        self.assertEqual({'smooth', 'snappy', 'bouncy'}, springs)

    def test_off_declares_no_curve_at_all(self):
        self.assertEqual({}, preset('off')['curves'])


class DurationsAreInsideTheBindingRange(unittest.TestCase):
    def setUp(self):
        self.ceiling = surface()['speed_formula']['speed_max'] * 100

    def test_every_duration_is_a_positive_integer_inside_the_ceiling(self):
        for name, doc in all_presets().items():
            for leaf, event in enabled_events(doc).items():
                with self.subTest(preset=name, leaf=leaf):
                    self.assertIsInstance(event['duration_ms'], int)
                    self.assertGreater(event['duration_ms'], 0)
                    self.assertLessEqual(event['duration_ms'], self.ceiling)

    def test_every_duration_survives_the_slowest_multiplier(self):
        # 0.5 doubles every duration; the longest must still be inside (0, 10000].
        low, _high, _default = anim.multiplier_bounds(tokens())
        for name, doc in all_presets().items():
            for leaf, event in enabled_events(doc).items():
                with self.subTest(preset=name, leaf=leaf):
                    self.assertLessEqual(event['duration_ms'] / low, self.ceiling)


class SmoothIsTheTokens(unittest.TestCase):
    """The default preset must not drift from the shared motion vocabulary."""

    def setUp(self):
        self.motion = tokens()['motion']
        self.doc = preset('smooth')

    def test_its_beziers_are_the_four_token_easings_point_for_point(self):
        for name, curve in self.motion['easing'].items():
            with self.subTest(curve=name):
                self.assertEqual('bezier', self.doc['curves'][name]['type'])
                self.assertEqual(curve['points'], self.doc['curves'][name]['points'])

    def test_its_spring_is_the_token_spring(self):
        for key, value in self.motion['spring'].items():
            with self.subTest(field=key):
                self.assertAlmostEqual(value, self.doc['curves']['spring'][key], places=6)

    def test_its_durations_are_the_token_durations_or_the_documented_sweep(self):
        allowed = {self.motion['fast_ms'], self.motion['normal_ms'], self.motion['slow_ms'],
                   3000}  # the borderangle loop period the static default ships
        for leaf, event in enabled_events(self.doc).items():
            with self.subTest(leaf=leaf):
                self.assertIn(event['duration_ms'], allowed)

    def test_the_transform_events_sit_in_the_band_the_brief_asks_for(self):
        # 220-380 ms for the moves; the opacity fades stay at fast_ms so a window
        # is not still materialising after its slide has finished.
        for leaf in ('windows', 'windowsIn', 'windowsMove', 'layers', 'layersIn'):
            with self.subTest(leaf=leaf):
                self.assertEqual(self.motion['normal_ms'],
                                 self.doc['events'][leaf]['duration_ms'])
        for leaf in ('workspaces', 'specialWorkspace'):
            with self.subTest(leaf=leaf):
                self.assertEqual(self.motion['slow_ms'],
                                 self.doc['events'][leaf]['duration_ms'])

    def test_the_intensity_that_ships_by_default_renders_this_preset(self):
        default_intensity = tokens()['default_intensity']
        self.assertEqual('smooth', anim.preset_for_intensity(tokens(), default_intensity))


class SnappyIsNeverSlowerThanSmooth(unittest.TestCase):
    def setUp(self):
        self.smooth = preset('smooth')['events']
        self.snappy = preset('snappy')['events']

    def test_every_event_is_as_fast_or_faster(self):
        for leaf, event in self.snappy.items():
            with self.subTest(leaf=leaf):
                self.assertLessEqual(event['duration_ms'], self.smooth[leaf]['duration_ms'])

    def test_every_duration_is_inside_the_band_the_brief_gives_it(self):
        for leaf, event in enabled_events(preset('snappy')).items():
            if leaf == 'borderangle':
                continue  # a loop period, not a transition
            with self.subTest(leaf=leaf):
                self.assertGreaterEqual(event['duration_ms'], 120)
                self.assertLessEqual(event['duration_ms'], 220)

    def test_at_least_one_event_is_actually_faster(self):
        self.assertTrue(any(event['duration_ms'] < self.smooth[leaf]['duration_ms']
                            for leaf, event in self.snappy.items()))

    def test_its_curves_are_the_same_shapes_as_smooths(self):
        # The difference is length, not feel: same beziers, a stiffer spring.
        for name, curve in preset('smooth')['curves'].items():
            if curve['type'] != 'bezier':
                continue
            with self.subTest(curve=name):
                self.assertEqual(curve['points'], preset('snappy')['curves'][name]['points'])


class BouncyOvershootsOnlyWhereAnOvershootIsAPosition(unittest.TestCase):
    def setUp(self):
        self.doc = preset('bouncy')

    def peaks(self) -> Dict[str, float]:
        return {name: max(y for _x, y in curve['points'])
                for name, curve in self.doc['curves'].items() if curve['type'] == 'bezier'}

    def test_it_declares_a_curve_that_overshoots(self):
        self.assertTrue(any(peak > 1.0 for peak in self.peaks().values()), self.peaks())

    def test_the_window_open_and_the_workspace_switch_use_those_curves(self):
        # The two events the brief names: a window arriving and a workspace
        # switching. Either an overshooting bezier or the spring counts, since both
        # arrive past the target and settle back.
        overshooting = {name for name, peak in self.peaks().items() if peak > 1.0}
        springy = {name for name, curve in self.doc['curves'].items()
                   if curve['type'] == 'spring'}
        for leaf in ('windows', 'windowsIn', 'workspaces', 'specialWorkspace'):
            with self.subTest(leaf=leaf):
                self.assertIn(self.doc['events'][leaf]['curve'], overshooting | springy)

    def test_the_events_the_brief_does_not_name_do_not_bounce(self):
        overshooting = {name for name, peak in self.peaks().items() if peak > 1.0}
        springy = {name for name, curve in self.doc['curves'].items()
                   if curve['type'] == 'spring'}
        for leaf in ('windowsOut', 'windowsMove', 'layers', 'layersIn', 'layersOut'):
            with self.subTest(leaf=leaf):
                self.assertNotIn(self.doc['events'][leaf]['curve'], overshooting | springy)

    def test_no_fade_or_border_event_overshoots(self):
        # An overshooting bezier drives the value past its endpoint: for a slide
        # that is a position past the target, for a fade an alpha above 1 and for
        # the border a colour channel out of range. Whether Hyprland clamps those
        # is TODO(verify) MOT-04, so nothing here depends on the answer.
        overshooting = {name for name, peak in self.peaks().items() if peak > 1.0}
        for leaf, event in enabled_events(self.doc).items():
            if leaf.startswith('fade') or leaf.startswith('border'):
                with self.subTest(leaf=leaf):
                    self.assertNotIn(event['curve'], overshooting)

    def test_no_layer_event_overshoots(self):
        overshooting = {name for name, peak in self.peaks().items() if peak > 1.0}
        for leaf, event in enabled_events(self.doc).items():
            if leaf.startswith('layers'):
                with self.subTest(leaf=leaf):
                    self.assertNotIn(event['curve'], overshooting)

    def test_its_spring_is_less_damped_than_smooths(self):
        # Less damping relative to stiffness is what makes the bounce visible.
        def ratio(doc):
            spring = doc['curves']['spring']
            return spring['damping'] / (2 * (spring['stiffness'] * spring['mass']) ** 0.5)

        self.assertLess(ratio(self.doc), ratio(preset('smooth')))

    def test_it_gives_the_bounce_room_rather_than_compressing_it(self):
        self.assertGreater(self.doc['events']['windows']['duration_ms'],
                           preset('smooth')['events']['windows']['duration_ms'])


class MinimalMovesNothing(unittest.TestCase):
    def setUp(self):
        self.doc = preset('minimal')

    def test_no_transform_event_is_enabled(self):
        for leaf in TRANSFORM_EVENTS:
            with self.subTest(leaf=leaf):
                self.assertFalse(self.doc['events'][leaf]['enabled'])

    def test_the_fades_are_kept_and_short(self):
        cap = tokens()['motion']['animation']['reduce_motion']['max_duration_ms']
        enabled = enabled_events(self.doc)
        self.assertTrue(enabled, 'minimal must still fade something')
        for leaf, event in enabled.items():
            with self.subTest(leaf=leaf):
                self.assertLessEqual(event['duration_ms'], 120)
                self.assertTrue(leaf.startswith('fade') or leaf.startswith('layers')
                                or leaf == 'border', leaf)

    def test_reduce_motion_brings_every_duration_to_the_cap(self):
        cap = anim.reduce_motion_cap_ms(tokens())
        plan, _warnings = anim.plan_events(self.doc, surface(), multiplier=1.0, cap_ms=cap,
                                           reduce_motion=True)
        for entry in plan:
            if entry['enabled']:
                with self.subTest(leaf=entry['leaf']):
                    self.assertLessEqual(entry['duration_ms'], cap)

    def test_the_focus_border_survives_reduce_motion(self):
        # Removing it would trade a motion problem for an orientation problem.
        self.assertTrue(self.doc['events']['border']['enabled'])

    def test_it_declares_no_overshoot_and_no_spring(self):
        self.assertEqual([], [c for c in self.doc['curves'].values() if c['type'] == 'spring'])
        for component in bezier_components(self.doc):
            self.assertGreaterEqual(component, 0.0)
            self.assertLessEqual(component, 1.0)


class OffTurnsTheMasterSwitchOff(unittest.TestCase):
    def setUp(self):
        self.doc = preset('off')

    def test_the_master_switch_is_off(self):
        self.assertFalse(self.doc['master'])

    def test_every_event_is_declared_off(self):
        self.assertEqual(0, len(enabled_events(self.doc)))
        self.assertEqual(BRIEF_EVENTS, set(self.doc['events']))

    def test_it_is_the_only_preset_with_the_master_switch_off(self):
        for name, doc in all_presets().items():
            with self.subTest(preset=name):
                self.assertEqual(name == 'off', not doc['master'])

    def test_the_performance_intensity_is_paired_with_it(self):
        self.assertEqual('off', tokens()['intensities']['performance']['motion']['preset'])


class TheTwoSwitchesThatSayTheSameThingAgree(unittest.TestCase):
    def test_enabled_false_only_ever_pairs_with_off(self):
        for name, intensity in tokens()['intensities'].items():
            motion = intensity['motion']
            with self.subTest(intensity=name):
                self.assertEqual(motion['preset'] == 'off', not motion['enabled'])

    def test_the_generator_refuses_a_pair_that_disagrees(self):
        for name, intensity in tokens()['intensities'].items():
            broken = json.loads(json.dumps(tokens()))
            broken['intensities'][name]['motion']['enabled'] = not intensity['motion']['enabled']
            with self.subTest(intensity=name):
                with self.assertRaises(anim.AnimationError):
                    anim.preset_for_intensity(broken, name)

    def test_every_intensity_resolves_to_a_preset_that_exists(self):
        for name in tokens()['intensities']:
            with self.subTest(intensity=name):
                self.assertIn(anim.preset_for_intensity(tokens(), name), PRESET_NAMES)

    def test_the_settings_multiplier_bounds_are_the_token_bounds(self):
        low, high, default = anim.multiplier_bounds(tokens())
        schema = read_json(SETTINGS_SCHEMA)['properties']['animation']['properties']['speed']
        self.assertEqual(low, schema['minimum'])
        self.assertEqual(high, schema['maximum'])
        self.assertEqual(default, read_json(SETTINGS_DEFAULT)['animation']['speed'])

    def test_the_reduce_motion_cap_is_under_a_hundred_milliseconds(self):
        cap = anim.reduce_motion_cap_ms(tokens())
        self.assertLess(cap, 100)
        self.assertEqual('minimal', anim.reduce_motion_preset(tokens()))
        schema = read_json(TOKENS_SCHEMA)['properties']['motion']['properties']['animation']
        self.assertEqual(100, schema['properties']['reduce_motion']
                         ['properties']['max_duration_ms']['exclusiveMaximum'])


class EveryPresetRenders(unittest.TestCase):
    """The data is load-bearing: each preset has to survive the real renderer."""

    def test_every_preset_renders_and_passes_the_structural_check(self):
        for name in PRESET_NAMES:
            with self.subTest(preset=name):
                text = anim.build_preset(tokens(), surface(), preset(name))
                self.assertEqual([], anim.sanity_check_lua(text))
                self.assertIn('hl.config', text)

    def test_a_preset_renders_at_both_ends_of_the_multiplier(self):
        low, high, _default = anim.multiplier_bounds(tokens())
        for name in PRESET_NAMES:
            for factor in (low, high):
                with self.subTest(preset=name, factor=factor):
                    self.assertIn('hl.config', anim.build_preset(tokens(), surface(),
                                                                 preset(name),
                                                                 multiplier=factor))

    def test_every_event_can_be_toggled_off_in_every_preset_that_animates_it(self):
        for name in PRESET_NAMES:
            doc = preset(name)
            if not doc['master']:
                continue
            for leaf in enabled_events(doc):
                with self.subTest(preset=name, leaf=leaf):
                    plan, _w = anim.plan_events(doc, surface(), overrides={leaf: False})
                    entry = next(e for e in plan if e['leaf'] == leaf)
                    self.assertFalse(entry['enabled'])
                    self.assertEqual({'leaf', 'enabled'}, set(entry))


if __name__ == '__main__':
    unittest.main()
