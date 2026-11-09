# minimaOS — Glass Desktop Profile

minimaOS is a visual and interaction profile for the existing minimaLinux Hyprland session. It extends the Noctalia v5+ shell already launched by this project; it does not replace Arch Linux, Hyprland, or system authentication.

## Architecture decision

Use the Noctalia v5+ native shell and its supported TOML configuration, built-in Control Center, Settings, notification service, dock, launcher, and IPC. This avoids adding a second layer-shell UI process or a second owner of the Freedesktop notification service.

Configuration files:

- `.config/noctalia/config.toml` — glass-focused shell, bar, dock, Control Center, notifications, and sound settings.
- `.config/noctalia/palettes/minimaOS.json` — custom dark/light palette.
- `scripts/minimaos-control-center.sh` — fixed, allowlisted IPC shortcuts.
- `scripts/minimaos-healthcheck.sh` — read-only diagnostics.

The existing installer deploys top-level entries from the repository's `.config` directory to the user's `~/.config`. The new Noctalia profile is therefore included in the same config deployment path. The installer backs up an existing `~/.config/noctalia` before copying the repository profile.

## Compatibility

This profile targets Noctalia v5+. The repository README also says it uses Noctalia v5. Noctalia v4 (legacy Quickshell-based release) uses a different configuration architecture; do not apply this TOML profile to v4 without migration.

Noctalia v5+ merges TOML files from `~/.config/noctalia` and applies GUI-managed overrides from `~/.local/state/noctalia/settings.toml`. Settings previously chosen in the GUI can override values in this profile. If a value appears unchanged, inspect the active Settings overrides instead of appending duplicate keys.

## Apply manually

From the repository root, back up your current shell configuration, copy the profile, and validate it before restarting the shell:

~~~bash
stamp=$(date +%Y%m%d-%H%M%S)
if [ -d "$HOME/.config/noctalia" ]; then
  cp -a "$HOME/.config/noctalia" "$HOME/.config/noctalia.backup.$stamp"
fi
mkdir -p "$HOME/.config/noctalia"
cp -a .config/noctalia/. "$HOME/.config/noctalia/"
noctalia config validate
~~~

If validation reports errors, restore your backup before restarting Noctalia. Do not remove the backup until you have logged out and back in and verified the desktop.

Useful actions:

~~~bash
noctalia config validate
noctalia msg config-reload
noctalia msg panel-toggle control-center
noctalia msg settings-toggle
bash scripts/minimaos-healthcheck.sh
~~~

Open specific Control Center sections:

~~~bash
bash scripts/minimaos-control-center.sh network
bash scripts/minimaos-control-center.sh bluetooth
bash scripts/minimaos-control-center.sh audio
bash scripts/minimaos-control-center.sh notifications
bash scripts/minimaos-control-center.sh power
~~~

The network, Bluetooth, audio, monitor, and power panels use Noctalia's real system integrations. Their availability depends on hardware, permissions, and installed system services. A laptop without a battery, for example, cannot provide battery controls.

## Visual features

- Rounded translucent top bar with clock, workspaces, network, Bluetooth, audio, brightness, battery, notification, and session controls.
- Floating glass Control Center and wallpaper/session panels.
- Rounded application dock with running-app indicators and pointer magnification.
- Translucent Settings window, refined radius/shadow, and animated panel behavior.
- Top-right notification toasts with app identity, actions, history, and restrained sound level.
- Dark/light custom palette with cool blue, violet, and cyan accents.

Compositor blur depends on the supported compositor and its settings. If blur is unavailable, panels should remain readable with background opacity and borders.

## Notification sound

The profile enables Noctalia's built-in Freedesktop sound theme at a reduced volume, including notification sounds. The currently documented v5 configuration does not establish an arbitrary custom audio-file path for notifications, so this profile does not create a second notification daemon or falsely claim that a custom iPhone-style sound is connected. A custom twinkle asset should only be integrated through a supported Noctalia sound API or a tested extension that will not duplicate notifications.

## Security and desktop boundaries

The profile retains Noctalia's existing Settings and session/lock integrations. The actual lock screen remains backed by the Linux session locker/authentication stack; no custom password collection is introduced. Apple-specific AirDrop, iCloud, cellular toggles, and exact iOS app lifecycle have no direct universal desktop equivalent and are not emulated as fake working controls.

## Rollback

If the shell looks wrong after applying the profile:

1. Restore the timestamped backup made before copying.
2. Run `noctalia config validate` again.
3. Run `noctalia msg config-reload`, or log out and back into Hyprland if the shell cannot reload.

Do not delete the old configuration until the new one has passed live-session testing.
