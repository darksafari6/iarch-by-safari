# Part T2 report — INCOMPLETE

This report is a work-in-progress inventory, not a completion claim. The dynamic
session shell remains blocked by `IARCH_SHELL_SKELETON_NOT_READY`. Classic remains
the default. Do not remove the guard based on this report.

| Task | Status | Evidence and remaining work |
| --- | --- | --- |
| Shell core | Partial | `iarch/shell/shell.qml`, `services/ThemeBridge.qml`, `SurfaceIpc.qml`, `SurfaceHost.qml`, `StartupTheme.qml`. Six loaders use placeholder windows; guarded launcher and opt-in development setup/user-unit generator exist; production readiness and verified notification ownership remain missing. Reload and sound IPC are experimental. UNTESTED-LIVE. |
| Services | Partial | `services/Clock.qml`, `Stats.qml`, `Network.qml`, `Battery.qml`, `GameMode.qml`, `Audio.qml`, `Media.qml`, `Brightness.qml`, `Compositor.qml`; tested Python parsers/stores in `iarch/lib/shell_data.py` and `shell_store.py`. Sound, keyboard and idle adapters have since been added; capture, recorder and explicit input adapters now exist; visible-consumer wiring remains missing. Adapters are UNTESTED-LIVE. |
| Components and gallery | Partial | `components/`, `Gallery.qml`, `GalleryShell.qml`, `scripts/iarch-shell.sh gallery`; `tests/test_shell_components.py` and icon/font tests. All types are present but not all variants, accessibility/state behavior and installed gallery operation are verified. |
| Theme runtime | Partial | `runtime/Theme.qml`, `ThemeRuntime.qml`, `projection.js`, `registry.js`, `iarch/cli/shell_projection.py`; invalid projections are rejected, but shape, easing, surface motion, variant and sound metadata are now projected; fade/wipe/none transition overlays are implemented but not live-verified. Colour interpolation, startup and IPC are UNTESTED-LIVE. |
| Motion | Partial | Eleven helpers including `ChamferReveal.qml` and `docs/SHELL-MOTION.md`; reduced-motion, masking and live behavior remain unverified. |
| Fonts and icons | Partial | Four font files with OFL notices under `assets/fonts`, local SVGs with ISC/MIT notices under `assets/icons/shell`, generated notices and hash tests. Installed placement, fallback rendering and installer integration remain unverified or absent. |
| Quality/performance | Partial | `runtime/quality.js`, battery/game-mode inputs, `iarch-shell perf`; CPU/RSS and an opt-in Qt animation-frame interval are sampled; actual idle budgets and GPU rendering have not been measured. |
| Doctor/docs | Partial | `iarch-doctor shell` prerequisite checks, `docs/SHELL-SERVICES.md`, `docs/COMPONENTS.md`, `docs/SHELL-MOTION.md`, `docs/UNVERIFIED.md` ENG-07–ENG-21. Additional diagnostics and a final report are still required. |
| Tests and gates | Partial | Latest full Python suite: 2,434 tests passed, 8 skipped; 49 documents validated against 35 schemas. Component creation, theme swap and fake-I/O adapter/core harnesses also passed in a software-only Qt probe with synthetic GL/EGL/D-Bus stubs (not real graphics, D-Bus or Quickshell tests). Quickshell/compositor integration remains untested. All repository gates must be rerun after completing the part. |

**UNTESTED-LIVE:** all new Quickshell adapters, session startup, surface geometry,
notification ownership, theme switching/rollback, sound, game and battery
signals, installed asset paths, frame timing and performance budgets. This
sandbox has no Quickshell or compositor and lacks the native graphics libraries
needed for Qt offscreen tests. See the numbered verification entries above.

No Part 2 version bump or final changelog entry has been made. Suggested final
commit message once the remaining work and checks really are complete:
`feat: complete dynamic shell core and theme runtime`.

### Additional unfinished service work

Experimental private, locked notification history and todo/timer/stopwatch CLI
adapters, an opt-in notification server, a demand-driven Cava adapter with a
synthetic fallback, and an inactive BlueZ adapter have been added. None have
been verified in a Quickshell/Hyprland session; none completes the missing
surface integrations. Notification bus ownership in particular is not proven.
The dynamic entry point remains guarded, Part 2 remains **INCOMPLETE**, and
Part 3 has not been delivered.

