# Glass desktop profile

The glass profile is the visual and interaction layer of iArch by Safari. It configures the
Hyprland session and the shell that the session launches; it does not replace Arch Linux,
Hyprland, or system authentication. Shell configuration keys are the upstream Noctalia v5+ ones —
this repository does not invent any.

## Architecture decision

Use the Noctalia v5+ native shell and its supported TOML configuration, built-in Control Center, Settings, notification service, dock, launcher, and IPC. This avoids adding a second layer-shell UI process or a second owner of the Freedesktop notification service.

Configuration files:

- `.config/noctalia/config.toml` — glass-focused shell, bar, dock, Control Center, notifications, and sound settings.
- `.config/noctalia/palettes/iarch-midnight.json` — custom dark/light palette.
- `scripts/iarch-control-center.sh` — fixed, allowlisted IPC shortcuts.
- `scripts/iarch-healthcheck.sh` — read-only diagnostics.

The existing installer deploys top-level entries from the repository's `.config` directory to the user's `~/.config`. The new Noctalia profile is therefore included in the same config deployment path. The installer backs up an existing `~/.config/noctalia` before copying the repository profile.

## Compatibility

This profile targets the shell at v5+. The repository README also says it uses v5. Noctalia v4 (legacy Quickshell-based release) uses a different configuration architecture; do not apply this TOML profile to v4 without migration.

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
bash scripts/iarch-healthcheck.sh
~~~

Open specific Control Center sections:

~~~bash
bash scripts/iarch-control-center.sh network
bash scripts/iarch-control-center.sh bluetooth
bash scripts/iarch-control-center.sh audio
bash scripts/iarch-control-center.sh notifications
bash scripts/iarch-control-center.sh power
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

## Control centre

`Super + I` opens Noctalia's control centre. `scripts/iarch-control-center.sh` wraps the same IPC with fixed commands, so a keybind or a script never has to assemble one: `home`, `audio`, `network`, `bluetooth`, `notifications`, `power`, `monitor`, `media`, `system`, `calendar`, `weather`, `screen-time`, `settings`, `wallpaper`, `launcher` and `session`. The panel is 700 px wide, its sidebar shows icons and labels on the Home tab and collapses to icons when something opens a tab directly, and no tab is hidden — a hidden tab also disappears from keyboard navigation and from the launcher's Panels provider, so hiding one is a person's choice rather than a default this profile picks.

The Home tab's shortcut row holds six buttons, which is the most it shows:

| Tile | `type` | What it does | Right-click |
| --- | --- | --- | --- |
| Wi-Fi | `wifi` | Toggles wireless | Opens the Network tab |
| Bluetooth | `bluetooth` | Toggles the adapter | Opens the Bluetooth tab |
| Do Not Disturb | `notification` | Toggles toast suppression; history keeps filling | Opens the Notifications tab |
| Night Light | `nightlight` | Toggles the blue-light filter | Toggles always-on |
| Power profile | `power_profile` | Cycles the system power profile, and shows the current one | Opens the System tab |
| Caffeine | `caffeine` | Holds idle and sleep off | — |

Four tiles the design brief asks for have no type in Noctalia v5.4.1, and a fifth is a dead button without a plugin. None of them is emitted, because a button that renders nothing is worse than no button — `shortcutSchema()` declares a plain string field, so an unknown `type` is not warned about or rejected, it just never appears. `iarch/cli/render_noctalia.py` records the eighteen documented types as an enum of its own and refuses to write one of them, which is the one place this profile is stricter than the shell.

| Asked for | What v5.4.1 actually has | Where it lives instead |
| --- | --- | --- |
| Airplane mode | No type at all | The `wifi` tile plus `audio` and `mic_mute`, which is everything a desktop can honestly mean by it |
| Game mode | No type at all | `iarch-gamemode toggle`, wireable as a session-panel button (below) |
| Focus mode | No type at all | `iarch-focus toggle`, with `caffeine` and `notification` covering the "do not dim, do not disturb" half |
| Performance profile | `power_profile` cycles the *system* profile, which is not this profile's intensity | `iarch-theme apply --intensity performance` |
| Screenshot | A bar widget, not a control-centre tile | The bar's `screenshot` widget |
| Screen record | `screen_recorder` exists, but stays disabled unless the official `noctalia/screen_recorder` plugin is enabled | Enable the plugin first, then the type can be added |

There is no custom slider either. Volume is the Audio tab and brightness the Monitor tab. Glass intensity and animation speed are commands — `iarch-theme apply --intensity {crystal,frosted,soft,performance}` and `iarch-anim speed 0.5`–`2.0` — and the Part 4 settings application is where they grow a slider. The media tab's visualizer is the one element in the panel that moves continuously rather than in answer to something, so it follows the same `motion.enabled` switch as every other animation this profile renders: on for crystal, frosted and soft, off for performance.

The one place v5.4.1 lets a config file add a button that runs a command of ours is `[[shell.session.actions]]`: `action = "command"` with a `command`, `label`, `glyph`, `variant`, `shortcut` (any XKB key name such as `F1`, or a combo such as `Ctrl+1`, live while the session panel is open) and `countdown_seconds`. It is recorded in `data/design/noctalia.json` and deliberately not emitted yet, for two reasons: the commands it would run do not exist until later in Part 3, and Noctalia runs that string with `/bin/sh -c` as the session user, so nothing goes in it until there is something real to run. The same restraint applies to `[shell.session.power]`, whose suspend, reboot and shutdown overrides are left unset so the shell keeps using its own prioritized backend list rather than a `sudo` line invented here.

## Notification sound

The profile selects Noctalia's built-in Freedesktop sound theme at a reduced volume, but notification sounds are disabled by default. GUI-managed overrides may take precedence. The currently documented v5 configuration does not establish an arbitrary custom audio-file path for notifications, so this profile does not create a second notification daemon or falsely claim that a custom iPhone-style sound is connected. A custom twinkle asset should only be integrated through a supported Noctalia sound API or a tested extension that will not duplicate notifications.

## Security and desktop boundaries

The profile retains Noctalia's existing Settings and session/lock integrations. The actual lock screen remains backed by the Linux session locker/authentication stack; no custom password collection is introduced. Apple-specific AirDrop, iCloud, cellular toggles, and exact iOS app lifecycle have no direct universal desktop equivalent and are not emulated as fake working controls.

## Rollback

If the shell looks wrong after applying the profile:

1. Restore the timestamped backup made before copying.
2. Run `noctalia config validate` again.
3. Run `noctalia msg config-reload`, or log out and back into Hyprland if the shell cannot reload.

Do not delete the old configuration until the new one has passed live-session testing.
