#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Report sampled process CPU/RSS for the named dynamic shell; never start it."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.cli import theme_engine  # noqa: E402


def read_process(proc, pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        raise ValueError('invalid process id')
    directory = Path(proc) / str(pid)
    stat = (directory / 'stat').read_text(encoding='ascii')
    end = stat.rfind(')')
    if end < 0:
        raise ValueError('invalid proc stat')
    fields = stat[end + 1:].split()
    if len(fields) < 20:
        raise ValueError('short proc stat')
    ticks = int(fields[11]) + int(fields[12])
    started = int(fields[19])
    resident = None
    for line in (directory / 'status').read_text(encoding='ascii').splitlines():
        if line.startswith('VmRSS:'):
            pieces = line.split()
            if len(pieces) != 3 or pieces[2] != 'kB' or not pieces[1].isdigit():
                raise ValueError('invalid resident memory')
            resident = int(pieces[1]) * 1024
    return {'ticks': ticks, 'start': started, 'resident_bytes': resident}


def report(run=None, proc=Path('/proc'), delay=1.0, clock=time.monotonic, sleep=time.sleep):
    record = theme_engine.engine('dynamic')
    instances, answer = theme_engine.instances(record, run=run)
    data = {'status': 'unavailable', 'processes': [], 'frame_time_ms': None,
            'frame_time_note': 'Frame interval sample unavailable',
            'budget': {'idle_cpu_percent': 3, 'balanced_resident_bytes': 250 * 1024 * 1024},
            'note': 'UNTESTED-LIVE: budget is a target, not a measured result'}
    if instances is None:
        data['note'] = 'Instance list unavailable; no process was sampled'
        return data
    pids = sorted({entry['pid'] for entry in instances if isinstance(entry, dict)
                   and type(entry.get('pid')) is int and entry['pid'] > 1})
    if not pids:
        data['note'] = 'No named dynamic-shell instance is running'
        return data
    first = {}
    for pid in pids:
        try:
            first[pid] = read_process(proc, pid)
        except (OSError, ValueError):
            pass
    probe = theme_engine.ipc_call('iarch.performance', 'start', run=run)
    frame_started = bool(probe and probe.ok and not probe.timed_out and probe.stdout.strip().lower() == 'true')
    start = clock()
    sleep(delay)
    elapsed = clock() - start
    if frame_started:
        sample = theme_engine.ipc_call('iarch.performance', 'finish', run=run)
        if sample and sample.ok and not sample.timed_out:
            try:
                frame = json.loads(sample.stdout)
                count, average, maximum = frame['frames'], frame['average_ms'], frame['max_ms']
                import math
                if (type(count) is int and 0 < count <= 100000 and type(average) in (int, float)
                        and type(maximum) in (int, float) and math.isfinite(average) and math.isfinite(maximum)
                        and 0 < average <= maximum <= 10000):
                    data['frame_time_ms'] = round(average, 2)
                    data['frame_time_note'] = f'{count} Qt animation-frame intervals, maximum {maximum:.2f} ms; not GPU render time'
            except (ValueError, KeyError, TypeError):
                pass
    hz = os.sysconf('SC_CLK_TCK')
    for pid, previous in first.items():
        try:
            current = read_process(proc, pid)
        except (OSError, ValueError):
            continue
        if current['start'] != previous['start'] or current['ticks'] < previous['ticks'] or elapsed <= 0:
            continue
        cpu = 100 * (current['ticks'] - previous['ticks']) / (hz * elapsed)
        data['processes'].append({'pid': pid, 'resident_bytes': current['resident_bytes'],
                                  'cpu_percent': round(cpu, 2)})
    if data['processes']:
        data['status'] = 'sampled'
        data['note'] = ('Frame sampling was active; CPU is not an idle measurement' if frame_started else
                        'One short sample; it does not establish idle or balanced-quality budget compliance')
    else:
        data['note'] = 'Named instances disappeared or could not be read'
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    result = report()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('iArch by Safari — shell performance')
        for process in result['processes']:
            rss = process['resident_bytes']
            memory = f'{rss / (1024 * 1024):.1f} MiB' if rss is not None else 'unavailable'
            print(f"  PID {process['pid']}: CPU {process['cpu_percent']:.2f}%, RSS {memory}")
        print('  frame timing: ' + (f"{result['frame_time_ms']:.2f} ms ({result['frame_time_note']})" if result['frame_time_ms'] is not None else 'unavailable'))
        print('  ' + result['note'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
