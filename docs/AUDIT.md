# minimaLinux 2.0 — repository audit

Audit baseline: `main` / `30208a39101737c5e273ab99e7696dad6a5af7a7`, plus the existing uncommitted work on `arena/0f1423cc-minimalinux`. This document distinguishes the default-branch installer from the newer session installer already present in the working tree. No production installer was run during this audit.

## Inventory

The tracked baseline contains 682 paths: Hyprland, Fish, Kitty, Fastfetch, Starship and Noctalia dotfiles and plugin sources, two desktop screenshots, docs, installers, and roughly 625 PipeWire files including HRIR WAV assets. `.config/kitty/kitty-themes` is a Git gitlink; no `.gitmodules` file is present, so the theme submodule is not automatically initialized. HRIR assets are intentionally retained. The PipeWire surround profile references `~/.config/pipewire/hrir/atmos.wav`, not the isolated session config path; activation has not been verified.

The newer working-tree session adds a GTK/Python customization center, GTK settings, isolated Noctalia settings, Wayland session launchers, and mocked tests. It is still based on Hyprland and Noctalia v4; GTK 3 and python-gobject are required by this center, but not by Hyprland itself. Noctalia v4 is unmaintained, and `noctalia-qs` AUR availability/build compatibility is not verified here.

## Existing feature and side-effect map

| Feature | Default-branch implementation (preserved as `legacy-install.sh` in the existing worktree) | Isolated v4 `install-v4-session.sh` |
|---|---|---|
| User/target | Root via sudo, discovers `SUDO_USER`; deploys to `~/.config` | Normal user with sudo; isolated `~/.config/minimalinux` and system-wide Wayland entry |
| Core packages | `PACKAGES` array near line 305 of legacy script, includes GTK, Thunar extras, codecs, filesystems, build tools, audio and more | Smaller `core_packages` array; Noctalia v4 source and AUR `noctalia-qs` |
| Additional applications | `prompt_optional_packages` / `install_optional_packages`; upscaler, downloader, mission-center, Obsidian, OBS, VS Code | Firefox, pavucontrol, loupe, mousepad only |
| Gaming | Initial gaming menu and `install_gaming_packages`: Steam, MangoHud, ProtonPlus, Wine, Winetricks, Protontricks, Lutris, Heroic, Prism, GOverlay, MangoJuice; extra lib32-MangoHud/JDK | Not exposed |
| Audio and media | Audio menu: none, EasyEffects + LV2/Calf, or bundled PipeWire profile; media menu: mpv, VLC (+ optional plugins), Dragon, Haruna, DeaDBeeF, Rhythmbox, Elisa | Not exposed; audio stack must already exist |
| Printer/Bluetooth | `install_printer_support_packages` installs CUPS family, enables/starts `cups`; `install_bluetooth_packages` installs bluez and enables `bluetooth` | Not exposed |
| Browser | `prompt_browser_installation` / `install_browser`: Vivaldi, Brave, Zen, Firefox, LibreWolf, skip | Firefox optional |
| DDC/CI | `setup_ddcutil`: installs packages, loads/persists i2c-dev, reloads udev, adds user to i2c group, enables Noctalia setting | Not exposed |
| GPU | Commented NVIDIA environment block in Hyprland startup; no detection or driver management | Same commented block; no detection or driver management |
| Repositories | `setup_chaotic_aur` enables multilib, fetches/signs Chaotic key and installs mirror/keyring, edits `/etc/pacman.conf`, refreshes package databases | Does not change repository files |
| Package removal / upgrades | `remove_conflicting_packages` calls `pacman -Rns --noconfirm dolphin polkit-kde-agent vim`; later `pacman -Syu --noconfirm` | Does not remove packages or upgrade separately |
| Files / permissions | `deploy_configs` moves each matching config to `.bak.<epoch>`, copies files, recursively chowns entire `~/.config`; may restore `backup/.config`, set XDG MIME and overwrite GTK bookmarks; optional PipeWire files merged without backup | Stages config, moves prior isolated config to `minimalinux.backup.*`; installs 4 marked system launcher/desktop files; no per-file manifest |
| Reboot | Reboot prompt loops on no and can invoke `sudo reboot now` | None |
| Uninstall | Original `uninstall.sh` removes matching user paths before looking for backups, including unrelated theme/icon directories; incomplete/inaccurate list; does not revert packages or services | Removes marked system launcher files only, keeps user config and backups; no restore workflow or installation manifest |

For exact package names and prompts, the authoritative inventories are the preserved legacy `PACKAGES`, `OPTIONALPKG` arrays and selection case statements, and the current `core_packages` and `--apps` allowlist. Several legacy names depend on Chaotic-AUR/AUR or multilib and may have changed; they should not be silently mapped to pacman without verifying current availability. The legacy audio profile is not necessarily portable to the new isolated XDG configuration.

## Prioritized issues

1. **Critical:** the default-branch uninstaller deletes matching paths regardless of ownership; legacy installer removes packages, changes repos/services and recursively chowns the user's entire config. Do not run it on an existing desktop without a separate review. The newer uninstaller avoids that deletion but cannot automatically restore backups or identify modified launcher contents beyond a marker.
2. **High:** earlier session work omitted several legacy package/service/audio/DDC options from the supported path. They remain in the legacy source but require a careful, explicit port with repository provenance and service-change rollback; do not describe them as supported by the session installer until tested.
3. **High:** the current installer registers several system files before replacing config; an interrupted registration can leave partial system changes. Backups are not timestamped/recorded in an install manifest, and package changes are not tracked. Existing managed files can be overwritten without preserving local edits.
4. **High:** hardware/OS/network/pacman preflight and a persistent installation log are missing. Current complete mode checks `/etc/arch-release` and pacman but does not distinguish derivatives reliably. `--yes` skips only the installer review; package managers may prompt.
5. **High:** theme changes write multiple files with no transaction/rollback or backup, and Noctalia settings can race with a running shell. Current themes are inline constants rather than self-describing presets. `theme()` assumes managed files and can partially update on failure.
6. **Medium:** Noctalia v4 and package names need current Arch/AUR verification. GTK4/libadwaita do not necessarily respect GTK3 settings; Python UI is currently part of core package selection. Legacy Chaotic/multilib setup and fixed PipeWire paths are machine-dependent.
7. **Medium:** no read-only system diagnostics or explicit safe repair workflow; no actual hardware, NVIDIA, DDC/CI, graphical session, package manager, or service integration tests were available in the audit sandbox. Existing tests mock install/sudo and validate configuration logic only.
8. **Medium:** previous documented fresh-Arch workflow and root requirement differ from the newer non-root session installer. The requested acceptance item “non-root invocation fails” conflicts with this newer design: its safe contract is to reject root and use sudo only for privileged operations. Document the actual contract instead of silently changing users' target account.

## Baseline checks

`bash -n` for shell scripts, `./tests/session-install.sh`, `python3 tests/test_customization.py`, `python3 tests/test_installer_cli.py`, and `git diff --check` passed. ShellCheck, an Arch package manager, Hyprland, a graphical session, and representative GPU/display hardware were not available. The checks do not prove the installer works on Arch or validate the real login session.
