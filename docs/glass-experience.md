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

## Launcher and window switcher

`Super + D` opens the launcher: a floating glass panel, centred, 760 px wide inside the 560–1100 range `kLauncherWidthRange` allows, with the search field at the bottom and the Recent view on arrival. It needs no plugin and no second application — every provider below is built into Noctalia v5.4.1.

| Provider | Prefix | What it gives you |
| --- | --- | --- |
| Applications | *none* | Fuzzy search over `.desktop` entries, weighted, boosted by how often you launch something. Flatpak, Snap, Nix and AppImage results are marked |
| Calculator | `/calc`, and globally on any query containing a digit | `libqalculate`: arithmetic, `sin`/`sqrt`/`pi`, unit conversion (`10 cm to in`), number bases (`0xff`). Enter copies the result |
| Emoji | `/emo` | Search by name, category or keyword; activating copies the character |
| Panels | `/pan` | Every panel the shell knows, plus one row per visible control-centre tab — this is how the clipboard history is reached from the launcher |
| Wallpaper | `/wall` | The directories in `[wallpaper]`; activating applies one to every monitor |
| Session | `/session` | The configured session actions, including lock, suspend, reboot and shutdown — the launcher's power commands |
| Windows | `/win` | Every open window across monitors and workspaces; activating focuses it and switches workspace if needed |

Two things the design brief asks for do not exist upstream, and neither is faked. There is **no clipboard provider**: clipboard history is its own panel, reachable through `/pan` or `scripts/iarch-control-center.sh`'s siblings in `noctalia msg panel-toggle clipboard`. There is **no web-search provider** either. A dmenu entry could imitate one — `[shell.launcher.dmenu.entry.<id>]` runs a `command` through `/bin/sh -lc` and can substitute the activated line into an `exec` string — but that substitutes text a person typed into a shell command line, and this project will not ship that. Both are recorded in `data/design/noctalia.json` with the reason, and neither is emitted.

Currency conversion is the one launcher feature that reaches the network: `fetch_exchange_rates` refreshes rates from libqalculate's online sources. It is off in the shipped payload, alongside `telemetry_enabled`, so nothing in the launcher calls a third party. Arithmetic, functions, units and number bases all work without it, and a currency query uses whatever rates are already cached.

`Alt + Tab` opens the shell's window switcher instead of moving focus invisibly. `.config/hypr/keybind.lua` binds it to `noctalia msg window-switcher hold`, which is the exact form `docs/user/ipc/shell.mdx` gives for a held-modifier keybind: a quick tap activates the previous window, `Tab`, the arrow keys and the mouse wheel cycle the cards while the overlay has focus, releasing `Alt` confirms the selected one, `Enter` confirms and closes, `Escape` cancels. `[shell.window_switcher]` chooses the look: `carousel`, the freestanding depth layout, with captions, a position counter and application icons over each preview, drawn from every monitor and every workspace, and `mru = true` so the order is most-recently-used — which is what Alt+Tab means — rather than workspace layout. Window previews need the compositor's foreign-toplevel image-capture protocol; without it the cards show application icons and everything else works the same.

The trade-off is worth stating plainly: with no shell running, that bind does nothing at all, where the compositor's own `hl.dsp.window.cycle_next()` always worked. To get the old behaviour back, replace the bind's second argument with `hl.dsp.window.cycle_next()` and re-run `python3 tools/extract_keybinds.py --write` and `python3 tools/render_shortcuts.py --write` so the keyboard map and `docs/SHORTCUTS.md` stay true.

**Overview is not enabled.** The brief's `Super + Tab` overview needs the `overview` plugin from `hyprland-plugins`, installed and enabled through `hyprpm` — a third-party component compiled against the compositor, which is exactly the kind of thing this project does not turn on for somebody. `Super + Tab` is also already taken: it is "next workspace on the focused monitor" in `.config/hypr/keybind.lua`. To try the overview anyway, in a session:

```sh
hyprpm update && hyprpm add https://github.com/hyprwm/hyprland-plugins
hyprpm enable overview && hyprpm reload
```

