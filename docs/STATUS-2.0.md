# minimaLinux 2.0 — work in progress

> **Historical document.** Kept because it records why the current rules exist.
> For today's session see [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md).

The [audit](AUDIT.md) describes the starting point and the original feature map. The following changes are incremental; this is **not a completed or production-validated 2.0 release**.

## Implemented and covered by isolated tests

- The session installer refuses to overwrite modified or symlinked system launchers; uninstall retains modified/unmanaged entries. Session backups are timestamped and an explicit recovery tool preserves both the selected backup and current config.
- A read-only hardware/OS report runs before confirmation, with best-effort GPU, NVIDIA, CPU, RAM, disk, session, pacman, sudo and optional connectivity checks. Complete installs reject systems not identified as vanilla Arch. Missing optional commands report unknown.
- Private logs record phases, command status and backup paths. Pacman before/after inventories record additions without removing anything. They do not capture package output and cannot establish which dependency is safe to remove later.
- The existing theme center now snapshots affected session files and attempts rollback on write failure; Nord was added alongside the existing presets, and the GUI shows color/component preview information.
- Read-only diagnostics check available Hyprland validation, Noctalia source, config paths, service status, DDC prerequisites and logs. No automated repair is implemented.

## Experimental glass increment

The opt-in `install-v4-session.sh --glass` preset adds v4-native translucency, brightness card, network/Bluetooth widgets and a disabled original chime. It is not a complete Glass UI and has not been exercised in a real graphical session. See [GLASS-UI.md](GLASS-UI.md) for the source audit, important native-control limitations and rollback/test instructions.

## Remaining work / limitations

- The supported session installer still does **not** port the legacy printer, Bluetooth, gaming, audio/Dolby, media, non-Firefox browser and DDC flows. The preserved legacy script has unsafe system-wide effects and is not recommended for an existing system. Package provenance and safe service/group/repository handling need design and tests before those flows can be offered safely.
- No declarative theme format, Crimson preset, custom theme import workflow, or general theme snapshot restore UI exists. GTK4/libadwaita and external apps may not follow GTK3 settings. Noctalia v4 file-watcher updates and rollback have not been validated in a real running session.
- The GTK customization center is still included in the normal package set rather than independently optional, and does not yet cover startup apps, diagnostics, package ownership, or recovery. A separate terminal diagnostic and recovery tool is available.
- Installation is not a complete transaction: partial system launcher registration and package changes can remain after failure or interruption. The log and package inventory support manual review; the uninstaller deliberately does not remove packages, change services, or automatically restore user data.
- `--yes` accepts the installer review but is not a full unattended mode: sudo, pacman and AUR helpers may still prompt. No unattended approval of risky package-manager operations is provided.
- ShellCheck, real Arch package-manager/AUR builds, NVIDIA/DDC hardware, Bluetooth/audio services and a graphical Hyprland/Noctalia login have not been tested in this sandbox. Confirm them in a disposable Arch VM or hardware test before release.
