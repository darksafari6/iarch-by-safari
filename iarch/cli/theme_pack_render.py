# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render dynamic pack data into existing session projection formats.

All output is prepared in memory. No subprocess runs and no file is written.
"""
import copy
import json
import re
from pathlib import Path

from iarch.cli import gen_animations_lua, gen_fontconfig, session_theme
from iarch.lib import configstore

ROOT = Path(__file__).resolve().parents[2]


def _gtk_settings(existing, entries):
    """Update only verified GtkSettings keys while preserving unrelated lines."""
    lines = existing.splitlines()
    headers = [i for i, line in enumerate(lines) if line.strip() == '[Settings]']
    if len(headers) > 1:
        raise ValueError('duplicate GTK Settings sections')
    if not headers:
        if lines and lines[-1].strip():
            lines.append('')
        lines.append('[Settings]')
        headers = [len(lines) - 1]
    start = headers[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].strip().startswith('[')), len(lines))
    for key, value in entries.items():
        matches = [i for i in range(start, end) if re.match(r'^\s*' + re.escape(key) + r'\s*=', lines[i])]
        if len(matches) > 1:
            raise ValueError('duplicate GTK setting: ' + key)
        if matches:
            lines[matches[0]] = key + '=' + str(value)
        else:
            lines.insert(end, key + '=' + str(value))
            end += 1
    return '\n'.join(lines) + '\n'


def _safe_name(name):
    if not re.fullmatch(r'[A-Za-z0-9_.+ -]{1,100}', name):
        raise ValueError('unsafe application theme or font name')
    return name


def actions(docs, env=None):
    """Build the shared compositor, terminal, GTK, Qt, prompt and font outputs."""
    theme, colors, hypr, apps = (docs[k] for k in ('theme', 'palette', 'hypr', 'apps'))
    colors = colors['colors']
    sizes = docs['layout']['sizes']
    radius = theme['shape']['radius']
    # Existing renderer handles syntax, escaping and validated animation leaves.
    # No Classic colours are inherited: all projected colours use palette roles.
    pack = json.loads((ROOT / 'data/themes/forest-night.json').read_text(encoding='utf-8'))
    pack['meta']['id'], pack['meta']['name'] = theme['id'], theme['name']
    p = pack['noctalia']['palette']
    p.update({'background': colors['background'], 'surface': colors['surface'],
              'primary': colors['accent'], 'on_primary': colors['on-accent'],
              'error': colors['error'], 'outline': colors['outline'],
              'bar': colors['surface'], 'dock': colors['surface'],
              'notification': colors['surface'], 'text': colors['text'],
              'secondary': colors['secondary'], 'on_secondary': colors['on-accent'],
              'on_error': colors['background']})
    t = pack['terminal']
    t.update({'foreground': colors[apps['kitty']['foreground']],
              'background': colors[apps['kitty']['background']],
              'cursor': colors[apps['kitty']['cursor']],
              'selection_foreground': colors['text'], 'selection_background': colors['surface']})
    terminal_roles = ('background', 'error', 'accent', 'secondary', 'accent', 'secondary', 'accent', 'text',
                      'outline', 'error', 'accent', 'secondary', 'accent', 'secondary', 'accent', 'text')
    t.update({f'color{i}': colors[role] for i, role in enumerate(terminal_roles)})
    pack['gtk'].update({'accent': colors[apps['gtk']['accent']], 'window_bg': colors['background'],
                        'headerbar': colors['surface'], 'destructive': colors['error']})
    h = pack['hypr']
    h.update({'gaps_in': sizes[hypr['gaps_in']], 'gaps_out': sizes[hypr['gaps_out']],
              'border_size': sizes[hypr['border_width']], 'rounding': radius[hypr['rounding']],
              'active_border': colors[hypr['active_border']], 'inactive_border': colors[hypr['inactive_border']],
              'shadow_range': sizes[hypr['shadow']['range']] if hypr['shadow']['enabled'] else 0,
              'shadow_color': colors[hypr['shadow']['color']]})
    h['blur'].update({'enabled': hypr['blur']['enabled'], 'size': sizes[hypr['blur']['size']],
                      'passes': hypr['blur']['passes']})
    # Refuse values outside Hyprland's own documented integer ranges.
    for field, maximum in (('border_size', 20), ('rounding', 100), ('shadow_range', 100)):
        if h[field] > maximum:
            raise ValueError(f'Hyprland {field} exceeds {maximum}')
    if h['blur']['size'] > 100:
        raise ValueError('Hyprland blur size exceeds 100')
    pack['starship']['palette'] = 'iarch-dynamic'
    root = configstore.home_dir(env) / '.config'
    for value in (apps['gtk']['theme'], apps['qt']['theme'], apps['cursor']['theme'], apps['icons']['theme'], *theme['fonts'].values()):
        _safe_name(value)
    body = session_theme.render_hypr_theme(pack)
    # Replace the Classic motion projection with the pack's validated preset.
    # render_hypr_theme emits its animations after the first config block.
    marker = '\n})\n'
    head = body.split(marker, 1)[0] + marker
    cursor_name = apps['cursor']['theme']
    cursor_size = sizes[apps['cursor']['size']]
    for key, value in (('XCURSOR_THEME', cursor_name), ('HYPRCURSOR_THEME', cursor_name),
                       ('QT_CURSOR_THEME', cursor_name), ('XCURSOR_SIZE', str(cursor_size)),
                       ('HYPRCURSOR_SIZE', str(cursor_size)), ('QT_CURSOR_SIZE', str(cursor_size))):
        head += 'hl.env(' + json.dumps(key) + ', ' + json.dumps(value) + ')\n'
    preset = gen_animations_lua.load_preset(hypr['animations']['preset'])
    preset = copy.deepcopy(preset)
    preset['master'] = hypr['animations']['enabled']
    for rule in hypr['window_rules']:
        # Class is a data string, never executable Lua. Effects are schema-enumerated.
        if any(ord(c) < 32 for c in rule['class']):
            raise ValueError('window class contains a control character')
        head += ('hl.window_rule({ match = { class = ' + json.dumps(rule['class'], ensure_ascii=False) +
                 ' }, ' + rule['effect'] + ' = ' + str(rule['enabled']).lower() + ' })\n')
    motion, warnings = gen_animations_lua.render_preset(gen_animations_lua.load_tokens(),
        gen_animations_lua.load_surface(), preset, multiplier=1.0, reduce_motion=False)
    if warnings:
        raise ValueError('animation rendering warnings: ' + '; '.join(warnings))
    kitty_body = session_theme.render_kitty_theme(pack)
    kitty_body += 'font_family ' + theme['fonts'][apps['kitty']['font']] + '\n'
    result = [('generated', root / 'hypr/generated/theme.lua', head + motion),
              ('generated', root / 'kitty/theme.conf', kitty_body)]
    kitty = root / 'kitty/kitty.conf'
    include = session_theme._ensure_kitty_include(kitty, env or {})
    result.append(('preserving', kitty, include if include is not None else 'include theme.conf\n'))
    starship = root / 'starship.toml'
    starship_text = starship.read_text(encoding='utf-8') if starship.is_file() else ''
    result.append(('preserving', starship, session_theme.render_starship_config(starship_text, pack)))
    for version in ('3.0', '4.0'):
        settings = root / f'gtk-{version}/settings.ini'
        existing = settings.read_text(encoding='utf-8') if settings.is_file() else ''
        entries = {'gtk-theme-name': apps['gtk']['theme'], 'gtk-icon-theme-name': apps['icons']['theme'],
                   'gtk-cursor-theme-name': apps['cursor']['theme'],
                   'gtk-cursor-theme-size': sizes[apps['cursor']['size']],
                   'gtk-font-name': theme['fonts'][apps['fonts']['ui']] + ' 11'}
        result.append(('preserving', settings, _gtk_settings(existing, entries)))
        css = root / f'gtk-{version}/gtk.css'
        css_text = css.read_text(encoding='utf-8') if css.is_file() else ''
        result.append(('preserving', css, session_theme.render_gtk_css(css_text, pack)))
    kvantum = root / 'Kvantum/iarch/iarch.kvconfig'
    kvantum_base = kvantum if kvantum.is_file() else ROOT / '.config/Kvantum/iarch/iarch.kvconfig'
    result.append(('preserving', kvantum, session_theme.render_kvantum_config(kvantum_base.read_text(encoding='utf-8'), pack)))
    fish = root / 'fish/conf.d/iarch-theme.fish'
    result.append(('generated', fish, 'set -g fish_color_command ' + colors[apps['fish']['command']][1:7] +
                   '\nset -g fish_color_error ' + colors[apps['fish']['error']][1:7] + '\n'))
    tokens = copy.deepcopy(gen_fontconfig.load_tokens())
    tokens['font']['ui'] = theme['fonts'][apps['fonts']['ui']]
    tokens['font']['ui_display'] = theme['fonts'][apps['fonts']['display']]
    tokens['font']['mono'] = theme['fonts'][apps['fonts']['mono']]
    surface = gen_fontconfig.load_surface()
    fontdoc = gen_fontconfig.build_document(tokens, surface)
    errors = gen_fontconfig.validate(fontdoc, tokens, surface)
    if errors:
        raise ValueError('fontconfig: ' + '; '.join(errors))
    result.append(('generated', root / 'fontconfig/fonts.conf', fontdoc))
    return result