then bind `hyprctl dispatch overview` to a key that is not in use, and add the plugin package to your own update routine — `hyprpm` rebuilds plugins against the installed Hyprland, so a compositor upgrade without a `hyprpm update` can leave the session refusing to start.

## Notification sound

The profile selects Noctalia's built-in Freedesktop sound theme at a reduced volume, but notification sounds are disabled by default. GUI-managed overrides may take precedence. The currently documented v5 configuration does not establish an arbitrary custom audio-file path for notifications, so this profile does not create a second notification daemon or falsely claim that a custom iPhone-style sound is connected. A custom twinkle asset should only be integrated through a supported Noctalia sound API or a tested extension that will not duplicate notifications.

## Lock screen and idle

Two things have to be settled before a lock screen can be designed, and both are decisions rather than settings.

**Which client locks.** Noctalia v5.4.1 has its own lock surface (`src/shell/lockscreen/lock_screen.cpp` and `lock_surface.cpp`) and hyprlock is a separate one; both implement `ext_session_lock_v1`, and the protocol hands the lock to whichever asks first. So this project does not run both. The shell owns the lock while it is running — `Super + L` is `noctalia msg session lock` in `.config/hypr/keybind.lua`, and the launcher's `/session` provider and the session panel reach the same action — and `.config/hypr/hyprlock.conf` is the lock screen for a session where the shell is not running. That is the whole content of `lock_cmd = pidof noctalia || hyprlock` in the shipped `hypridle.conf`: prefer the lock surface that is already up, and only start a second one when it is not.

**Which daemon idles.** Hyprland's `hypridle` and the shell both watch `ext_idle_notifier_v1`, so running both means two processes racing to lock, dim and suspend the same session, and nothing on screen tells you which one won. The shell's idle system is the one this project configures, because it already respects D-Bus inhibitors (`org.freedesktop.ScreenSaver`, which is how a browser holds idle off during playback) and Wayland idle inhibitors:

| Behaviour | Timeout | Action |
| --- | --- | --- |
| `lock` | 900 s (15 min) | native `lock` — the session locks |
| `screen_off` | 960 s (16 min) | native `screen_off` — monitors off, and back on by themselves when you return |

Before either fires, `[idle] pre_action_fade_seconds = 2.0` fades a fullscreen overlay in the surface colour from transparent to opaque over two seconds — click-through, so pointer and keyboard activity still reaches the compositor, and becoming active during the fade cancels the action. That overlay is motion, so it follows the same switch as everything else: at the Performance intensity it is `0` and the action runs as soon as the compositor reports idle.

`.config/hypr/hypridle.conf` therefore ships **unlaunched**. It declares no listener, so it owns no timer: only `lock_cmd`, `before_sleep_cmd = loginctl lock-session` and `after_sleep_cmd = hyprctl dispatch dpms on`, the three commands a session with no shell still needs. Nothing in `.config/hypr/startup.lua` starts it, and a test fails if any shipped file does. To use it *instead* of the shell's idle system, add `hypridle` to the `exec_once` list in `startup.lua` **and** disable every `[idle.behavior.*]` entry in `config.toml`; doing only the first is what causes the race.

Two idle features are deliberately absent. `action = "command"` exists upstream and takes a shell string, but an idle timer is the wrong place to invent a command line for somebody else's machine — the same rule that keeps `[[shell.session.actions]]` and `[shell.launcher.dmenu.entry.*]` out of the payload. Suspend is left out entirely: which backend suspends a given machine is not knowable from a repository, and a wrong guess takes somebody's session away while they are reading. `behavior_order` is recorded but never emitted, because upstream installs a reader that discards it and a writer that emits it — setting it can only be ignored.

### The lock screen you actually see

`[lockscreen]` in the generated `config.toml` configures the shell's own lock surface, and three of its keys are decisions rather than preferences.

