# Shell services: current implementation and verification

Part 2 is in progress. The Python data models do not poll. A minimal read-only
status view connects clock, battery and network to the placeholder bar; the
sidebars expose system status and a todo count. Stats and other demand-driven
adapters run only while a surface that uses them is visible.
No service in this file should be presented as verified live in the shell yet.

| Module | Inputs | Outputs and failure behavior |
| --- | --- | --- |
| `iarch/shell/services/Compositor.qml` | Quickshell Hyprland events while active | Monitor, workspace and toplevel models, active window, and raw events; unavailable when no focused monitor. UNTESTED-LIVE. |
| `iarch/shell/services/Brightness.qml` | `brightnessctl` while active | Current backlight percentage and bounded absolute changes; at least one raw brightness unit is retained. Errors reported. UNTESTED-LIVE. |
| `iarch/shell/services/Media.qml` | MPRIS player list, active-only position timer | Preferred bus name, otherwise playing player, otherwise first by bus name; metadata, position and capability-checked controls. No remote art fetch. UNTESTED-LIVE. |
| `iarch/shell/services/Audio.qml` | PipeWire native nodes while active | Default sink/source and tracked stream nodes, bounded volume/mute requests for output, input and streams; missing or unready nodes are unavailable. Stream nodes are bound only while active. Requests are not acknowledgements. UNTESTED-LIVE. |
| `iarch/shell/services/GameMode.qml` | Existing settings record, watched locally | Restores preferred quality when game mode clears and enforces `animation.reduce_motion`; malformed fields retain their last valid values. UNTESTED-LIVE. |
| `iarch/shell/services/Battery.qml` | UPower aggregate device, event-driven | Availability, charge, state and times; low battery overrides quality without changing preference. UNTESTED-LIVE. |
| `iarch/shell/services/Network.qml` | Cached `nmcli` Wi-Fi listing and `/proc/net/dev` while active | SSID, signal and aggregate non-loopback rates; no active Wi-Fi scan. Bounded response validation rejects malformed samples. UNTESTED-LIVE. |
| `iarch/shell/services/Stats.qml` | Demand-driven local sample helper | CPU delta, memory, disk and thermal sample; missing sources are reported individually and malformed samples rejected. A minimal sidebar displays CPU status. UNTESTED-LIVE. |
| `iarch/shell/services/Clock.qml` | System clock while `active` | Localized date/time; its timer stops when no consumer is active. Connected to the placeholder bar; UNTESTED-LIVE. |
| `iarch/cli/shell_runtime.py` | A dynamic pack directory and validated user overrides | A copied token snapshot and per-surface visible state; invalid packs or unknown variants leave the previous snapshot intact. |
| `iarch/lib/shell_store.py` | Local JSON todo, timer and stopwatch state | Atomic, bounded writes; corrupt existing data is preserved and reported. |
| `iarch/lib/shell_data.py` | Synthetic or locally read CPU, memory, network, spectrum and media data | Parsed values, or `DataError` on malformed input; it never fetches album art or starts a process. |

The Python runtime uses the same versioned pack validator as the CLI. It can
produce a narrow projection checked by the QML runtime model. The guarded shell
now contains a two-phase theme IPC adapter: it prepares via the validating helper,
then commits only on an explicit matching request. It has not been exercised in
a live session. The guarded shell now has six lazy loaders with minimal placeholder windows and
a logical surface IPC adapter. They are not finished themed surfaces, and a
logical state acknowledgement is not proof that a compositor window appeared.
A one-shot selected-theme startup reader and colour interpolation are also
UNTESTED-LIVE. Fade and wipe overlays have been implemented, but their appearance and live behavior are unverified; visible consumer integration remains incomplete.

For development, `scripts/iarch-shell.sh preview` launches the shared core via
its separate `PreviewShell.qml` configuration using the bundled reference pack.
It does not switch the session engine, register a notification server, or reserve
compositor space. It may overlay existing windows; stop it with Ctrl+C in the
launching terminal. IPC instance selection and isolation are **UNTESTED-LIVE**;
do not issue shell IPC commands while another dynamic instance is running. This
preview is not a replacement for the guarded session shell.

The Quickshell source describes `IpcHandler` (`src/io/ipchandler.hpp`),
`Process` (`src/io/process.hpp`), and `StdioCollector` (`src/io/datastream.hpp`)
at the upstream `master` reference. This environment has no Quickshell or Qt QML
runtime, so none of those interfaces have been exercised here. Protocol and parser
assumptions that still need an authoritative versioned source are tracked as
ENG-07 in `docs/UNVERIFIED.md`. Live behavior remains UNTESTED-LIVE.

Notification history has a bounded, validated local storage model in
`iarch/lib/shell_store.py`, retaining the latest 200 entries and refusing to
overwrite corrupt files. An opt-in notification adapter can write and read it; image references are stored as data and are not fetched.

