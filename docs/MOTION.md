# Motion

How this desktop moves, what each surface can actually do, and how to check it on a
machine. Nothing here is a hope: every duration, curve, key and bound below was read
out of the release it belongs to, and what could not be read is listed at the end and
in [UNVERIFIED.md](UNVERIFIED.md) rather than described as though it worked.

Motion lives on three surfaces that do not share a vocabulary:

| Surface | Configured by | Vocabulary | Renderer |
| --- | --- | --- | --- |
| Hyprland — windows, workspaces, layers, fades, the focus glow | `~/.config/hypr/generated/animations.lua`, `glass.lua` | named bezier and spring curves, per-leaf `enabled`/`speed`/`curve`/`style` | `iarch/cli/gen_animations_lua.py`, `gen_glass_lua.py` |
| GTK 4 and GTK 3 — hover, press, focus | `~/.config/gtk-4.0/gtk.css`, `~/.config/gtk-3.0/gtk.css` | `transition-property`/`-duration`/`-timing-function` | `iarch/cli/render_gtk_css.py` |
| Noctalia — the shell's own panels, bar, launcher and notifications | `~/.config/noctalia/config.toml` | `[shell.animation] enabled` and `speed`, and nothing else | `iarch/cli/render_noctalia.py` |

One switch, `iarch-anim reduce-motion`, reaches all three. The multiplier reaches the
compositor today, and the shell's `speed` key is compatible with it but not yet wired
to it — see [Speed](#speed). The GTK sheets take their durations from the same tokens
the compositor does, so a preset change is not three separate edits.

## The five presets

`iarch-anim list` prints these with the number of events each animates. Every one of
them is a file in `data/design/animations/`, validated against
`data/schemas/animations_preset.schema.json`, and rendered only through values
`data/design/animations.json` records for Hyprland v0.57.2.

| Preset | Character | Window arrival | Window exit | Workspace switch | Fades |
| --- | --- | --- | --- | --- | --- |
| `smooth` | The default. Ease-out everywhere, no overshoot | 220 ms | 120 ms | 380 ms slide | 120 ms, except `fadeDim` at 220 |
| `snappy` | Same curves and styles, less time | 160 ms | 120 ms | 220 ms slide | 120 ms, except `fadeDim` at 160 |
| `bouncy` | Slight overshoot, but only where an overshoot is a position | 300 ms, ~6% past | 160 ms | 420 ms slide | 160 ms, except `fadeDim` at 240 |
| `minimal` | Fades only; seven events declared off | off | off | off | 90 ms, layer panels at 120 |
| `off` | The master switch. Hyprland warps every animated variable | none | none | none | none |

Arrival is longer than exit on purpose in every preset: a window opening is something
a person is waiting for, and a window closing is something they have already decided
on. `minimal` turns off `windows`, `windowsIn`, `windowsOut`, `windowsMove`,
`workspaces`, `specialWorkspace` and `borderangle`, and keeps `border` at 90 ms,
because the focus cue is the one thing worth animating when nothing else moves.

`borderangle` is the odd one out in the three full presets: 3000 ms on a `loop`
style, which is the animated border gradient turning slowly rather than an
interaction answering a click. It is the only event that is meant to be long.

`bouncy` puts its two overshoot curves on window arrival and on the workspace
switches and nowhere else, because those animate a position. On a fade the same curve
would drive an alpha past 1, and on the border a colour channel past its range, and
whether Hyprland clamps that before compositing was not read out of this release —
`tests/test_animation_presets.py` asserts the placement so the question stays
unanswerable rather than load-bearing. That is [MOT-04](UNVERIFIED.md).

`off` is what the Performance intensity and Game mode use. It is not a preset with
short durations: it emits `hl.config({ animations = { enabled = false } })` and no
leaves at all, and Hyprland's `AnimationManager` then warps every animated variable
straight to its final value, so there is no per-frame curve work to skip.

## Speed

`speed = duration_ms / 100`. That is not a convention this project chose: Hyprland
multiplies the configured speed by 100 to get milliseconds, so a larger number is
*slower*, and `iarch-anim speed` takes the reciprocal of what a person means by
"speed". The command therefore takes a **multiplier** and divides by it:

```
iarch-anim speed 2.0     # twice as fast: a 220 ms arrival becomes 110 ms
iarch-anim speed 0.5     # half as fast: it becomes 440 ms
iarch-anim speed 99      # clamped to 2.0, with a warning, and 2.0 is what is stored
```

The multiplier is clamped to `tokens.motion.animation.speed_multiplier` (0.5–2.0)
rather than refused, because a slider in Part 5 will be dragged past its ends and a
refusal there would read as a broken control. The clamped value is what gets
persisted and what gets rendered, so `current` never reports a number the render did
not use. Hyprland's own bound is wider — speed must be in `(0, 100]`, and a value
outside it is a hard config error, never clamped upstream — so the token bounds are
the project's choice and the upstream ones are the ones that cannot be crossed.

Noctalia's `[shell.animation] speed` has the **same polarity**: its own example
config says `0.5 = 2× slower, 2.0 = 2× faster`, and its accepted range is 0.1–4.0 in
steps of 0.05. So the same number means the same thing on both sides, and this
project's 0.5–2.0 sits inside Noctalia's range — one slider can drive both without
either going out of bounds.

That slider does not exist yet, and today the shell is written at `speed = 1.0`
whatever `iarch-anim speed` says. `render_noctalia.py` derives the value as
`MOTION_BASELINE_MS / motion.normal_ms` from the tokens alone, and that is
deliberate rather than an oversight: the committed `config.toml` has to be
reproducible from the repository with no user state in it, or the CI check that it
matches a fresh render would depend on whose machine ran it. Reading
`animation.speed` from `settings.json` belongs to the live render the Part 5
control-center slider performs, not to the renderer that produces the shipped
payload. Until then the honest summary is that the multiplier moves windows and
workspaces, and the shell's own panels animate at their compiled-in durations.

## Reduce motion

`iarch-anim reduce-motion on` is an accessibility switch, not a sixth preset. It does
three things and keeps one:

* it renders the preset `tokens.motion.animation.reduce_motion.preset` names
  (`minimal`), so reduce-motion means the same thing whatever was selected before;
* it caps every duration at `reduce_motion.max_duration_ms` (90 ms), applied *after*
  the multiplier so that slowing down cannot push a fade back over the ceiling;
* it zeroes every GTK transition in both sheets;
* and it leaves the selected preset recorded, so `reduce-motion off` gives it back.

The compositor and the toolkits get there by different routes, because they can:

* **GTK 4** answers the desktop's own `prefers-reduced-motion` media query, so it
  follows the system preference even when this project's switch is off. That block is
  a universal selector rather than a list of controls. It used to name twelve, and
  silently missed `spinbutton`, `.titlebar`, `listview > row` and all three menu-item
  selectors, so a person who asked for less motion still got a fading menu. A list
  cannot cover what gets added next; `*` can.
* **GTK 3 cannot parse `@media` at all** — its at-rule list stops at `binding-set`,
  `define-color`, `import` and `keyframes` — so the only lever is the sheet itself.
  `render_gtk_css.py --reduce-motion` renders every duration as 0 ms, and
  `iarch-theme apply` passes the recorded switch down to it.
* **Noctalia** has `[shell.animation] enabled`, which its own documentation
  describes as disabling all animated transitions globally. It follows the
  *intensity*: Performance writes `enabled = false`, so the shell's panels stop
  animating for the same reason the compositor's windows do. What it does not yet
  follow is `iarch-anim reduce-motion`, for the same reason the multiplier does not
  reach it — a user's settings cannot go into a payload that has to be reproducible
  from a clean clone. Both belong to the live render the Part 5 control-center
  slider performs.

Reduce-motion zeroes transitions and deliberately leaves `animation-duration` alone.
These sheets emit no keyframe animation at all, so every animation in a session
belongs to the application's own theme, and the common one is a spinner: freezing it
does not reduce motion so much as hide the fact that something is still working.

Because `iarch-theme apply` also renders `animations.lua`, it honours this switch on
the compositor side too and picks the forced preset. It honours *only* this switch:
the chosen preset, the multiplier and the per-event toggles belong to `iarch-anim`,
and a theme apply that overwrote them says so on stderr, naming each one. An
accessibility setting that a colour change could quietly revert is not a setting.

## Hover, press and focus

Every transition a GTK widget wears answers inside **120–180 ms**, and the whole
sheet uses one value — `tokens.motion.fast_ms`, 120 ms — so the band holds or fails
as a single decision instead of rule by rule. `motion.normal_ms` (220) and
`motion.slow_ms` (380) belong to the compositor, where a workspace slide has room to
breathe; a hover that took 380 ms would feel broken rather than calm.

What moves, and what does not:

| State | Property | Notes |
| --- | --- | --- |
| Hover | `background-color`, border colours | A fill change only. No transform, no scale |
| Press | `background-color`, `box-shadow`, `transform` (GTK 4) | The button sinks by 2%. GTK 3 has no `transform` property at all, so it answers with a darker fill rather than a fake one |
| Focus | `outline-color`, `outline-width`, and the window's inset `box-shadow` | The ring fades in. It used to snap: the ring was set by `:focus-visible` rules whose base rule transitioned only its fill |
| Window loses focus | `box-shadow` on `window.background` (GTK 4), `decoration` (GTK 3) | The hairline every window shares. GTK 3 puts the client-side decoration on a different node, and that node had no transition at all |

No transform is invented for a toolkit that cannot parse one. `transform` is in GTK
4's property list and absent from GTK 3's, and `data/design/gtk.json` records both
lists, so the renderer cannot emit a GTK 4-only property into a GTK 3 sheet.

On the compositor side the focus cue is Hyprland's **inner glow**, which this project
turns on and colours from the palette:

```
decoration:glow:enabled          # false upstream by default
decoration:glow:range            # integer 0..100
decoration:glow:render_power     # integer 1..4
decoration:glow:color            # the accent role, not a hex constant
decoration:glow:color_inactive   # the same role, much quieter
```

The glow needs no animation leaf of its own. Hyprland's inner-glow decoration
initialises its animations as `fadeGlow` and `glowangle` and then calls
`onWindowFocus()`, and `fadeGlow`'s parent in the animation tree is `fade` — which
every preset whose master switch is on sets — so the glow inherits a real duration
and curve. `tests/test_glass_lua.py` asserts that inheritance chain, because the
whole effect rests on it. The Performance intensity turns the glow off rather than
merely shrinking it: with motion off, every animated variable is warped, so the glow
would snap on instead of arriving, which reads as a flash and not as a cue.

## What Noctalia actually offers

Read out of Noctalia **v5.4.1**, which is what `data/design/noctalia.json` records
and what `render_noctalia.py` refuses to write past. The configurable surface is
smaller than it looks, and the honest list matters because the alternative is a
setting that silently does nothing.

**Configurable** — `[shell.animation]`, and this is the whole of it:

| Key | Type | Range | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | — | Disables all animated transitions globally. This project writes it from `intensity.motion.enabled` |
| `speed` | float | 0.1–4.0, step 0.05 | Scales durations globally; 2.0 is twice as fast. Written as `220 / motion.normal_ms`, so 1.0 for the shipped tokens |

Two keys. `shellAnimationSchema` in `src/config/schema/config_schema.cpp` declares
exactly those, so there is no per-event duration, no per-widget toggle, no hover
length and no easing choice to set from a config file.
[Shell settings](https://docs.noctalia.dev/noctalia/configuration/shell/) documents
both, and says plainly that `enabled` disables all animated transitions and `speed`
scales durations globally.

**Compiled in**, and therefore consistent but not adjustable:

* Durations come from `src/ui/style.h`: `animFast = 100`, `animNormal = 200`,
  `animSlow = 400` milliseconds. This project's own tokens are 120 / 220 / 380 —
  deliberately the same three-tier shape and within 20 ms of each tier, so a GTK
  window and a shell panel answer a click at about the same time.
* Hover and press are colour states, not movement. `Button::ButtonStateColors` has
  `hover` and `pressed` members, and the control animates between them over
  `animFast` with `Easing::EaseOutCubic`. There is no scale or translate on a shell
  button to configure, and nothing here claims one.
* The easing vocabulary is a closed enum of seven: `Linear`, `EaseInQuad`,
  `EaseOutQuad`, `EaseInOutQuad`, `EaseOutCubic`, `EaseInOutCubic`, `EaseOutBack`.
  `EaseOutBack` is the overshoot, and it is chosen in code per animation, not in
  config.
* An animation interpolates **one float** through a setter callback. That is why the
  shell's motion reads as fades and fills rather than as movement: there is no
  geometry interpolation in the manager to move a panel with.

**Deliberately exempt from the global switch.** `AnimationManager::animateTimer` is
documented in its own header as a real elapsed-time driver that *ignores* the global
motion enable and speed, for timeouts and for effects with a duration that must stay
independent — the wallpaper crossfade is the example it names. So
`iarch-anim speed 2.0` will not speed up a wallpaper change, and
`[shell.animation] enabled = false` will not stop one. That is upstream's decision,
not a bug here, and it is why the wallpaper duration is its own setting:
`[wallpaper] transition_duration`, 1500 ms by default, with eleven named transitions
(`fade`, `wipe`, `disc`, `stripes`, `zoom`, `honeycomb`, `vortex`, `pixel`,
`diamond`, `golden`, `melt`) and a separate `transition_on_startup`.
[Wallpaper](https://docs.noctalia.dev/noctalia/desktop/wallpaper/).

The lock screen has the same eleven transitions and its own `transition_duration`
(1500 ms) plus `edge_smoothness` (0.3), under
[Shell settings → Lock screen](https://docs.noctalia.dev/noctalia/configuration/shell/).
An empty `transition` disables the lock and unlock animation, which is how
reduce-motion should reach it in Part 7.

## Checking it on a machine

`iarch/cli/qa_motion.sh` is the manual QA walk-through. It is read-only unless asked,
and it separates what a shell can prove from what only a person can see:

```
./iarch/cli/qa_motion.sh                   # check what is checkable, print the rest
./iarch/cli/qa_motion.sh --walk            # pause at each visual step for y/n
./iarch/cli/qa_motion.sh --apply-switches  # also run the five-preset round-trip
IARCH_VERBOSE=1 ./iarch/cli/qa_motion.sh   # show the commands being run
```

It exits 1 if any check fails, and prints a tally of passed, failed, skipped and
still-to-look-at. **A missing binary is a SKIP, never a FAIL**: no `hyprctl` means
the compositor was not asked, not that it disagreed. The same rule the CLIs follow.

| Check | Expected |
| --- | --- |
| The three renderers' `--check` | The committed `animations.lua`, `glass.lua` and both GTK sheets match a fresh render of their source |
| The preset and generator suites | Every preset validates, and the generator refuses a leaf, curve, style or bound Hyprland does not have |
| `animations.lua` registers `iarch-` curves | Present, and it parses under `luac -p` when a Lua compiler exists |
| `glass.lua` carries a `glow` block | Present; the focus cue is the border plus the glow, not the border alone |
| GTK durations | Every transition is inside 120–180 ms, or 0 ms because reduce-motion is on. Anything else is a regression, and the script names the value |
| `hyprctl configerrors` | Empty, in a session |
| `hyprctl animations` | Reports `iarch-` curves, so the compositor loaded the render rather than the static default |
| Open and close a window | It arrives over roughly a fifth of a second and leaves faster than it arrived |
| Switch workspace | The two workspaces slide past each other rather than crossfading |
| Focus a window | The accent border changes and a faint glow fades in with it, instead of snapping |
| Hover a GTK button | The fill lightens within about an eighth of a second; nothing moves or scales |
| Press and hold it | It sinks by 2% under the pointer in GTK 4, and darkens in GTK 3 |
| Tab to the next control | The focus ring fades in rather than appearing at once |
| `reduce-motion on`, then open a window | Nothing slides and nothing overshoots; only short fades remain, each under 90 ms |
| `reduce-motion on`, then hover | The fill changes at once, with no fade |
| `reduce-motion off` | The preset you had chosen comes back, overshoot included |
| The `--apply-switches` round-trip | All five presets apply and your recorded preset is restored afterwards |

The acceptance test for the round-trip is that `iarch-anim set bouncy` followed by
`set off` both apply with `hyprctl configerrors` empty afterwards. What the script
cannot do is see a window arrive, which is why the visual steps are steps.

## Files

| File | Owns |
| --- | --- |
| `data/design/tokens.json` | `motion.fast_ms`/`normal_ms`/`slow_ms`, the four easings, the spring, the `animation` block, each intensity's `motion` and `glow` |
| `data/design/animations.json` | The Hyprland v0.57.2 surface: 34 leaves, their parents, per-leaf styles, builtin curves, and every numeric bound |
| `data/design/animations/*.json` | The five presets: named curves and per-event settings |
| `data/design/gtk.json` | What each GTK version parses, and which of those properties are animatable |
| `data/design/noctalia.json` | The shell settings that exist upstream, with their types and bounds |
| `iarch/cli/gen_animations_lua.py` | Preset → Lua, plus `resolve_modifiers`, the one place the clamp, the cap and the forced preset live |
| `iarch/cli/iarch_anim.py` | `iarch-anim`: switch, verify against the compositor, roll back |
| `iarch/cli/render_gtk_css.py` | The GTK sheets, their transition groups and the `--reduce-motion` render |
| `iarch/cli/gen_glass_lua.py` | The glow and the rest of the decoration block |
| `iarch/cli/qa_motion.sh` | The walk-through above |

## What is not verified

Five items in [UNVERIFIED.md](UNVERIFIED.md), each with the evidence that does exist
and the claim it blocks: [MOT-01](UNVERIFIED.md) the presets have never been rendered
where a window actually opens; [MOT-02](UNVERIFIED.md) whether a leaf set to
`enabled = false` really stops moving without affecting its parent or siblings;
[MOT-03](UNVERIFIED.md) how long a spring takes and how far it overshoots, since the
damping ratios quoted in the preset files are textbook arithmetic on the declared
stiffness, damping and mass rather than measurements of Hyprland's integrator;
[MOT-04](UNVERIFIED.md) whether an overshooting bezier is clamped when the value is
an opacity or a colour; and [MOT-05](UNVERIFIED.md) whether `hyprctl configerrors` is
empty in a stock session this project did not configure.

No duration, easing or effect in this document was chosen because it looked right in
a mockup and then written down. Where an effect is not supported it says so: GTK 3
gets no transform, the shell gets no per-event durations, and the wallpaper crossfade
ignores the global speed switch.