**One transition, named.** `transition` is not a list of effects that play in order — the shell picks *one of them at random* for every lock and unlock (`lock_screen.cpp:1152`) and randomizes that effect's own parameters too: direction 0-3, centre 0.2-0.8, stripe count 4-24, angle 0-360, cell size 0.02-0.06 (`:1159-1176`). Upstream's default lists all eleven, so an unconfigured session locks into a random one of melt, vortex, honeycomb, pixel and golden, for 1500 ms. This project emits `["fade"]`, which is the only way to get a repeatable effect, and takes the duration from the motion preset's own `fadeIn` leaf. `kLockscreenTransitionDurationRange` is `{100, 30000, 100}` — a 100 ms step with a 100 ms floor — and neither smooth's 120 ms nor minimal's 90 ms is a multiple of it, so both snap to the floor. The lock screen fades in 100 ms, the fastest upstream allows, and the record says which number was lost rather than letting 100 look like a choice nobody made. With motion off the list is empty, which is how upstream disables the lock and unlock animation entirely.

**A blurred snapshot of your own desktop.** `blurred_desktop = true` captures the desktop through `zwlr_screencopy_manager_v1`, which the shell binds at version 3 (`wayland_connection.cpp:35, :84, :1706-1709`) and which Hyprland v0.57.2 still ships (`src/protocols/Screencopy.cpp` in its own tree). A capture that fails is warned about and skipped, not fatal, so the worst case is a lock screen without the snapshot. `blur_intensity` is a 0-1 dial the code turns into a radius by multiplying — `blur_intensity * 40.0` px (`lock_surface.cpp:2007, :2104`) — which is *not* Hyprland's `decoration:blur:size` scale, and there is no verified way to convert one into the other, so it stays at the documented midpoint of 0.5 and the gap is recorded. `tint_intensity` *is* convertible: it is the alpha of a `ColorRole::Surface` overlay (`lock_surface.cpp:1321`), which is exactly what the intensity's `glass.tint_alpha` means everywhere else here, so it is written from the intensity — 0.22 for crystal, 0.34 for frosted, 0.52 for soft, 0.0 when blur is off. The login panel's border is `ColorRole::OutlineVariant` (`:1329`), the same role every other panel border in this project uses.

**Two keys are security settings, and both are emitted at their restrictive values.** `grace_period_seconds` above zero lets any keypress, or a mouse move beyond 5 px, end a lock *with no password at all*; it is emitted as `0` and a test asserts it stays there across every preset and intensity. `allow_empty_password` accepts an empty password; it is emitted `false`. `lock_before_suspend = true` locks on logind's `PrepareForSleep`, so a lid close cannot suspend an unlocked session — which is also why the hypridle fallback needs no listener of its own.

`wallpaper` and `monitors` are recorded and not emitted: a path on somebody's disk and a connector name are machine state, not repository state, and the defaults (the desktop wallpaper, every monitor) are the only answers that are right on a machine this repository has never seen.

### What the fallback lock screen looks like

The rest of this section is `.config/hypr/hyprlock.conf`, which a session only reaches when the shell is not running.


`python3 iarch/cli/render_hyprlock.py` renders it from the same tokens as everything else, and the central claim is that **hyprlock's blur is Hyprland's blur**: its manual says the background's blur options are taken from Hyprland, so `blur_passes`, `blur_size`, `noise`, `contrast`, `brightness` and `vibrancy` are written from the intensity's own `decoration:blur` values, number for number. The lock screen frosts by the same recipe as the panels and windows, rather than by a similar-looking one.

| Layer | What it is | Where it comes from |
| --- | --- | --- |
| Background | A capture of the desktop taken when the lock starts, blurred | `path = screenshot`, plus the intensity's blur recipe |
| Card | A frosted panel, 460×170, 24 px corners, hairline border | the palette's `surface` at the intensity's `tint_alpha`, `radius.panel`, `layout.border_size`, `outline_variant` at `border_alpha` |
| Field | hyprlock's own documented 400×90, 12 px corners, dots centred | `radius.input`, the palette's `surface_variant` at `tint_alpha_strong`, `on_surface` text |
| Clock | `$TIME` at the top, 28 px, with a shadow behind it | `type.sizes.xxl`, `font.ui` |
| Name and hint | `$DESC` and "Enter to unlock · Esc clears the field" below the card | `type.sizes.lg` and `sm`, `on_surface_variant` |