`python3 iarch/cli/shell_projection.py [id]` validates the selected or named
pack and overrides and emits a bounded JSON token/layout bundle for a future
bridge. The QML runtime checks the two narrow projections before replacing
state. The guarded, UNTESTED-LIVE IPC adapter invokes this helper with an
argument list and requires an explicit commit before changing theme state. The
helper does not write files, start services or acknowledge a live change.

## Performance budget

`iarch-shell perf [--json]` asks the toolkit for instances of the named session
configuration and samples their process CPU and resident memory over one second.
It rejects a sample if the PID was reused. A single sample does not demonstrate an
idle workload or balanced quality; an opt-in animation-frame interval is available when IPC works, but does not measure GPU rendering. The targets
are idle CPU below 3% and resident memory below 250 MiB at balanced quality.
Measured live values: **UNTESTED-LIVE** (no shell session was available).

The optional `quality` field in `~/.config/iarch/theme-overrides.json` accepts
`ultra`, `high`, `balanced`, `low`, or `null`; missing or null means balanced.
Existing overrides files without it remain valid. `iarch-shell quality` prints
the saved preference; `iarch-shell quality high` saves a new one and requests a
reload. A queued reload is not proof of live application. Use `--no-reload`
to save only, or `default` to return to balanced. Saving validates the whole
record, preserves other overrides, backs up the previous file and writes atomically.
An advisory lock serializes cooperating writers; external editors need to avoid
concurrent changes. The next validated theme load or reload reads the preference.
Game mode and low battery temporarily reduce the effective level without rewriting
it. The existing `settings.json` accessibility preference `animation.reduce_motion`
disables shell motion independently of the pack. The file-watcher and live reload
behavior are **UNTESTED-LIVE**.

### Experimental persistent and streaming services (UNTESTED-LIVE)

`Todo.qml`, `TimerService.qml`, and `Stopwatch.qml` call `shell_store_cli.py`
with bounded JSON on stdin and argv, never a shell command. Mutations are
serialized by a no-follow per-state-directory lock; state files are atomically
replaced with mode 0600. Corrupt state is refused, not overwritten. An explicit
`recover` request (or `LocalStore.recover()`) preserves a corrupt regular file
as a uniquely named `.corrupt-…` backup before atomically installing an empty
store; valid, missing, unreadable and symlinked files are not reset. The backup
retains its original permissions and may contain personal data. For example:
`printf '%s' '{"action":"recover"}' | python3 iarch/cli/shell_store_cli.py todo`.
The response includes the backup path. Recovery is never automatic. Timers use
wall-clock deadlines, so a clock adjustment changes their displayed time. Their
The placeholder left sidebar activates todo and displays a task count; timer
and stopwatch remain inactive until a consumer opts in.

`Notifications.qml` is an opt-in experimental notification-server adapter,
not a replacement for the running Classic server. It persists non-transient
notifications privately and serializes writers, bounds the queue and history,
and does not advertise image or action UI. It must not be enabled while Classic
owns the notification bus; ownership handover and rendering are untested.
`IARCH_ENABLE_NOTIFICATIONS=1` is a developer-only switch, not a readiness claim.

`Visualizer.qml` reads bounded-shape Cava raw ASCII frames with a dedicated
read-only configuration; it starts only while active, has a quiet synthetic
fallback and caps updates by the quality policy. Cava, PipeWire, process shutdown
and reduced-motion behavior need live testing. `Bluetooth.qml` uses Quickshell's
BlueZ model, does not scan automatically, and stops its requested scan on
inactivation. Its asynchronous setters are requests, not acknowledgements;
permission errors and device behavior remain unverified. APIs were checked
against Quickshell commit `9b0f339b19057f4731bf3b48293307d7ef241671` and
Cava commit `505cbf6dc19be0e0aaf082b5b35f1031102c5e97`, not against a live session.

### Sound, keyboard and idle (UNTESTED-LIVE)

`Sounds.qml` accepts only the three schema-defined events, queues one request
at a time and delegates validation to `shell_sound.py`. The helper validates
the selected pack and overrides, uses an argument list and a ten-second
playback timeout, tries `pw-play --volume` and falls back to `paplay` only when
`pw-play` is absent. Disabled events do not launch a player. A queued IPC
request is not a playback acknowledgement; `finished` reports the result.

`Keyboard.qml` observes layout change events and queries `hyprctl -j devices`
only while active. It limits queries and switches to five seconds and switches
only `current` with `next` or `prev`. It does not interpolate device names in a
command. `Idle.qml` exposes the compositor idle monitor and respects inhibitors;
it does not trigger lock, suspend or display power changes. Neither is active
by default or integrated with visible controls.