### Latest Part 2 work

Added validated sound-event playback and IPC, event-driven keyboard state and
layout requests, opt-in idle and night-light adapters, theme reload queuing, expanded validated
shape/motion/variant/sound projections, and a chamfer reveal helper. Shell tests:
105 run, one skipped; Python-to-QML validation, pure-component qmllint, naming,
branding and QML-colour lints passed. These additions remain UNTESTED-LIVE.
The missing services, session startup and other gaps above still prevent claiming
completion or safely removing the guard.

### Additional services and preview

Added private explicit screenshot and no-audio recording helpers, temporary
input requests with fixed validated arguments, a calendar model, notification
grouping/history access, an opt-in frame interval sample, and a gallery-only
reference-pack preview. Pure surface styling now supports chamfers and gradient
or double borders. All Wayland, notification ownership and visual behavior are
UNTESTED-LIVE. These do not resolve session startup or other listed gaps.

### Latest checks

The full Python suite ran 2,434 tests with eight skips after the setup, transition,
gallery, store-recovery, status-view, isolated-preview, quality, sample-validation
and PipeWire stream-binding changes. The schema gate validated 49 documents
against 35 schemas. Shell scripts, shellcheck,
all six shell test suites, and generator and branding gates passed earlier. The unit generator is opt-in and does not enable or start a service.
The dynamic shell remains blocked: the missing live/session and safety evidence
listed above prevents a completion claim.

The notification adapter now has a point-in-time D-Bus owner-PID probe, but it
does not prevent bus takeover later and does not establish a safe handoff. The
readiness guard and developer-only server opt-in remain necessary.

Todo, timer and stopwatch stores now support explicit corruption recovery with a
preserved backup; valid and symlinked files are refused. The store helper and
recovery paths have unit tests, while the QML recovery signal is UNTESTED-LIVE.
A minimal read-only `SurfaceContent.qml` now displays status in the bar and
sidebars and activates its polling services only while their consumers are
visible. An explicit `iarch-shell preview` starts `PreviewShell.qml` with the
reference pack, without session switching, notifications or reserved screen
space. The windows are still placeholders, not the later finished surface
implementations; preview startup, IPC isolation, bindings and compositor behavior
remain UNTESTED-LIVE. The optional saved quality preference now survives theme
reloads, and the shell observes the existing reduce-motion setting; watcher and
live rendering behavior remain UNTESTED-LIVE. `iarch-shell quality` now provides
a validated, backed-up preference update and reports a reload as queued, not
applied. A software-only Qt object-creation probe exposed and fixed invalid
animations on read-only colour properties and a QML `onAccent` name collision.
It also checked that an animated update reaches its target and a rejected pack
preserves the previous colours and surface state. That probe used synthetic
GL/EGL/D-Bus stubs and is not evidence of native
rendering or a real session; the normal offscreen tests still skip without native
libraries. A separate QML harness now exercises theme IPC logic, preference and
store handling, and stats, network and brightness state transitions using fake
Quickshell I/O types. It verifies local logic only, not upstream API behavior.
The stats and network adapters now reject malformed or oversized samples. The
fake core harness also checks demand gating and preview isolation, recorder
startup queues early stop requests and has a timeout, and PipeWire stream nodes
are bound while active for volume and mute requests. Real recording, audio,
notification ownership and orphan handling are still UNTESTED-LIVE.

### Input and night-light request lifecycle

The experimental input and night-light adapters now time out stalled helpers,
report that a timed-out request may still have taken effect, ignore late exits,
limit helper response sizes, and queue a refresh when a consumer is hidden then
shown while a request is in flight. Pointer names are checked against the same
bounded safe character set as the Python helper. Tests exercised success and
late-exit timeout paths using QML test doubles and synthetic GL/EGL/D-Bus
libraries; this is not a real toolkit, compositor, graphics or bus test. The
adapters and timeout effects remain UNTESTED-LIVE.

### Audio input controls

The experimental PipeWire adapter exposes bounded microphone volume and mute
requests and rejects input and stream changes when PipeWire is not ready. The
QML mock harness checks those paths using synthetic graphics and bus libraries;
actual PipeWire behavior remains UNTESTED-LIVE.