The field's three state colours are the palette's semantic accents — `warning` while PAM is being asked, `danger` when it refuses, `primary` when Caps Lock is on — which is the same mapping the shell uses for a critical notification's border. hyprlock documents each as a gradient, and a gradient accepts one colour.

Only `background` blurs in hyprlock, so the "frosted card" is a translucent surface colour over an already-blurred capture: the shell's panel recipe, minus a second blur pass it has no variable for. `rounding` is an int in pixels — there is no percentage rounding and no shared radius scale — and the shadow alpha is carried once, in `shadow_boost`, because that variable *multiplies* the shadow's opacity and putting the alpha in the colour too would square it.

Motion reaches the lock screen two ways. `general:compositor_fade` fades the lock surface together with the compositor's blur contribution and follows the intensity's motion switch, falling back to hyprlock's own client-side fade when the compositor does not advertise `hyprland_surface_manager_v1`. And the `animations` block takes its durations from the motion preset's own `fadeIn` and `fadeOut` leaves — 120 ms for smooth, 90 ms for minimal, nothing at all for off — converted to the seconds hyprlock's `animation` keyword takes. The tokens' `speed_multiplier` is deliberately not applied: it scales Hyprland's tree through `generated/animations.lua`, and hyprlock has no multiplier, so scaling one side would make the lock screen disagree with the session it locks.

At the Performance intensity there is no fade, no capture and no blur. `blur_passes = 0` means the desktop would be shown sharp, and a password field over sharp high-contrast content is the least readable background there is, so `path` goes empty and the palette's background fills the screen instead. `iarch/cli/qa_motion.sh` fails that combination if it ever reappears.

### What the lock screen cannot do

Recorded in `data/design/hyprlock.json` under `not_in_hyprlock`, so nobody invents a variable that silently does nothing:

- **No per-widget blur.** Only `background` blurs; a frosted card has to be a translucent colour.
- **No theme or palette file.** Colours are literals in the file, so the generator resolves the palette itself.
- **No global speed multiplier** and no reading of `hyprland.lua`: each `animation` line carries its own duration.
- **No unlock command, password file or hash.** Authentication is PAM or fprintd and nothing else.
- **No idle timeout.** hyprlock does not lock itself; a daemon does, which is the hypridle question above.
- **`SIGUSR1` unlocks it without a password**, and `onclick` can attach a command to a label, image or shape. The generator emits no `onclick`, and [SECURITY.md](../SECURITY.md) says plainly what both facts mean: a lock screen keeps a session private from somebody walking up to it, and is not a boundary against a local user who can already run commands as you.

A *live* blurred desktop behind the field — rather than a capture that freezes the moment you lock — is available and is not enabled. It needs Hyprland's `misc:session_lock_xray` and `misc:session_lock_blur` (both real v0.57.2 leaves, `src/config/values/ConfigValues.cpp:587-588`), `general:compositor_fade = true` and an empty `background:path` with a transparent colour. Those two leaves keep every workspace rendering underneath a locked session, which is compositor work spent on a screen nobody is looking at, so they stay off by default and this paragraph is how you turn them on. Fingerprint authentication is the same shape: `auth:fingerprint:enabled = true` needs fprintd and a scanner, and hyprlock reports the result through `$FPRINTPROMPT` and `$FPRINTFAIL`.

## The login screen

The login screen is not a Hyprland client and not a Noctalia panel. `greetd` starts `noctalia-greeter-session` as the unprivileged `greeter` account, and the greeter brings its own embedded wlroots compositor (`src/compositor/noctalia_compositor.c` in noctalia-greeter v1.7.0). Nothing in `.config/hypr/` or `.config/noctalia/` is read there, so the glass profile reaches the login screen by exactly one route: the shell's own Sync.

