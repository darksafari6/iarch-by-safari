# minimaLinux

> **Historical document.** Kept because it records why the current rules exist.
> For today's session see [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) and [ROADMAP.md](../../docs/ROADMAP.md).


> **Path note.** This document was written before the v4 payload moved into
> `legacy/`; every command and path here that starts with `./` or names a
> repository file now lives one directory deeper, e.g. `./legacy/install-v4-session.sh`.

minimaLinux is a set of Hyprland dotfiles with the [Noctalia shell](https://github.com/noctalia-dev/noctalia-shell), Kitty, Fish and other desktop tools. Install it alongside an existing Arch Linux desktop and choose **minimaLinux** at the login screen.

## Desktop preview

![Example of the minimaLinux Hyprland desktop with a Tokyo Night-style theme and Noctalia bar](../../assets/screenshots/desktop-tokyo-night.png)

*An example of a customized minimaLinux desktop. The current installation uses a solid dark wallpaper by default; wallpaper, bar layout and colors can be changed in Noctalia settings.*

<details>
<summary>See another desktop example</summary>

![Example of the minimaLinux desktop with a red wallpaper and top bar](../../assets/screenshots/desktop-red.png)

</details>

## Requirements

- An up-to-date **vanilla Arch Linux** installation (including a fresh `archinstall` system), internet access, and a normal user with sudo access. Derivatives are not supported or tested.
- A Wayland-capable display manager with a session chooser (for example, SDDM or GDM), already installed and enabled. The installer does not change your display manager or enable automatic login.
- Git, and an existing AUR helper (`yay` or `paru`). The Noctalia Quickshell runtime (`noctalia-qs`) is installed from the AUR using the helper; review their build files and prompts as you would for any AUR package. Package names and availability can change.
- A working graphics driver and a system capable of running Hyprland. See the [Hyprland documentation](https://wiki.hyprland.org/) for hardware and NVIDIA guidance.

## Install alongside your desktop

```bash
git clone https://github.com/darksafari6/iarch-by-safari.git
cd iarch-by-safari
./install-v4-session.sh
```

Run as your **normal user**, not `sudo ./install-v4-session.sh`. The script asks for confirmation, uses sudo to install Arch packages and register the session, runs your AUR helper as your user for `noctalia-qs`, and downloads Noctalia shell v4.4.0 into your session config. This older, unmaintained v4 release is required by the bundled Quickshell configuration; it is not the newer Noctalia v5. If package installation fails, resolve the error and rerun it. The installer does not remove packages, add third-party pacman repositories, change the default shell, or reboot the computer.

### Experimental glass preset

For an opt-in translucent Noctalia v4 bar, panels and notifications, run `./install-v4-session.sh --glass`. This stages a fresh configuration and backs up an existing minimaLinux session; it does **not** merge your custom settings. The preset has not been tested in a real graphical session and is not the complete requested Glass UI. Sound is off by default. Read the [glass audit, limitations, test plan and rollback instructions](GLASS-UI.md) before trying it.

A separate Noctalia v5 profile deployment helper is under development; see the [v5 port status](../../docs/V5-PORT-STATUS.md). This session installer targets v4; the main v5 installer is a separate workflow.

### Installer choices

In a terminal, the guided installer offers a complete or session-only install, an initial theme, optional apps, and the first-login welcome screen. It shows a summary before making changes. Choose **complete** to install the required packages; **session only** assumes you installed all dependencies yourself. Both download the Noctalia v4.4.0 tag and require sudo to register the session; the experimental glass preset additionally verifies its audited source commit.

```bash
./install-v4-session.sh --verbose                          # Show commands and extra progress
./install-v4-session.sh --skip-packages --theme dracula     # Deploy only, using Dracula
./install-v4-session.sh --theme catppuccin --apps firefox,audio
./install-v4-session.sh --help
```

Available themes: `tokyo`, `catppuccin`, `nord`, `dracula`, `light`. Optional app names: `firefox`, `audio` (pavucontrol), `images` (loupe), `editor` (mousepad). `--no-welcome` disables the automatic welcome screen; Super+K still opens the customization center. `--yes` accepts the installer review and uses defaults for choices not supplied on the command line, but **does not** suppress sudo, pacman, or AUR-helper prompts. Without a terminal the menus use defaults, and the review still needs confirmation unless `--yes` is supplied. Colors automatically turn off for redirected output, dumb terminals, or `NO_COLOR`. `--no-network-check` skips the connectivity probe, but the Noctalia source download still needs network access.

The installer displays a read-only hardware and compatibility report before confirmation. Detection is best-effort: missing utilities produce an unknown result, and NVIDIA drivers are never installed or changed automatically. The complete package mode requires `ID=arch` and `/etc/arch-release`; session-only mode displays a warning on other systems, which remain unsupported.

After confirmation, the installer records operations and outcomes in a private `~/.local/state/minimalinux/logs/` file (or under `$XDG_STATE_HOME`). Complete installations also record before/after pacman package inventories and the calculated additions; review them manually, as **no packages are automatically removed**. Package manager output and passwords are not copied into the log.

Packages already installed are not rolled back if a later step fails. If registration fails partway through, rerun the installer or use `./uninstall-v4-session.sh` to remove managed session entries. Existing minimaLinux configuration is backed up before replacement. Managed system launcher files with different contents are not overwritten; inspect them manually.

**Then log out**, select **minimaLinux** in your display manager's session menu (often a gear icon), and log in. Your old session remains available in the same menu. The entry is registered system-wide, but the configuration is installed only for the user who ran the installer; each user must run it for their own account.

If you do not use a display manager, log out of your graphical session and start it from a TTY with `dbus-run-session /usr/local/bin/minimalinux-session` instead. Do not start it inside an existing graphical session.

## What changes

- Copies these dotfiles and Noctalia v4 source to `~/.config/minimalinux/`, leaving the existing `~/.config/hypr`, Noctalia, Kitty, Fish and other configs in place. Reinstalling saves the previous minimaLinux directory as `~/.config/minimalinux.backup.*` rather than merging or deleting it. Restore it manually if needed.
- Installs the system-wide session launcher, login entry, and **minimaLinux Customize** application launcher. The installer refuses to overwrite unmanaged files at those paths.
- In the minimaLinux session, `XDG_CONFIG_HOME` points at `~/.config/minimalinux`. This affects **all** programs launched in that session, not just Hyprland: their preferences or browser profiles may differ from your usual session. Other XDG data, system services, packages, and user files are shared; this is not a sandbox. D-Bus-activated services can also share state with other sessions.
- The old fresh-install-only script is retained as `legacy/legacy-install.sh` for reference. It makes extensive system and config changes and is **not** the supported way to install the separate session.

## Using and customizing the session

- **Super+Return** opens Kitty, **Super+D** opens the launcher, **Super+K** opens the customization center, **Super+H** searches shortcuts, and **Super+Shift+M** logs out.
- Adjust `~/.config/minimalinux/hypr/monitors.conf`, `inputs.conf`, and `keybinds.conf` for your hardware and preferences. The default monitor setting uses the preferred mode.
- For NVIDIA, review the commented environment settings in `~/.config/minimalinux/hypr/startup.conf` and the current Hyprland NVIDIA documentation before changing them.
- A browser and VS Code are not installed by default; the browser shortcut searches for an existing supported browser, and the editor shortcut requires `code`.
- Noctalia provides the bar, launcher and lock screen. Its configuration and wallpaper cache are separate from your regular desktop’s Noctalia settings.

## Customization center

Unless disabled during installation, the welcome/setup screen opens on your first minimaLinux login. Open it again with **Super+K** or search for **minimaLinux Customize** in the launcher. It includes:

- **Appearance:** Tokyo Night, Catppuccin, Nord, Dracula, or Light presets, GTK icons and fonts. Hyprland and Noctalia use the chosen scheme; restart apps for GTK and open new terminals for Kitty changes. GTK 4/libadwaita and sandboxed apps may not follow the GTK 3 theme.
- **Wallpaper:** preview an image and set it on all monitors. Noctalia must be running, and the image must remain at its selected path. For wallpaper-derived colors, open Noctalia settings and enable **Use wallpaper colors** under Color Scheme. This changes Noctalia's colors; Kitty and Hyprland keep their chosen preset.
- **Terminal:** select Kitty colors, font and size, plus a detailed or minimal Starship prompt. Changes apply to new terminals. Generated settings live in `kitty/minima-colors.conf`, `kitty/minima-profile.conf`, and `fish/conf.d/minimalinux-prompt.fish` under the session config.
- **Bar & lock:** choose the bar position/density and lock screen clock/avatar. The bar includes workspaces, clock, system stats and a session/power menu. Use advanced Noctalia settings to rearrange widgets and change lock screen options.
- **Shortcuts:** search the actual session keybinds. **Optional apps:** select packages to install in a terminal with a sudo/pacman confirmation; none are installed automatically.

When automatic welcome is enabled, the first-run marker is `~/.local/state/minimalinux/welcome-shown` (or under `$XDG_STATE_HOME`); remove it to show the welcome screen again. If installed with `--no-welcome`, open the center with Super+K instead. The center requires `python-gobject` and GTK 3, installed by default but not by `--skip-packages`. Theme changes back up affected files under `~/.config/minimalinux/minimalinux/theme-backups/` and attempt rollback if an application fails. Changes to Noctalia settings rely on its file watcher; if they do not appear immediately, log out and back in. Avoid editing its settings simultaneously in both tools.

## Look and terminal

The default look (unless another theme was selected) uses **Tokyo Night** Noctalia colors and Hyprland borders, a solid dark wallpaper, the `adw-gtk3-dark` GTK 3 theme, Papirus Dark icons, and Bibata cursors. Noto Sans, emoji fonts, and JetBrainsMono Nerd Font are installed by the normal installer. GTK 4 and libadwaita applications may follow their own theme or system color preference rather than the GTK 3 theme; sandboxed apps may also need theme access.

- Open Noctalia settings with **Super+T** to change the bar, color scheme, and wallpaper. `nwg-look` offers a graphical GTK 3 appearance editor. Application theme settings may vary by toolkit.
- Edit `~/.config/minimalinux/kitty/kitty.conf` for the Kitty font, padding, and palette. Kitty launches Fish without changing your account's login shell. The normal installer includes `starship`, `fzf`, `zoxide`, and `eza`; with `--skip-packages`, install these and the theme/font packages yourself to get the full experience.
- Fish includes command autosuggestions and syntax highlighting. Press **Right** to accept a suggestion, **Alt+Right** for one word, or **Tab** for completions. **Ctrl+R** searches history with fzf, `z <directory>` jumps to a frequently visited directory with zoxide, and `ll` / `lt` list files with eza. These helpers activate only when installed. Customize them in `~/.config/minimalinux/fish/config.fish`; change the prompt in the customization center or edit the selected `~/.config/minimalinux/minimalinux/starship-*.toml` profile.
- To apply these defaults to an existing minimaLinux installation, update the checkout and rerun `./install-v4-session.sh`. Reinstalling backs up the entire previous session config, including your Noctalia, Fish and Kitty customizations, to `~/.config/minimalinux.backup.*`; it does not merge them. Copy back the changes you want to keep, then log out and select minimaLinux again.

## Uninstall

From the cloned repository, run `./uninstall-v4-session.sh` as your normal user. After confirmation it removes unmodified managed system-wide session and customization launchers and desktop entries. **This removes the entry for all users.** Modified entries and symlinks are retained for manual review. Packages, your minimaLinux config and its backups remain. If no longer needed, remove `~/.config/minimalinux` and any `~/.config/minimalinux.backup.*` directories manually. Existing desktop configurations are not touched.

## Diagnostics and recovery

```bash
python3 tools/preflight.py                 # hardware report, no installation
python3 tools/diagnose.py                  # read-only checks; nonzero if warnings
python3 tools/diagnose.py --no-network     # skip the connectivity probe
python3 tools/recover_session.py            # list session backups only
python3 tools/recover_session.py --restore ~/.config/minimalinux.backup.NAME
```

Recovery requires confirmation, copies the chosen backup without deleting it, and moves the current session config to a new backup first. Symlink backups are not restored automatically. Diagnostics do not change services or drivers. When supported by the installed Hyprland and an `XDG_RUNTIME_DIR` exists, diagnostics run `Hyprland --verify-config`; Hyprland itself may write a runtime log. `python3 tools/diagnose.py --repair` currently reports that no automated repair is available and makes no changes.

The original optional printer, Bluetooth, gaming, browser, audio and DDC/CI flows remain in `legacy/legacy-install.sh`, but **are not yet available in the supported session installer**. The legacy script also modifies repositories, services, configuration ownership, and packages and is not a safe substitute for an existing desktop. See [the audit](../../docs/AUDIT.md) and [2.0 status](../../docs/STATUS-2.0.md) before using or contributing to it.

To add a preset today, define its supported Noctalia v4 scheme and colors in `.config/minimalinux/backend.py`, expose its name in the installer if desired, and test on the target versions. This is not yet a standalone declarative theme format; unsupported components and custom schemes require manual validation.

See [InstallNotes.md](V4-INSTALL-NOTES.md) for troubleshooting. The project is licensed under GPL-3.0; Noctalia is credited to its own developers and contributors.

## Contributing and bug reports

Open an issue or pull request with reproduction steps, Arch and Hyprland versions, and relevant **redacted** logs. Do not share credentials or private data. Run the tests listed in [InstallNotes.md](V4-INSTALL-NOTES.md) before submitting changes.
