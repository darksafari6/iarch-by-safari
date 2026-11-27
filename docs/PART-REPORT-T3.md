# Part 3 report — INCOMPLETE

The dynamic entry point remains guarded; these foundations are not a working
shell or evidence that any surface is ready for use.

| Task | Status | Evidence and remaining work |
|---|---|---|
| Five bar variants | Not done | Pure workspace indicator/navigation helpers in `runtime/workspace_state.js`; variants, compositor actions and theme integration remain. |
| Workspace overview | Partial | `runtime/overview.js` calculates a 5×2 grid and clipped proportional window rectangles. Actual overlay, keyboard/pointer actions, compositor interaction and search remain. |
| Launcher | Partial | `iarch/lib/launcher_math.py`, `launcher_search.py`, `iarch/cli/shell_launcher.py`; bounded arithmetic and offline unit conversions, deterministic fuzzy ranking. Desktop-entry enumeration and execution, frequency persistence, clipboard, emoji, web/system commands and UI are not implemented. |
| Media dock | Not done | Existing Cava and MPRIS adapters are experimental and not a dock. |
| OSD/popups | Not done | No working surfaces. |
| Lock and idle | Not done | Existing Classic hyprlock is not a dynamic-theme fallback implementation. |
| Power menu | Not done | No menu, confirmation flow or shortcut wiring. |
| Layer/window rules | Not done | No generated per-surface rules. |
| Tests/docs | Partial | `test_launcher_logic.py`, `test_shell_overview_layout.py`, `test_shell_workspace_state.py`; no offscreen loads or live verification. |

All new geometry and launcher logic is isolated and does not invoke a shell,
execute arbitrary expressions, or launch applications. Unit tables are fixed and
local. A real graphical/compositor session is still required to verify all UI,
Hyprland actions and theme behavior. Suggested commit message only when this part
is complete: `feat(shell): implement shared dynamic surfaces`.

A pure `components/WorkspaceIndicator.qml` now supplies the three requested
styles and emits click, scroll and middle-click requests, but is not integrated
with a bar or compositor and is UNTESTED-LIVE. Its presence does not complete
Task 1. Full Python discovery after the initial foundations ran 2,394 tests
successfully with 17 skips in this environment; live/offscreen tests were not
available.
