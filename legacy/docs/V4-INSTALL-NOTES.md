# Session installation notes

> **Historical document.** Kept because it records why the current rules exist.
> For today's session see [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) and [ROADMAP.md](../../docs/ROADMAP.md).


> **Path note.** This document was written before the v4 payload moved into
> `legacy/`; every command and path here that starts with `./` or names a
> repository file now lives one directory deeper, e.g. `./legacy/install-v4-session.sh`.

The supported installer is `./install-v4-session.sh`, run as the user who will log in. It installs Arch packages with pacman, `noctalia-qs` with an existing `yay` or `paru`, downloads Noctalia v4.4.0 from GitHub, and registers a Wayland session with sudo. It does not configure a display manager, GPU driver, audio system, network, or login service. Make sure those already work on your machine. See the README for requirements and the login steps.

## Guided installation

Run `./install-v4-session.sh` in a terminal to choose the installation mode, theme, optional apps, and welcome screen. Review the summary before confirming. `./install-v4-session.sh --verbose` shows commands and additional progress; it does not enable shell tracing. Use `./install-v4-session.sh --help` for flags, including `--skip-packages` for a manual dependency setup. `--yes` only accepts the installer's review; pacman, the AUR helper, and sudo may still ask questions. Optional apps cannot be combined with `--skip-packages`.

The installer prints hardware and compatibility information before confirmation. Use `python3 tools/preflight.py --no-network` for an independent read-only report. A private operation log and, for package installs, before/after package inventories are stored in `${XDG_STATE_HOME:-~/.local/state}/minimalinux/logs/`. The log does not capture package-manager output.

If installation fails, packages already installed are not removed. A failure during registration can leave some managed system launchers; rerun or use `./uninstall-v4-session.sh`. Existing session configuration is backed up before replacement.

## Troubleshooting

- **No minimaLinux entry:** Make sure your display manager supports Wayland sessions and reads `/usr/share/wayland-sessions`, then log out. Check that `/usr/share/wayland-sessions/minimalinux.desktop` and `/usr/local/bin/minimalinux-session` exist. For a TTY login, use `dbus-run-session /usr/local/bin/minimalinux-session`.
- **Session exits or does not start:** Check that the installer was run for this user, and that `~/.config/minimalinux/hypr/hyprland.conf` exists. Check your display manager and Hyprland logs, GPU drivers, and Hyprland's hardware documentation. You can select your original desktop at the login screen.
- **No bar or launcher:** Check that `noctalia-qs` and the `qs` executable are installed and that `~/.config/minimalinux/quickshell/noctalia-shell/shell.qml` exists. The bundled configuration requires the unmaintained Noctalia v4, not v5. AUR builds may fail or packages may change; check the AUR helper's output and resolve errors before rerunning the installer.
- **Apps look different or browser settings are missing:** The session uses its own `XDG_CONFIG_HOME`. Other applications may use different settings and profiles while in minimaLinux. Your regular session's configuration is not removed.
- **Reinstalling:** The previous `~/.config/minimalinux` is moved to a uniquely named `~/.config/minimalinux.backup.*` directory. Copy or restore any customizations you want to keep.
- **Installer refuses a file:** Existing symlinks, unmanaged files, and managed files whose content differs from the shipped launcher are not overwritten. Back up and inspect the conflict manually. The uninstaller also refuses to remove such files.

The legacy fresh-install script has a different, destructive workflow and is not suitable for installing alongside an existing desktop.

## Diagnostics and recovery

- `python3 tools/diagnose.py --no-network` checks commands, configuration paths, optional Hyprland `--verify-config` support, Noctalia source, service status, DDC prerequisites when enabled, and the latest operation log. It returns nonzero on warnings. Hyprland may write a runtime log during verification; no services or drivers are changed.
- `python3 tools/diagnose.py --repair` reports that no automatic repairs are implemented and exits without modifying anything.
- `python3 tools/recover_session.py` lists backups. Use `python3 tools/recover_session.py --restore /absolute/path/to/minimalinux.backup.NAME` and confirm to copy one back. Current config is moved aside and the source backup remains intact. Symlink backups require manual inspection.
- Theme changes create snapshots with a manifest in `~/.config/minimalinux/minimalinux/theme-backups/`; rollback is attempted if a multi-file theme operation fails. If rollback reports failure, inspect the referenced snapshot manually. Avoid concurrent edits in Noctalia.

## Theme and terminal

- Run `nwg-look` for GTK 3 appearance settings and use Noctalia's settings for bar, wallpaper, and shell colors. GTK 4/libadwaita or sandboxed apps may not honor the GTK 3 theme.
- Kitty uses Fish for its interactive terminal only; the installer does not change your login shell. Fish provides autosuggestions and syntax highlighting itself. `fzf`, `zoxide`, and `eza` integrations are conditional on those tools being installed.
- If the glyphs in the prompt appear as boxes, verify `ttf-jetbrains-mono-nerd` is installed and Kitty is using `JetBrainsMono Nerd Font Mono`. `--skip-packages` does not install themes, fonts, or shell tools.

## Customization center

- Press Super+K or open **minimaLinux Customize** from the launcher. Super+H opens its searchable shortcut list. The first-run welcome state is kept under `~/.local/state/minimalinux/`.
- If it does not open, check that `python-gobject` and `gtk3` are installed, and run `/usr/local/bin/minimalinux-customize` in a terminal to see errors. Wallpaper actions require the running minimaLinux Noctalia session.
- Appearance and bar settings are saved to the isolated session configuration. GTK applications and Kitty may need to be restarted; if Noctalia doesn't reload its settings, log out and in. Do not edit Noctalia settings simultaneously from the center and Noctalia.

## Tests

From the repository root run `./tests/session-install.sh`, `./tests/managed-files.sh`, `./tests/package-audit.sh`, and `python3 -m unittest discover -s tests -p "test_*.py"`. These exercise installer mocks and configuration logic; they do not replace testing an Arch graphical session.
