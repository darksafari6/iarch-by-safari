#!/usr/bin/env python3
"""Apply the v4.4.0 glass preset to the installer's disposable staging tree.

Not a live configuration editor: the installer supplies a fresh stage and backs
up any existing session before deploying it.
"""
import json
import math
from pathlib import Path
import struct
import sys
import wave


RULE = ('\n# minimaLinux glass: Hyprland 0.54+ layer rules for Noctalia v4.4.0.\n'
        '# Ignore transparent/dimmer pixels so the full-screen layer is not blurred.\n'
        'layerrule = match:namespace ^noctalia-(background|notifications)-.*, blur on, ignore_alpha 0.5\n')


def write_twinkle(path):
    """Original synthesized two-note chime, 80 ms, mono 16-bit PCM."""
    rate, count = 24000, 1920
    samples = []
    for i in range(count):
        t = i / rate
        # A soft, quick attack and decay avoid clicks; two overtones make a sparkle.
        envelope = min(1, t / 0.006) * max(0, 1 - t / 0.08) ** 1.6
        value = 0.36 * envelope * (math.sin(2 * math.pi * 880 * t) +
                                   0.45 * math.sin(2 * math.pi * 1320 * t))
        samples.append(struct.pack('<h', int(max(-1, min(1, value)) * 32767)))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b''.join(samples))


def apply(stage):
    settings_path = stage / 'noctalia/settings.json'
    settings = json.loads(settings_path.read_text())
    if settings.get('settingsVersion') != 49:
        raise ValueError('Unsupported Noctalia settings version; expected v4 settingsVersion 49')
    bar = settings['bar']
    bar.update(floating=True, marginVertical=8, marginHorizontal=12,
               useSeparateOpacity=True, backgroundOpacity=0.82,
               showCapsule=True, capsuleOpacity=0.78)
    right = bar['widgets']['right']
    existing = {w.get('id') for w in right}
    # Keep every existing widget, its settings, and its relative order.
    for widget in ('Network', 'Bluetooth'):
        if widget not in existing:
            right.insert(next((i for i, w in enumerate(right) if w.get('id') == 'ControlCenter'), len(right)), {'id': widget})
    settings.setdefault('ui', {})['panelBackgroundOpacity'] = 0.86
    notifications = settings.setdefault('notifications', {})
    notifications.update(location='top_right', backgroundOpacity=0.88)
    sounds = notifications.setdefault('sounds', {})
    sounds.update(enabled=False, volume=0.35, separateSounds=False,
                  normalSoundFile='minimalinux-twinkle.wav')
    # v4's defaults, with brightness enabled. Existing custom cards are retained.
    cc = settings.setdefault('controlCenter', {})
    cards = cc.setdefault('cards', [
        {'enabled': True, 'id': 'profile-card'},
        {'enabled': True, 'id': 'shortcuts-card'},
        {'enabled': True, 'id': 'audio-card'},
        {'enabled': False, 'id': 'brightness-card'},
        {'enabled': True, 'id': 'weather-card'},
        {'enabled': True, 'id': 'media-sysmon-card'},
    ])
    brightness = next((card for card in cards if card.get('id') == 'brightness-card'), None)
    if brightness is None:
        cards.append({'enabled': True, 'id': 'brightness-card'})
    else:
        brightness['enabled'] = True
    sound_path = stage / 'quickshell/noctalia-shell/Assets/Sounds/minimalinux-twinkle.wav'
    sound_path.parent.mkdir(parents=True, exist_ok=True)
    write_twinkle(sound_path)
    rules = stage / 'hypr/windowrules.conf'
    text = rules.read_text()
    if RULE not in text:
        rules.write_text(text + RULE)
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: glass_preset.py STAGING_DIRECTORY')
    apply(Path(sys.argv[1]))
