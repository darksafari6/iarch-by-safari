# Part T1 report — dynamic theme foundations

## Phase A: repository findings

1. The existing default was the Classic shell and remains so until M5 QA.
2. Six Classic packs were flat JSON files, with a closed index.
3. The theme command already projected Classic packs across applications.
4. Existing generated files used atomic writes and rotating backups.
5. Motion switching already had a compositor error and rollback pattern.
6. No dynamic shell runtime was present in the checkout.
7. There were no shipped synthesized theme sounds.
8. The existing shell owns the session notification service.
9. JSON data and generated output are checked in the single CI workflow.
10. A live compositor, shell toolkit and session bus were unavailable in CI.

## Delivered

The engine catalogue, doctor check and shell switch encode the one-shell and
one-notification-server rule and a ten-second switch rollback. Versioned pack
schemas and a reference pack cover the manifest, palette, layout, motion,
sounds, compositor, application settings and data-only wallpaper recipes.
The validator refuses unknown keys, unsafe paths, links, executables and size
violations. Import and export use bounded archives; the reference pack is not
exposed for apply or export.

The theme CLI offers grouped listing, current selection, validation, archive
import/export, illustrative preview, dynamic apply and rollback. Dynamic apply
validates and renders first, snapshots files, signals the shell, reloads the
compositor, compares new config errors and restores on failure. Rollback uses a
persistent snapshot and attempts to restore the current state if verification of
the rollback fails. Classic selection files are migrated on write and user
overrides remain separate from read-only packs.

The catalogue of record generates `docs/themes/STATUS.md`. The shell tree is a
skeleton only; asset and milestone policies are in `docs/THEMES-ASSETS.md` and
`docs/THEMES-MILESTONES.md`. The six Dynamic themes are planned, not completed.

## Verification and limits

The Python suite passed 2,320 tests (five skipped). Shell syntax and shellcheck
gates, six shell test suites, generated-output checks, naming and branding
audits and the schema workflow step also passed offline. The schema workflow
validated 49 documents against 35 schemas. Transaction success and failure, archive safety, status drift,
selection migration and shell switching use fakes. No live Hyprland, Qt or
Quickshell session was available, so actual compositor parsing, shell IPC
argument and acknowledgement behavior, notification ownership, sound playback,
and live cursor/icon refresh remain **UNTESTED-LIVE**; see ENG-01 through ENG-06
in `docs/UNVERIFIED.md`. The runtime in this part cannot acknowledge an apply;
when it cannot be verified, apply fails closed and restores files.

Wallpaper recipes are validated but not rendered here. The generated preview is a
palette illustration, not screenshot parity. No actual theme sounds are bundled.
Dynamic surface rendering and shell hot swap belong to M1 and later; the six
screenshot-parity packs, full live system integration, installer selection and
Settings toggle remain later-milestone work. Runtime Qt style selection and live
icon/cursor changes have not been established; the shared projection writes
Kvantum colours and GtkSettings but does not claim all applications refresh.
These limits are not evidence that the dynamic engine has passed QA.

Dynamic pack validation requires the Python `jsonschema` package; previews
require Pillow. These dependencies must be present in the Python environment;
the installer does not yet provision them as part of this work.
