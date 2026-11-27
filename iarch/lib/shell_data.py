# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Pure parsers for shell service adapters; no polling or subprocess execution."""
import math


class DataError(ValueError):
    """A service returned malformed data."""


def cpu_counters(text):
    """Return total and idle counters from the aggregate Linux /proc/stat row."""
    line = next((line for line in text.splitlines() if line.startswith('cpu ')), None)
    if line is None:
        raise DataError('missing aggregate CPU counters')
    try:
        fields = [int(x) for x in line.split()[1:]]
    except ValueError as exc:
        raise DataError('invalid CPU counters') from exc
    if len(fields) < 4 or any(x < 0 for x in fields):
        raise DataError('invalid CPU counter values')
    # guest and guest_nice are already included in user and nice.
    return sum(fields[:8]), fields[3] + (fields[4] if len(fields) > 4 else 0)


def cpu_percent(before, after):
    """Return busy percent between two samples; None if counters did not advance."""
    total = after[0] - before[0]
    idle = after[1] - before[1]
    if total <= 0 or idle < 0 or idle > total:
        return None
    return 100.0 * (total - idle) / total


def memory_usage(text):
    """Return used and total bytes, using MemAvailable from /proc/meminfo."""
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition(':')
        if sep and key in ('MemTotal', 'MemAvailable'):
            parts = value.split()
            if len(parts) != 2 or parts[1] != 'kB' or not parts[0].isdigit():
                raise DataError(f'invalid memory value: {key}')
            if key in fields:
                raise DataError(f'duplicate memory value: {key}')
            fields[key] = int(parts[0]) * 1024
    if set(fields) != {'MemTotal', 'MemAvailable'} or not 0 <= fields['MemAvailable'] <= fields['MemTotal']:
        raise DataError('missing or inconsistent memory values')
    return {'total': fields['MemTotal'], 'used': fields['MemTotal'] - fields['MemAvailable']}


def nmcli_fields(line):
    """Split nmcli terse output while honoring its escaped colon and backslash."""
    fields, chars, escape = [], [], False
    for char in line:
        if escape:
            chars.append(char)
            escape = False
        elif char == '\\':
            escape = True
        elif char == ':':
            fields.append(''.join(chars))
            chars = []
        else:
            chars.append(char)
    if escape:
        raise DataError('truncated nmcli escape')
    fields.append(''.join(chars))
    return fields


def wifi_networks(text):
    """Parse nmcli's terse IN-USE,SSID,SIGNAL fields without splitting SSIDs."""
    result = []
    for line in text.splitlines():
        fields = nmcli_fields(line)
        if len(fields) != 3 or fields[0] not in ('', '*'):
            raise DataError('invalid nmcli Wi-Fi record')
        try:
            signal = int(fields[2])
        except ValueError as exc:
            raise DataError('invalid signal') from exc
        if not 0 <= signal <= 100:
            raise DataError('signal outside 0–100')
        result.append({'active': fields[0] == '*', 'ssid': fields[1], 'signal': signal})
    return result


def spectrum(line, *, maximum=65535, bars=128):
    """Parse one semicolon-separated integer spectrum frame into 0..1 floats."""
    if maximum <= 0 or not 1 <= bars <= 1024:
        raise DataError('invalid spectrum limits')
    values = line.strip().rstrip(';').split(';')
    if not values or len(values) > bars:
        raise DataError('invalid spectrum size')
    try:
        samples = [int(value) for value in values]
    except ValueError as exc:
        raise DataError('invalid spectrum sample') from exc
    if any(n < 0 or n > maximum for n in samples):
        raise DataError('spectrum sample out of range')
    return [n / maximum for n in samples]


def media_metadata(data):
    """Normalize common MPRIS metadata without fetching art or executing URLs."""
    if not isinstance(data, dict):
        raise DataError('metadata must be an object')
    artist = data.get('xesam:artist', [])
    if isinstance(artist, str):
        artist = [artist]
    if not isinstance(artist, list) or not all(isinstance(x, str) for x in artist):
        raise DataError('invalid artist list')
    title = data.get('xesam:title', '')
    art = data.get('mpris:artUrl', '')
    length = data.get('mpris:length', 0)
    if not isinstance(title, str) or not isinstance(art, str):
        raise DataError('invalid media text')
    if isinstance(length, bool) or not isinstance(length, (int, float)) or not math.isfinite(length) or length < 0:
        raise DataError('invalid media length')
    return {'title': title, 'artists': list(artist), 'art_url': art, 'length_us': length}


def network_counters(text):
    """Read receive/transmit bytes by interface from Linux /proc/net/dev."""
    result = {}
    for line in text.splitlines():
        name, separator, counters = line.partition(':')
        if not separator:
            continue
        name = name.strip()
        fields = counters.split()
        if not name or len(name) > 64 or name in result or len(fields) != 16:
            raise DataError('invalid network interface row')
        try:
            numbers = [int(value) for value in fields]
        except ValueError as exc:
            raise DataError('invalid network counters') from exc
        if any(value < 0 for value in numbers):
            raise DataError('negative network counters')
        result[name] = {'rx': numbers[0], 'tx': numbers[8]}
    return result
