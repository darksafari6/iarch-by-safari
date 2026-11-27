# Dynamic shell components

The pure QtQuick components in `iarch/shell/components/` use the shared defaults
in `runtime/Theme.qml` and do not import shell-specific modules. Buttons expose
standard Qt Quick Controls click, keyboard focus and accessibility behavior;
`Segmented`, `CalendarMonth`, and `TodoList` emit selection signals rather than
running session commands. `CoverArt` only accepts local file URLs; it never
fetches an album image. `Spectrum` consumes supplied samples and does not run a
visualizer. See `docs/SHELL-SERVICES.md` for the model and service boundaries.

This library remains **in progress**: its theme runtime and motion helpers have not been verified in a live session. A pure QtQuick
gallery previews all component types. `scripts/iarch-shell.sh gallery` launches
an isolated preview with installed dynamic-pack choices through a validating
helper. It does not launch the session shell or own notifications. This preview
is UNTESTED-LIVE; its toolkit integration has only source-level verification. Styling is subject to future pack-token integration.
The current components pass Qt's QML static lint when that tool is available;
offscreen loads and live interaction remain UNTESTED-LIVE in this environment.

Four original upstream font binaries are vendored under `assets/fonts/`, with
unmodified OFL licenses beside them and pinned provenance in the generated
third-party notices. The Theme singleton attempts to load them from the repository
layout, prefers the requested available family and falls back to a bundled or system family. The development shell asset link resolves fonts and icons from the checkout; actual font loading and installed placement are UNTESTED-LIVE, and installer integration is still missing.

The Icon component accepts only names in its local allowlist, tints the bundled
SVGs with a Qt Quick effect and falls back to a caller-supplied glyph if an asset
is missing. The icon license and provenance are included in the notices. The
relative asset paths and effect rendering still require live installation testing.
