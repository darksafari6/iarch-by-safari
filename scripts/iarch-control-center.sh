#!/usr/bin/env bash
# Safe, fixed-command shortcuts for the shell IPC used by iArch by Safari (Noctalia v5+).
# Usage: scripts/iarch-control-center.sh [home|audio|network|bluetooth|notifications|power|monitor|media|system|calendar|weather|screen-time|settings|wallpaper|launcher|session]
set -e

if ! command -v noctalia >/dev/null 2>&1; then
    printf 'Error: noctalia is not installed or not on PATH.\n' >&2
    exit 127
fi

ACTION="$1"
if [ "$#" -eq 0 ] || [ -z "$ACTION" ]; then
    ACTION="home"
fi

case "$ACTION" in
    home)          exec noctalia msg panel-toggle control-center ;;
    audio)         exec noctalia msg panel-toggle control-center audio ;;
    network)       exec noctalia msg panel-toggle control-center network ;;
    bluetooth)     exec noctalia msg panel-toggle control-center bluetooth ;;
    notifications) exec noctalia msg panel-toggle control-center notifications ;;
    power)         exec noctalia msg panel-toggle control-center power ;;
    monitor)       exec noctalia msg panel-toggle control-center monitor ;;
    media)         exec noctalia msg panel-toggle control-center media ;;
    system)        exec noctalia msg panel-toggle control-center system ;;
    calendar)      exec noctalia msg panel-toggle control-center calendar ;;
    weather)       exec noctalia msg panel-toggle control-center weather ;;
    screen-time)   exec noctalia msg panel-toggle control-center screen-time ;;
    settings)      exec noctalia msg settings-toggle ;;
    wallpaper)     exec noctalia msg panel-toggle wallpaper ;;
    launcher)      exec noctalia msg panel-toggle launcher ;;
    session)       exec noctalia msg panel-toggle session ;;
    *)
        printf 'Unknown action: %s\n' "$ACTION" >&2
        printf 'Allowed actions: home audio network bluetooth notifications power monitor media system calendar weather screen-time settings wallpaper launcher session\n' >&2
        exit 2
        ;;
esac
