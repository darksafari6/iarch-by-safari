# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render a lightweight palette preview; it is not a screenshot-parity claim."""
import os
import tempfile
from pathlib import Path

from iarch.cli.theme_pack_validate import validate_pack
from iarch.lib import configstore


def render_preview(pack_path, *, env=None):
    from PIL import Image, ImageDraw
    docs = validate_pack(pack_path)
    theme = docs['theme']
    if theme['id'] == 'dynamic-reference':
        raise ValueError('the reference pack is not offered for preview')
    colors = docs['palette']['colors']
    image = Image.new('RGB', (800, 450), colors['background'])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 20, 776, 62), radius=12, fill=colors['surface'], outline=colors['outline'], width=2)
    draw.ellipse((43, 31, 63, 51), fill=colors['accent'])
    draw.text((78, 34), theme['name'], fill=colors['text'])
    draw.rounded_rectangle((24, 86, 510, 422), radius=16, fill=colors['surface'], outline=colors['outline'], width=2)
    draw.text((46, 106), 'Palette preview', fill=colors['text'])
    draw.text((46, 132), 'Illustrative only; not a live shell screenshot.', fill=colors['secondary'])
    roles = ('accent', 'secondary', 'error', 'outline', 'text', 'background')
    for i, role in enumerate(roles):
        x = 47 + (i % 3) * 145
        y = 180 + (i // 3) * 88
        draw.rounded_rectangle((x, y, x + 110, y + 48), radius=8, fill=colors[role], outline=colors['outline'])
        draw.text((x, y + 54), role, fill=colors['text'])
    draw.rounded_rectangle((532, 86, 776, 422), radius=16, fill=colors['surface'], outline=colors['outline'], width=2)
    draw.text((553, 106), 'Surfaces', fill=colors['text'])
    y = 144
    for name, surface in docs['layout']['surfaces'].items():
        if surface['enabled']:
            draw.text((553, y), name + ': ' + surface['variant'], fill=colors['text'])
            y += 28
    env = os.environ if env is None else env
    cache = env.get('XDG_CACHE_HOME')
    base = Path(cache) if cache and Path(cache).is_absolute() else configstore.home_dir(env) / '.cache'
    directory = base / 'iarch' / 'theme-previews'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / (theme['id'] + '.png')
    fd, name = tempfile.mkstemp(prefix='.preview-', suffix='.png', dir=directory)
    os.close(fd)
    try:
        image.save(name, format='PNG')
        os.replace(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
    return output
