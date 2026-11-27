# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Validated, side-effect-free state for the dynamic shell's future runtime.

The model accepts only packs validated by the shared pack validator. It does not
start a shell, expose IPC, watch files, or claim to be a live QML runtime.
"""
import copy
import re
from pathlib import Path

from iarch.cli import theme_pack_validate, theme_packs, theme_records


class RuntimeError(ValueError):
    """An invalid state transition; the previous runtime state is untouched."""


class ThemeRuntime:
    """Hold a last-known-good token snapshot and a visible-surface registry."""

    def __init__(self, env=None, pack_lookup=None, *, reference_preview=False):
        self.env = env
        self.reference_preview = reference_preview
        self.pack_lookup = pack_lookup or (lambda name: theme_packs.find_dynamic(name, env))
        self._theme = None
        self._surfaces = {}
        self.error = None

    @property
    def available(self):
        return self._theme is not None

    @property
    def snapshot(self):
        # A consumer cannot mutate the accepted state behind validation's back.
        return copy.deepcopy(self._theme)

    @property
    def surfaces(self):
        return copy.deepcopy(self._surfaces)

    def load(self, pack_id):
        """Validate the entire pack and override set before replacing the state."""
        if not isinstance(pack_id, str) or not re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', pack_id):
            self.error = 'invalid pack id'
            raise RuntimeError(self.error)
        try:
            pack_path = Path(self.pack_lookup(pack_id))
            candidate = theme_pack_validate.validate_pack(pack_path)
            reference_ok = (self.reference_preview and pack_id == 'dynamic-reference' and
                            pack_path.resolve() == (theme_packs.ROOT / 'data/themes/dynamic-reference').resolve())
            if candidate['theme']['id'] != pack_id or (pack_id == 'dynamic-reference' and not reference_ok):
                raise RuntimeError('pack id does not match or is reserved')
            overrides = theme_records.read_overrides(self.env)
            candidate = copy.deepcopy(candidate)
            if overrides['accent'] is not None:
                candidate['palette']['colors']['accent'] = overrides['accent']
            layouts = candidate['layout']['surfaces']
            for surface, variant in overrides['variants'].items():
                if surface not in layouts:
                    raise RuntimeError(f'unknown surface override: {surface}')
                if f'{surface}:{variant}' not in candidate['theme']['variants']:
                    raise RuntimeError(f'undeclared surface variant: {surface}:{variant}')
                layouts[surface]['variant'] = variant
            # Never let a pack choose a path for a sound or wallpaper outside its
            # validated directory; user wallpaper overrides remain user-owned.
            candidate['user_overrides'] = copy.deepcopy(overrides)
            new_surfaces = {name: {'available': item['enabled'], 'visible': False,
                                   'variant': item['variant'], 'position': item['position']}
                            for name, item in layouts.items()}
        except (ValueError, OSError, ImportError) as exc:
            self.error = str(exc)
            raise RuntimeError(self.error) from exc
        self._theme = candidate
        self._surfaces = new_surfaces
        self.error = None
        return self.snapshot

    def projection(self, quality=None, reduce_motion=False):
        """Build the narrow QML token projection from the last accepted pack."""
        if self._theme is None:
            raise RuntimeError('no validated theme is loaded')
        if quality is None:
            quality = self._theme['user_overrides'].get('quality') or 'balanced'
        if quality not in ('ultra', 'high', 'balanced', 'low') or not isinstance(reduce_motion, bool):
            raise RuntimeError('invalid quality settings')
        theme = self._theme['theme']
        palette = self._theme['palette']['colors']
        def qt_color(value):
            # The pack's eight-digit values are RRGGBBAA; Qt uses AARRGGBB.
            return '#' + value[7:9] + value[1:7] if len(value) == 9 else value
        color_keys = ('background', 'surface', 'text', 'accent', 'secondary', 'error', 'outline')
        colors = {k: qt_color(palette[k]) for k in color_keys}
        colors['onAccent'] = qt_color(palette['on-accent'])
        radius = theme['shape']['radius']
        sizes = self._theme['layout']['sizes']
        durations = self._theme['motion']['durations']
        return {'id': theme['id'], 'palette': colors,
                'radius': {'small': radius['sm'], 'medium': radius['md'], 'large': radius['lg']},
                'spacing': {key: sizes[key] for key in ('small', 'medium', 'large')},
                'fonts': dict(theme['fonts']), 'motion': dict(durations),
                'shape': copy.deepcopy(theme['shape']),
                'easing': self._theme['motion']['easing'],
                'transition': self._theme['motion'].get('transition', 'fade'),
                'surfaceMotion': copy.deepcopy(self._theme['motion']['surfaces']),
                'variants': {name: item['variant'] for name, item in self._theme['layout']['surfaces'].items()},
                'sounds': {name: {'enabled': event['enabled'] and self._theme['user_overrides']['sounds_enabled'] is not False,
                                  'volume': event['volume'] if self._theme['user_overrides']['volume'] is None else self._theme['user_overrides']['volume']}
                           for name, event in self._theme['sounds']['events'].items()},
                'surfaceStyle': theme['surfaceStyle'], 'quality': quality,
                'reduceMotion': reduce_motion}

    def set_surface(self, name, action):
        if not isinstance(name, str) or name not in self._surfaces:
            raise RuntimeError('unknown surface')
        surface = self._surfaces[name]
        if not surface['available']:
            raise RuntimeError('surface is disabled by this theme')
        if action not in ('open', 'close', 'toggle'):
            raise RuntimeError('unknown surface action')
        visible = not surface['visible'] if action == 'toggle' else action == 'open'
        surface['visible'] = visible
        return visible
