# Part T2 — shell runtime and components plan

The user-provided Dynamic Themes prompt specifies Part 2 as the shell core,
services, pure QtQuick components, runtime, motion helpers, fonts, quality,
doctor, documentation and tests. It calls for completing this part before
starting later surfaces and themes. The existing Part T1 skeleton is not a
working shell and its safety marker must remain until readiness is established.

## Work still required

1. Implement the shell entry, validated IPC, opt-in launcher and lazy surface
   registry. Verify argument and reply types against the toolkit, and keep the
   one-shell/one-notification-server policy.
2. Implement the service adapters for audio, media, network, Bluetooth, battery,
   brightness, notifications, compositor, clock, todo, timer, stats, visualizer,
   sounds, keyboard, idle, screenshot, recorder, night light and input toggles.
   Stop polling when no dependent surface is visible.
3. Implement the requested pure QtQuick component library, gallery and motion
   helpers, including accessible and reduced-motion behavior.
4. Connect validated pack and override loading to the QML runtime, hot swap,
   registry and transitions; keep the previous theme on failure.
5. Provide licensed fonts and icons, quality and battery/game-mode policy,
   performance reporting, doctor checks and the requested documentation.
6. Run unit, QML lint and offscreen tests where tooling exists; record all
   live-session limitations and complete the Part T2 report, version and changelog
   only when the part is complete.

## Progress and safety

The validated Python runtime, local stores, parsers and colour lint have unit
tests. Thirty QtQuick components, the gallery and ten motion helpers pass static
QML lint, but offscreen and live rendering are unverified. The guarded shell now
contains a two-phase theme bridge, selected-theme startup loader, logical surface
IPC and six lazy placeholder windows; it does not yet provide complete surfaces.
Audio, media, brightness, battery, game mode, network and statistics adapters are
implemented but remain UNTESTED-LIVE; the remaining service adapters and wiring
are incomplete. The shell switch guard must remain. The isolated gallery has a
launcher and validated theme selector; it too is UNTESTED-LIVE. Source observations
and live verification gaps are in `docs/SHELL-SERVICES.md` and
`docs/UNVERIFIED.md` ENG-07 through ENG-16. This environment has static Qt QML
lint but no runnable Qt graphics libraries, Quickshell, compositor or session bus.
