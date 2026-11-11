# Experimental glass preset: audit and test plan

> **Historical document.** Kept because it records why the current rules exist.
> For today's session see [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) and [ROADMAP.md](../../docs/ROADMAP.md).


> **Path note.** This document was written before the v4 payload moved into
> `legacy/`; every command and path here that starts with `./` or names a
> repository file now lives one directory deeper, e.g. `./legacy/install-v4-session.sh`.

This is an **incremental, opt-in preset**, not the completed iPhone Glass UI upgrade. It changes only a freshly staged minimaLinux session; it does not alter the currently running desktop or merge an existing user's Noctalia settings. No Arch/Hyprland graphical session, audio device or real services were available for validation here. See [STATUS-2.0.md](../../docs/STATUS-2.0.md) and [AUDIT.md](../../docs/AUDIT.md) for the wider installer and feature audit.

## Stage A — source and compatibility audit

- The repository installs isolated Hyprland and Noctalia configuration under `~/.config/minimalinux` and runs `qs -c noctalia-shell`. Its existing bar already has launcher, clock, stats, active window, workspaces, tray, notification history, battery, volume, brightness, Control Center and session menu; Super+O opens Control Center and Super+T settings. Screenshot keybinds already exist. No new notification daemon is added.
- An installed end-user version could not be inspected: Quickshell, Noctalia and Hyprland are absent in the development environment. The installer downloads the Noctalia **v4.4.0 tag**, inspected at commit `55e9b3735d78aef8fdab49d3d3d7d31d81628b49`. `--glass` explicitly refuses another source commit or settings schema other than 49. The normal non-glass installer still follows the tag without verifying its commit. The installed AUR `noctalia-qs` runtime is not version-pinned; compatibility remains to be verified on Arch.
- The v4 `Commons/Settings.qml` and `Assets/settings-default.json` expose the preset settings. `Modules/MainScreen/MainScreen.qml` hosts panel and bar backgrounds on a full-screen `noctalia-background-*` layer, while notification popups use `noctalia-notifications-*`. Hyprland v0.54.0 source supports `match:namespace`, `blur` and `ignore_alpha` rule syntax. This does **not** validate the target compositor version, actual appearance or GPU performance.
- The native Control Center v4 defaults contain Network, Bluetooth, Wallpaper, DND/history, PowerProfile, KeepAwake and NightLight shortcuts, audio input/output, profile, media/system-monitor and optional brightness cards. The preset enables the brightness card and adds the existing network and Bluetooth bar widgets without removing any existing widget. No paired/connected state is fabricated by this preset, but upstream Bluetooth radio power uses an optimistic value before polling. Some unavailable Wi-Fi/Bluetooth controls are not disabled or explained by upstream; they may do nothing or transiently misrepresent state. Wi-Fi needs NetworkManager/nmcli, Bluetooth needs BlueZ/bluetoothctl, audio needs PipeWire/WirePlumber, brightness needs supported hardware/permissions (and optional DDC setup), night light uses wlsunset, power profiles need a functioning provider. Installing or enabling those services is not done by the preset.
- Native notifications own the freedesktop notification service when enabled; do not run another daemon in the same session. Source provides actions, dismissal, history, urgency durations and a fixed maximum of five visible notifications. DND suppresses new popups and sound. The v4 source does not guarantee all desired missing-service explanations, adaptive narrow-screen layout, or a separate universal airplane mode. No coordinated-radio shortcut or additional screenshot/lock button has been implemented. Use existing screenshot/lock keybindings. The session menu uses a cancellable countdown by default, not an explicit confirmation dialog; a second click executes immediately.
- Upstream v4 plays no sound for replacement notifications, suppresses sound under DND/performance mode or output mute, and rate-limits new sounds to 100 ms; distinct-sound volume and urgency configuration are native settings. It does **not** serialize playback: even with the 80 ms chime, audio scheduling could overlap bursts. The generated chime is original synthesized PCM created by `tools/glass_preset.py`, under this repository's GPL-3.0 license (`LICENSE.txt`). It is installed into Noctalia's `Assets/Sounds`, preselected but **disabled**. Playback needs optional Qt Multimedia and a working Qt multimedia backend/audio session; neither is added to the package list. Upstream may also exclude some applications from notification sounds by default.

