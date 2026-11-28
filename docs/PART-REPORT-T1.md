# Part T1 report — dynamic theme foundations

## Non-stop edition review — current status: PARTIAL

### Latest implementation work

The generic transaction journal now uses private files, syncs each write and
its parent directory before proceeding, and refuses world-readable, hardlinked
or unowned journal files. Tests include real process death during an operation
and during undo, followed by repeated recovery. Engine and handoff records now
also sync their containing directory after atomic replacement. Persistence of
newly created ancestor directories and filesystem-specific power-loss behavior
are not proven by these tests. This hardening does not wire the runner into
Classic or Dynamic apply, and the fault matrix is not complete.

The latest full Python discovery ran 2,482 tests with eight skips; all six shell
suites, shellcheck, bash syntax, generators, schema and workflow gates passed.
Dynamic selection is published after shell and compositor verification, and a
failed compositor verification restores the previous selection and requests the
previous Dynamic theme. Classic snapshots its choice and sound/settings targets
before writing the choice. The engine record now lives in the state directory;
legacy config records are read only until a state record exists, and are not
removed. Updates back up an existing state record and reject symlink targets.
An already-running engine is only recorded by the CLI after its notification
ownership is verified. These improvements are not a crash-recoverable apply.
Dynamic apply and rollback now refuse paths in Classic shell configuration,
including canonical paths through directory aliases. The common session lock has
an interprocess serialization test; journals exceeding the recovery size limit
are refused before their first operation.
`iarch/lib/theme_transaction.py` now provides a shared-lock step runner with
private journals, verification, reverse idempotent compensation, interrupted
transaction recovery, and fault-injection tests. It is infrastructure only:
Classic and Dynamic apply do not yet invoke it or supply recovery handlers.

A shared `shell-switch.lock` now serializes the main Classic and Dynamic theme
apply paths, Dynamic rollback and engine switching. Dynamic switching requires an
explicit `dynamic_engine_enabled: true` in `~/.config/iarch/dynamic-engine.json`,
but the separate unfinished-shell guard still prevents production startup.
`iarch/cli/shell_handoff.py` contains an injectable journalled notification
handoff with release and claim timeouts, recovery and fake fault tests;
`iarch-shell-switch to` now uses it and `iarch-shell-switch recover` can recover
its interrupted journal. CLI rollback uses a verified reverse handoff. The older
programmatic switch/rollback entry points still use their legacy flow, and the
old switch journal has a different schema. Bus behavior is UNTESTED-LIVE.
Notification history is not migrated. The requested shared crash-recoverable
Classic/Dynamic transaction runner, automatic engine switching during theme
apply and `iarch-theme recover` are not implemented. No completion is claimed.

### Earlier hardening

The engine probe now scopes toolkit PIDs to the named iArch configuration and
fails closed on ambiguous instance lists, so unrelated toolkit configurations
are not signalled. Switch preflight also refuses unknown or foreign notification
owners. These checks do not prevent later bus takeover, and remain UNTESTED-LIVE.
Dynamic apply and rollback now serialize with a shared advisory lock; the lock
only covers cooperating Dynamic operations, not Classic writers or external
editors. Malformed successful D-Bus owner replies are treated as unknown.

Latest verification: `python -m unittest discover -s tests -p 'test_*.py'`
ran 2,452 tests successfully, with eight skips. Shell syntax and warning-level
shellcheck, all six shell suites, the full generator/branding/naming/contrast
and schema/workflow checks passed. The schema check validated 49 documents against
35 schemas. These checks used fakes; no live compositor, session bus handoff or
Arch VM was available. No second version bump is made while tasks are partial.

The following review supersedes the historical snapshot below where they differ.
The foundations were merged previously (version 0.5.0); Part 2 work was later
merged experimentally and is still guarded. This review does not claim that the
Dynamic engine is ready, or that an Arch VM test was run.

| Task | Status | Evidence / remaining work |
| --- | --- | --- |
| 1. Engine strategy and switch | Partial | `docs/THEMES-ARCHITECTURE.md`, `iarch/cli/{shell_switch,engine_steps,iarch_doctor}.py` and fake-process tests. The switch now refuses unsearchable process tables and verifies that an engine has stopped before starting another, including manual and automatic rollback. Independently started processes and later notification-bus takeover are not prevented; live handoff remains UNTESTED-LIVE. Installer/Settings opt-in is not implemented. |
| 2. Pack format | Done | `data/schemas/theme-pack*.schema.json`, `data/themes/dynamic-reference/`; schema and bounded archive validation tests. Six actual packs are scheduled for Part 5. |
| 3. Repository layout | Done | `iarch/shell/`, `data/themes/`, `assets/sounds/`, `docs/themes/`; `tests/test_shell_layout.py`. Shell implementation remains experimental, not a completed Part 2. |
| 4. Theme CLI and atomic apply | Partial | `iarch/cli/theme_pack_{apply,archive,validate,preview}.py`, fake transaction and archive tests. The shell is blocked, so end-to-end live apply, complete app/cursor/font refresh, switch-sound and rollback cannot be established or claimed complete. Recovery itself can fail and is reported. |
| 5. State and records | Done | `theme_records.py`, `data/design/themes.json`, overrides schema and generated `docs/themes/STATUS.md`; record and drift tests. |
| 6. Legal/assets policy | Done | `docs/THEMES-ASSETS.md`, notices and licence checks. |
| 7. Milestones | Done | `docs/THEMES-MILESTONES.md`; no theme is claimed complete without parity QA. |
| 8. Tests and gates | Done, with live limitations | Full discovery: 2,443 tests, 7 skipped; six shell suites, bash syntax, warning-level shellcheck, generators, branding, naming, contrast, schema (49 documents/35 schemas), TOML and workflow sanity gates passed. Mock tests do not prove real session behaviour. |

**Acceptance:** documentation, schema, grouped listing and fake rollback tests
pass. Exactly-one-shell/notification ownership and a fully working dynamic apply
remain partial, not guaranteed. `IARCH_SHELL_SKELETON_NOT_READY` is retained.
The earlier Part 1 release already bumped `VERSION` and `CHANGELOG.md` to 0.5.0;
no second completion bump is made while these gaps remain.

**UNTESTED-LIVE / risks:** actual process identification and timing, D-Bus
notification ownership/handoff, Quickshell IPC acknowledgements, Hyprland reload,
application refresh and recovery, sound playback and an Arch VM install. See
`docs/UNVERIFIED.md` ENG-01–ENG-06 and ENG-09. Screenshot parity, actual theme
packs and installer integration belong to later milestones. Suggested commit
message: `fix: fail closed when switching shell engines`.

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

The Python suite passed 2,321 tests (five skipped). Shell syntax and shellcheck
gates, six shell test suites, generated-output checks, naming and branding
audits and the schema workflow step also passed offline. The schema workflow
validated 49 documents against 35 schemas. Transaction success and failure, archive safety, status drift,
selection migration and shell switching use fakes. No live Hyprland, Qt or
Quickshell session was available, so actual compositor parsing, shell IPC
argument and acknowledgement behavior, notification ownership, sound playback,
and live cursor/icon refresh remain **UNTESTED-LIVE**; see ENG-01 through ENG-06
in `docs/UNVERIFIED.md`. The runtime in this part cannot acknowledge an apply;
when it cannot be verified, apply fails closed and restores files. The switch
refuses the marked skeleton before stopping a working shell.

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