Both installers write `/etc/greetd/config.toml` with the two tables upstream's own helper prints — `[terminal] vt = 1` and `[default_session] command`/`user` — and create the greeter account the same way. One line had drifted: the state directory `/var/lib/noctalia-greeter` was left at the umask default of 0755, while the greeter's own setup tightens it to 0750 (`kSyncedDirMode`, `src/greeter/greeter_preferences.cpp:29`). It now matches, and `tests/test_greeter.py` fails if the two installers' copies of the function ever differ again.

**No `greeter.toml` ships, on purpose.** The greeter's declarative config lives at `/var/lib/noctalia-greeter/greeter.toml`, root-owned, and it wins over Sync for every key it sets. Its parser only ever warns — an unknown key logs `unrecognized key` and an invalid value logs `invalid <key> value`, and the login screen comes up looking default either way — and nearly everything worth putting in it is a fact about one machine: a connector name, an account name, a cursor theme directory, a keyboard layout. A repository that guessed those would be wrong on every machine it has not seen. `data/design/greeter.json` records the whole surface instead, with the code that enforces each default, enumeration and range, so the absence is evidenced rather than assumed.

### What Sync carries from this repository

`noctalia msg greeter-sync`, or Settings → Security → Noctalia Greeter → **Sync Now**, stages a snapshot in `$XDG_RUNTIME_DIR/noctalia-greeter-sync` and a privileged helper merges it into the state directory. Log out or restart greetd to see the result.

| Carried | From | Note |
| --- | --- | --- |
| Palette | `.config/noctalia/palettes/*.json` | Sixteen colours, and all sixteen or nothing: an incomplete palette is refused by the helper, so every shipped palette is tested against the greeter's own `requiredPaletteKeys()` |
| Wallpaper, per output too | `[wallpaper]` and the shell's wallpaper state | `fill_mode` defaults to `crop`; `span` projects one image across the logical multi-monitor layout |
| Theme mode | the resolved light/dark mode | `[appearance] theme_mode` |
| Corner radius scale | `[shell] corner_radius_scale = 1.5` | The derived `radius.lg / radius.md` — 24 px over 16 px — so the login screen's radii follow the same tokens as the panels |
| Font family | `[shell] font_family` | Shipped empty, so Sync omits it and the greeter keeps its own font. That is the safe outcome: a synced family has to be resolvable by the `greeter` account through Fontconfig, and a family installed only in your home directory does not reach it |
| Monitor layout, transforms, scales | the session's effective per-output state | Skipped entirely if `greeter.toml` sets `[output] use_synced_settings = false` |

Two of the sixteen colours travel under names that no longer exist in the shell. The palette file says `mSurfaceVariant` and `mOutline`; the shell's runtime roles were renamed `surface_container` and `outline_variant` in 5.4.x; and Sync writes those two roles back out under the greeter's older names `surface_variant` and `outline` (`greeter_appearance_sync.cpp:466, :468`). The colour comes full circle, and `outline_variant` is the same role the lock panel's border uses — the login screen's outline and the lock screen's border are the same colour for the same reason.

**Auto-sync stays off.** Each sync elevates through `pkexec`, and the packaged polkit action `org.noctalia.greeter.sync-appearance` is `auth_admin` in all three states, so every sync prompts unless somebody installed a site-local passwordless rule for that account (`sudo noctalia-greeter passwordless-sync enable <user>`). This repository never runs that command — granting passwordless execution of a root helper is yours to decide, not a payload's — so `[shell.greeter_sync] auto_sync = true` would mean an authentication dialog on every wallpaper or palette change. A stale login screen is the smaller harm. The renderer refuses the key outright and says why, rather than claiming upstream has no such setting; `[shell.greeter_sync] privilege_command` is refused for a sharper reason, being a prefix the shell appends `--sync` to and runs as root.

For the prompt to appear at all, a polkit agent has to be running in the session, and one is: `.config/hypr/startup.lua:19` starts `polkit-gnome-authentication-agent-1`, replaced with `xfce-polkit` on Fedora. The shell's *own* agent (`[shell] polkit_agent`) stays off for that reason — two agents on one seat compete for the same request.

