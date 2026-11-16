#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# The brightness keys: one step up, one step down, and the level the panel would show.
#
# Usage: scripts/iarch-brightness.sh {up,down,get}
#
# Every spelling below is read out of brightnessctl's own manual at the version Arch
# packages, 0.5.1 (brightnessctl(1), https://man.archlinux.org/man/brightnessctl.1, and
# the same text in the release tarball's brightnessctl.1):
#
#   * `set +10%` is the manual's own example for "adds 10% of the maximum to the current
#     brightness", and `set 50%-` for "subtracts 50% of the maximum". The sign has to be
#     where it is: a leading `-` would be read by getopt as an option, so the down step
#     is the suffix form `5%-` and the up step the prefix form `+5%`.
#   * `--min-value=VALUE` "set minimum brightness when using delta values". The option
#     takes an *optional* argument (options[] at brightnessctl.c:101 declares
#     `{"min-value", optional_argument, NULL, 'n'}`), which means the value has to be
#     attached with `=`: a separate word is not consumed at 0.5.1 (`case 'n'` at
#     brightnessctl.c:146-150 reads optarg or defaults to 1 and never looks at the next
#     argument), and the leftover word would then be taken for the operation.
#
# The floor is the reason this script exists rather than a bare `brightnessctl set 5%-`
# on the key. Without `--min-value` the compiled floor is 0 (p.min is zero-initialised
# and only `-n` raises it), and calc_value clamps to it at brightnessctl.c:402-403, so a
# key the compositor repeats while it is held walks the backlight all the way down to a
# black screen. With `--min-value=1` the same held key stops one unit above off. The
# step itself can never be a no-op: calc_value forces the delta to +/-1 when a non-zero
# percentage request would round to zero (brightnessctl.c:397-398).
#
# Permissions, which decide whether the key works for the person pressing it: a `set` run
# by a non-root user whose sysfs node is not writable falls back to logind when the build
# has ENABLE_SYSTEMD (brightnessctl.c:217-228), and that path calls
# org.freedesktop.login1's SetBrightness on /org/freedesktop/login1/session/auto
# (brightnessctl.c:371-395). Arch builds exactly that way -- its PKGBUILD runs
# `make ENABLE_SYSTEMD=1` for both build() and package() and depends on systemd-libs,
# and Makefile:18-24 at tag 0.5.1 turns ENABLE_SYSTEMD into `-DENABLE_SYSTEMD`,
# `INSTALL_UDEV_RULES=0` and MODE 0755 -- so on this distribution the key needs neither
# root nor the `video` group nor a setuid binary. Without that build the same call fails
# with "You should run this program with root privileges." (brightnessctl.c:223-226).
#
# What has not happened: no machine here has a backlight, so none of it was observed.
# docs/UNVERIFIED.md carries that as KB-07.
set -euo pipefail

STEP='5%'
FLOOR='1'

usage() {
    printf 'Usage: %s {up,down,get}\n' "$0" >&2
}

if ! command -v brightnessctl >/dev/null 2>&1; then
    printf 'Error: brightnessctl is not on PATH, so there is no backlight to change. It is in\n' >&2
    printf "Arch's extra repository (0.5.1-3, MIT) and install.sh installs it; see KB-07.\n" >&2
    exit 127
fi

case "${1:-}" in
    up)   exec brightnessctl set "+${STEP}" "--min-value=${FLOOR}" ;;
    down) exec brightnessctl set "${STEP}-" "--min-value=${FLOOR}" ;;
    get)  exec brightnessctl get ;;
    *)
        usage
        exit 2
        ;;
esac
