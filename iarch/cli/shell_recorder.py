#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Explicitly record the display without audio in a private state directory."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.cli.shell_screenshot import capture_directory  # noqa: E402


def record(*, state_dir=None, popen=subprocess.Popen, stopping=lambda: False, notify=lambda _: None, clock=time.monotonic):
    directory = capture_directory(state_dir)
    fd, name = tempfile.mkstemp(prefix='.record-', suffix='.mkv', dir=directory)
    os.close(fd)
    temporary = Path(name)
    process = None
    stopped_at = None
    try:
        # -y only overwrites the private temporary file that mkstemp created;
        # no user-supplied path or shell text reaches the recorder.
        process = popen(['wf-recorder', '-y', '-f', str(temporary)], stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notify({'status': 'started'})
        while True:
            if stopping() and stopped_at is None:
                process.send_signal(signal.SIGINT)
                stopped_at = clock()
            try:
                status = process.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if stopped_at is not None and clock() - stopped_at > 10:
                    process.kill()
                    process.wait()
                    raise ValueError('recorder did not stop cleanly')
        if status != 0 or stopped_at is None or temporary.stat().st_size == 0:
            raise ValueError('recorder failed or ended unexpectedly')
        with temporary.open('rb') as file:
            os.fsync(file.fileno())
        final = directory / (temporary.name.removeprefix('.record-').removesuffix('.mkv') + '.mkv')
        os.link(temporary, final, follow_symlinks=False)
        return {'status': 'finished', 'path': str(final)}
    except OSError as exc:
        raise ValueError('recorder unavailable') from exc
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        temporary.unlink(missing_ok=True)


def main():
    stop = [False]
    def request_stop(signum, frame):
        stop[0] = True
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        result = record(stopping=lambda: stop[0], notify=lambda event: print(json.dumps(event), flush=True))
        print(json.dumps(result), flush=True)
        return 0
    except (ValueError, OSError) as exc:
        print(f'recorder: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