## Try / disable / restore

From an inactive minimaLinux session, review changes and then choose one:

```bash
./install-v4-session.sh --glass                    # normal guided install
./install-v4-session.sh --glass --skip-packages    # dependencies already installed
./install-v4-session.sh --glass --theme nord       # existing themes still apply
```

The installer displays the choice, downloads the v4 tag and checks the audited commit **before** registering/deploying the preset. It stages everything, then moves an existing isolated session to `~/.config/minimalinux.backup.<timestamp>.<random>`. **Reinstall replaces the active isolated configuration**, so custom widgets, plugins, settings and changes are not merged into the new session; they remain in that backup. Do not run the installer while the session is active. The existing non-glass installer path is unchanged. To opt out on a new install omit `--glass`; to revert an existing installation, log out and from another session run:

```bash
python3 tools/recover_session.py
python3 tools/recover_session.py --restore /full/path/to/minimalinux.backup.NAME
```

Select the actual pre-install backup shown by the first command. Recovery copies it, keeps the selected backup, and moves the current session to a separate pre-restore backup. Alternatively reinstall without `--glass` (this also replaces, rather than merges, session settings). Packages/system launchers are not rolled back by either method; see [AUDIT.md](../../docs/AUDIT.md).

Log in to minimaLinux. Open Noctalia Settings (Super+T), Notifications → Sounds, and enable sound if desired; adjust its volume there. The preselected file is `minimalinux-twinkle.wav` in the Noctalia source sound directory. Install `qt6-multimedia` and its appropriate Arch multimedia backend separately if needed, after reviewing package changes. Set panel/notification opacity to 1 in Noctalia settings for contrast, disable animation in its UI settings for reduced motion, or disable compositor blur for performance. Theme choices, colors and keybindings remain independently configurable.

## Stage E — manual validation required

In a disposable, current vanilla Arch VM or test machine with Hyprland 0.54+ using the existing Hyprlang config, Qt/Quickshell and the appropriate services:

1. Log in, inspect `hyprctl layers` and `hyprctl configerrors`, verify bar, panel and toast background blur and readability at different scaling, screen widths and themes. Check focus, keyboard navigation, floating margins, multi-monitor placement, reduced motion and contrast. Remove the added layer rule if it is unsupported or costly.
2. Click the bar Control Center or press Super+O; check real Wi-Fi and Bluetooth state, audio input/output and mute, brightness, battery, power-profile, night light, media, wallpaper and settings. Test without each device/service and after service failure; note missing explanations or stale state. Test screenshots and locking by the existing keybindings. Do not test power actions on a session with unsaved work.
3. Check that there is exactly one `org.freedesktop.Notifications` owner (for example `busctl --user status org.freedesktop.Notifications`). Use `notify-send 'minimaLinux test' 'Notification body'`; test actions with a client that supplies actions, dismissal, replacement IDs, burst limits, history, DND and urgency. Confirm another daemon is not also running.
4. With sound explicitly enabled and working multimedia, test volume, output mute, DND, urgency, replacement updates and rapid bursts. Burst non-overlap is **not guaranteed**. Test missing multimedia and audio services without relying on simulated output.
5. Log out, restore the backup above, log in again and compare prior settings/widgets. Test on a real GPU and radio hardware as well as the VM before treating this as complete.

Automated checks (mocked, not desktop validation):

```bash
bash -n install-v4-session.sh
./tests/session-install.sh && ./tests/managed-files.sh && ./tests/package-audit.sh
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

Changed files for this increment: `install-v4-session.sh`, `tools/glass_preset.py`, `tests/test_glass_preset.py`, `tests/test_installer_cli.py`, this document, `README.md`, and `STATUS-2.0.md`.