Checked against Quickshell commit `9b0f339b19057f4731bf3b48293307d7ef241671`
(`src/wayland/idle_notify/monitor.hpp`, `src/wayland/hyprland/ipc/connection.hpp`),
Hyprland v0.57.2 (`src/ipc/s1/Commands.cpp`, `hyprctl/src/Strings.hpp`) and
PipeWire 1.2.7 (`src/tools/pw-cat.c`). Real Wayland, IPC, player, timeout, and
inhibitor behavior must still be checked on the target session.

The `iarch.theme reload` IPC queues revalidation of the current theme and
commits only a fully validated bundle; failure retains the previous theme. Its
boolean response means queued, not successfully reloaded. It has not been
verified with a running IPC server.

`NightLight.qml` and `shell_night_light.py` query the local hyprsunset IPC on
demand; they do not start or configure the daemon, poll, or change gamma. The
only mutations are explicitly requested identity or a bounded integer
1000–20000 K. Responses are checked, with a five-second timeout per command.
The `profile` command is deliberately not used because the pinned source can
schedule its on-switch command when queried. Source: hyprsunset commit
`7d75ea30e905bc535372e49df16ead0f40bbd65f`, `src/IPCSocket.cpp`.
UNTESTED-LIVE; older installations may not support the identity query and will
report unavailable rather than assume a state.

### Capture and input requests (UNTESTED-LIVE)

`Screenshot.qml` offers explicit whole-screen and region requests. Its helper
uses `slurp` for an explicitly selected region and `grim` to write PNG data to
an already-open mode-0600 temporary file. It only publishes a successful image
under the private, user-owned state `captures` directory; failures and cancelled
selections remove the temporary file. `Recorder.qml` runs `wf-recorder` without
audio, only on request; stopping sends SIGINT and waits for finalization before
publishing a unique private file. A stop requested during startup is queued; a
startup timeout requests termination. The startup event only confirms that the
child was spawned, not that the compositor has begun delivering frames. There is
no automatic capture, upload, or microphone recording. Orphan/crash behavior and
the actual Wayland capture permission path remain untested.

`InputToggles.qml` lists compositor pointer names and only changes a specifically
selected existing pointer. `hl.device` requests are temporary and the response
means *requested*, not independently verified; identifying a touchpad correctly is
the caller's responsibility. Global `force_no_accel` is an explicit request and
may cause pointer desynchronization. No unchecked user string is inserted into
Lua. Hyprland 0.57.2 Lua config does not provide a normal `hyprctl keyword`
command; these fixed calls use `hyprctl eval` and check its textual reply.

Source pins: grim `47e2658619c6b5a790732c5876fb84e8273f08a9` (`grim.1.scd`),
slurp `a3998d3ec79fbd85b81911f43010466b032ed0d9` (`slurp.1.scd`), wf-recorder
`c5de47440e8e81c92befb696cb69819cdb3bfe8a` (`manpage/wf-recorder.1`,
`src/main.cpp`), Hyprland v0.57.2 (`src/ipc/s1/Commands.cpp` and
`src/config/lua/bindings/LuaBindingsConfigRules.cpp`).

The notification adapter can group its tracked notifications and invoke a
tracked action, but only advertises actions and images if a consumer explicitly
opts in. No current consumer does so. History is read on demand. Notification
bus ownership and interaction with the live notification client remain unverified.

`iarch-shell perf` may request a bounded opt-in Qt animation-frame interval
sample. This enables an animation driver for the sample, so CPU measured during
that sample is **not** an idle CPU measurement. The interval is not GPU render
time, and missing or malformed IPC data is reported as unavailable. The sampler
stops itself after three seconds. Neither sampling nor performance budgets have
been verified on a real desktop.

### Opt-in development setup and startup

`iarch-shell setup` creates `~/.config/quickshell/iarch` as a link to this
checkout only when that path is free (or already points to this checkout). It
refuses foreign files, foreign links and parent-directory escapes; it does not
start a process. `iarch-shell start` delegates to `iarch-shell-switch to dynamic`,
which still refuses the skeleton before stopping Classic. The switch launcher
passes the checkout path to the helper environment. `iarch-shell autostart`
prints a proposed user unit; `iarch-shell autostart --write` writes it atomically
with backup and refuses foreign files, but **never enables or starts it**. The
unit calls the same guarded launcher. Linking the source is a development setup,
not a substitute for the later installer; moving the checkout breaks the link.
The unit and session startup have not been exercised live.

The gallery includes the bundled reference pack via a preview-only validation
path; that pack remains reserved and cannot be selected or applied to a session.

The opt-in notification adapter checks the session-bus owner PID against
`Quickshell.processId` at startup and on explicit refresh. If the bus query is
unavailable, malformed, or belongs to another process, `available` is false.
This is a point-in-time observation, not a lease or handoff mechanism; ownership
may change later. Upstream server registration can retry after another server
exits, so this does **not** make it safe to run the adapter alongside Classic.
The guard and developer-only opt-in remain. UNTESTED-LIVE.
