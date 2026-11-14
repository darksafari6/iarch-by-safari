#!/usr/bin/env bash
# Start the iArch by Safari settings window.
#
# Usage: scripts/iarch-settings.sh [--describe]
#
# This is the launcher the desktop entry's Exec= names, and it is deliberately a thin
# wrapper: everything the window does is in iarch/settings-app/iarch_settings, and the only
# thing here is putting that package on PYTHONPATH and handing the exit status through.
# `python3 -m iarch_settings` and this script are therefore one code path, which is what
# makes the installed launcher testable -- tests/test_settings_packaging.py runs the module
# in a subprocess and nothing about this file is on a path no test reaches.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
package="$root/iarch/settings-app"

if [ ! -d "$package/iarch_settings" ]; then
    printf 'Error: %s is not the settings package, so this launcher is not in the repository it came from.\n' \
        "$package/iarch_settings" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the settings window cannot start.\n' >&2
    exit 127
fi

# The package is not installed, it is in the repository, so PYTHONPATH is how it is found.
# An existing PYTHONPATH is kept: dropping it would break a session that put something
# else there and had a reason to.
IARCH_PYTHONPATH="$package${PYTHONPATH:+:$PYTHONPATH}"

# --describe answers the one question a person whose window will not open actually has:
# which typelib is missing, and which package provides it on the distribution they are on.
# It exits non-zero when the toolkit is unusable, so it is a check as well as a report.
if [ "${1:-}" = "--describe" ]; then
    PYTHONPATH="$IARCH_PYTHONPATH" exec python3 -c '
from iarch_settings import gtkenv, paths, version
print(version.read_version(paths.repo_root()))
print(gtkenv.describe())
raise SystemExit(0 if gtkenv.available() else 1)
'
fi

if [ "$#" -gt 0 ]; then
    printf 'Usage: %s [--describe]\n' "$0" >&2
    exit 2
fi

PYTHONPATH="$IARCH_PYTHONPATH" exec python3 -m iarch_settings