### What the login screen does not inherit

Recorded in `data/design/greeter.json` under `sync.excludes`, because each of these looks like it should follow the session and does not:

- **Motion, at all.** The greeter animates with five compiled-in easings — `Linear`, `EaseInCubic`, `EaseOutCubic`, `EaseInOutCubic` and an overshooting `EaseOutBack` (`src/render/animation/animation.h:7-13`) — and its config vocabulary is nine tables with no duration, easing or on/off switch among them. Reduce motion, the Performance intensity and every motion preset stop at the login screen. This is the one surface in the stack they cannot reach.
- **The clock's formats.** Sync does not carry `[shell] time_format` or `date_format`. This repository ships `{:%H:%M}` and `%a, %x`; the greeter's defaults are `{:%H:%M}` and `%A, %x`, so the time agrees and the weekday does not — abbreviated in the bar, spelled out at login.
- **The keyboard.** The greeter reads `XKB_DEFAULT_*`, then `/etc/default/keyboard`, `/etc/vconsole.conf`, `/etc/sysconfig/keyboard` and the xorg config (`system_keyboard_config.c:213-218`) — never Hyprland's `input {}`. `.config/hypr/inputs.lua` sets `kb_layout = "us"` and `numlock_by_default = true`, and neither reaches the login screen. Num Lock is the sharpest case: the compositor enables it *only* when `greeter.toml` says `numlock = true` (`noctalia_compositor.c:2176-2186`), even though `examples/greeter.toml` and `docs/user/input.md` both claim it defaults to on. A numeric keypad is therefore off at login and on in the session.
- **The cursor theme.** `[cursor] theme` wants the exact case-sensitive directory name — Arch's Breeze is `breeze_cursors`, not `Breeze` — and this repository's own cursor name is unverified on Fedora (`TP-18`), so guessing it would leave the login screen with a default cursor and no warning.
- **Idle.** The greeter blanks its own outputs on its own timer, `[idle] timeout`, which defaults to `0` — never — despite the example file showing 300. It is the third idle subsystem here after the shell's `[idle.behavior.*]` and the unlaunched `hypridle`, and it is the only one that ignores pointer movement: the countdown is polled every 2 s and mouse noise deliberately does not reset it (`noctalia_compositor.c:1177, :1232`), which is the opposite of the shell's pre-action fade.

Four places where the greeter's documentation disagrees with its code are written down in `doc_disagreements` — Num Lock's default, `[output] scale` below 1.0 being accepted and then dropped, `[idle] timeout`'s real default, and only one of the three position keys being validated at all. The record keeps the value the code honours each time, because a record that repeated the manual would be wrong in four places and look right in all of them.

## Security and desktop boundaries

The profile retains Noctalia's existing Settings and session integrations. The lock screen is the shell's own while the shell runs, with `.config/hypr/hyprlock.conf` as the fallback for a session where it does not; both authenticate through PAM, and neither collects a password on this project's behalf — [SECURITY.md](../SECURITY.md) records what that does and does not protect, including hyprlock's `SIGUSR1` unlock. The login screen is a fourth surface with its own compositor and its own PAM conversation through greetd, and this repository writes only `/etc/greetd/config.toml` and the mode of `/var/lib/noctalia-greeter` on it; [SECURITY.md](../SECURITY.md#the-login-screen) records both, plus why no `greeter.toml` ships and why no passwordless polkit rule is installed. Apple-specific AirDrop, iCloud, cellular toggles, and exact iOS app lifecycle have no direct universal desktop equivalent and are not emulated as fake working controls.

## Rollback

If the shell looks wrong after applying the profile:

1. Restore the timestamped backup made before copying.
2. Run `noctalia config validate` again.
3. Run `noctalia msg config-reload`, or log out and back into Hyprland if the shell cannot reload.

Do not delete the old configuration until the new one has passed live-session testing.
