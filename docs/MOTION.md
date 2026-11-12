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

Game mode does not name that preset. `data/design/tokens.json` records
`modes.game.intensity = performance` and nothing else, and
`iarch/cli/iarch_gamemode.py` reads the preset through
`gen_animations_lua.preset_for_intensity`, which is the same function the renderer
uses and which refuses an intensity whose `motion.enabled` and `motion.preset`
disagree. One pairing, one reader, no second copy to drift.

Reduce-motion outranks game mode. With `animation.reduce_motion` on, the motion
half renders `minimal` rather than `off` — `iarch_anim._effective_preset` forces
it — and `iarch-gamemode` reports that instead of quietly switching an
accessibility setting off. The master switch it then checks is `minimal`'s, not
`off`'s, so the check follows the render rather than the intention.

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

The window switcher is the exception to "the shell's motion reads as fades". Its
cards animate **position, scale, opacity and pointer-hover lift** using the global
animation settings, and the selected card's shadow follows `[shell.shadow]` — so
`[shell.animation] enabled = false` freezes the carousel and `speed` scales it,
exactly as it does for a panel
([Shell → Window switcher](https://docs.noctalia.dev/noctalia/ipc/shell/)). This
project binds `Alt + Tab` to `noctalia msg window-switcher hold` and sets
`style = "carousel"` with `mru = true`; the movement is upstream's, and the
durations are its own 100/200/400 ms constants, not something a config file can
set.

One control-centre key is a motion key, and this project writes it from the same
switch: `[control_center.media] show_visualizer` is the only element in the panel
that moves continuously rather than in answer to something, so it follows
`intensity.motion.enabled` — on for crystal, frosted and soft, off for performance.
`tests/test_noctalia.py` asserts both values really occur, because a key that never
changes is a key that does nothing.

The shell's own lock screen is a motion surface with a surprise in it.
`[lockscreen] transition` is not a list of effects that play in order: the shell
picks **one of them at random** for every lock and unlock —
`std::floor(Random::randomFloat(0, transitions.size()))` at
`src/shell/lockscreen/lock_screen.cpp:1152` — and randomizes the chosen effect's
own parameters too, direction 0-3, centre 0.2-0.8, stripe count 4-24, angle
0-360, cell size 0.02-0.06 (`:1159-1176`). Upstream's struct default lists all
eleven (`config_types.h:602-607`), so an unconfigured session locks into a random
one of melt, vortex, honeycomb, pixel, golden and the rest, for 1500 ms each time.

This project therefore emits `transition = ["fade"]` — one named effect, the only
way to get a repeatable one — and derives the duration from the motion preset's
own `fadeIn` leaf. `kLockscreenTransitionDurationRange` is `{100, 30000, 100}`
(`src/config/schema/ranges.h:35`), a 100 ms step with a 100 ms floor, and neither
preset value is a multiple of it: smooth asks for 120 ms and minimal for 90 ms, so
both snap to the floor and the lock screen fades in 100 ms. That loss is recorded
in the key's note rather than hidden behind the shipped number. With motion off
the list is empty, which is how upstream disables the lock and unlock animation
entirely, and `blurred_desktop`, `blur_intensity` and `tint_intensity` follow the
intensity's blur switch.

`edge_smoothness` (0.3, upstream's default) feathers a transition's edge, so at
`transition = ["fade"]` it is stored and read and cannot change what is on screen
— a fade has no edge. It is emitted anyway, so the file states the value instead
of leaving it to change upstream. `blurred_desktop` needs
`zwlr_screencopy_manager_v1`, which the shell binds at version 3
(`src/wayland/wayland_connection.cpp:35, :84, :1706-1709`) and which Hyprland
v0.57.2 still ships (`src/protocols/Screencopy.cpp` in its own tree); a capture
that fails is warned about and skipped, not fatal.

The other lock screen this repository renders — `.config/hypr/hyprlock.conf`, for
a session where the shell is not running — animates through hyprlock's own
`animations` block, which takes the same preset's `fadeIn`/`fadeOut` durations in
seconds and has no speed multiplier to scale them. `general:compositor_fade`
fades the lock surface together with the compositor's blur contribution and
follows the same switch. Both are asserted against every intensity by
`tests/test_noctalia.py` and `tests/test_hyprlock.py`, and
`iarch/cli/qa_motion.sh` fails if the two files ever disagree with
`[shell.animation] enabled`.

The login screen is the one surface none of this reaches, and it is worth saying
so where the rest of the motion story is told. `greetd` starts
`noctalia-greeter-session`, which brings its own embedded wlroots compositor, so
no preset, no intensity and no reduce-motion setting applies there. The greeter
animates with five compiled-in easings — `Linear`, `EaseInCubic`, `EaseOutCubic`,
`EaseInOutCubic` and an overshooting `EaseOutBack` carrying the standard
1.70158 constant (`src/render/animation/animation.h:7-13` in noctalia-greeter
v1.7.0) — and its whole configuration vocabulary is nine tables with no
duration, easing, distance or on/off switch among them. There is no key to set
and no key to refuse, so `data/design/greeter.json` records the absence under
`motion` and `not_in_greeter` instead: a surface that cannot be tuned has to say
that as plainly as one that can.

One appearance value does cross over, and it is radius rather than motion: Sync
copies `[shell] corner_radius_scale` — this repository's derived
`radius.lg / radius.md`, 24 px over 16 px, so 1.5 — into the greeter's own
`corner_radius_scale`, which multiplies its base radii. The login screen's
corners therefore follow the same tokens as the panels, without this repository
writing a greeter file. Its clock formats do not cross over, so the weekday is
spelled out at login and abbreviated in the bar.

## Notifications

iArch runs no notification daemon of its own. Noctalia's built-in one is claimed
with `[notification] enable_daemon = true` in the generated `config.toml`, and
everything below is that daemon: its motion, its timeout rules, and the three
things the Part 3 brief asked for that v5.4.1 has no setting for.

**What moves, and how long it takes.** Read out of
`src/shell/notification/notification_toast.cpp` at v5.4.1:

| Effect | Duration | Easing | Call | Follows `[shell.animation]` |
| --- | --- | --- | --- | --- |
| Card reveal on arrival | `Style::animNormal` = 200 ms | `EaseOutCubic` | `animate()` at `:1073` | yes |
| Foreground slide inside the reveal | 12 px (`kContentSlideOffset`, `:110`) | — | same animation | yes |
| Cards re-stacking after a dismiss | 200 ms | `EaseInOutQuad` | `animate()` at `:1981` | yes |
| An arrival that interrupts a re-stack | retargets from the current reveal, 200 ms | `EaseOutCubic` | `animate()` at `:1959` | yes |
| Flash when a notification replaces one already on screen | `Style::animFast` = 100 ms | `EaseOutCubic` | `animate()` at `:846` | yes |
| The countdown bar draining | the toast's own timeout | `Linear` | `animateTimer()` at `:827` | **no, by design** |

Two consequences worth stating, because both are the opposite of what a reader
would assume:

* The toast animations go through `AnimationManager::animate()`, which honours the
  global motion enable and speed. So `[shell.animation] enabled = false` — what the
  `performance` intensity writes — stops toasts sliding as well as panels, and
  `speed` scales them. The wallpaper crossfade was the only exempt effect named
  earlier; the countdown bar is a second one, and for the same reason: a timer that
  has to agree with a real deadline cannot be scaled by a preference.
* There is no slide-in/slide-out pair to configure. The brief's ~300 ms in and
  ~200 ms out is not reachable in v5.4.1: one 200 ms reveal, one 200 ms re-stack,
  and a retract that reuses them. This document records the real numbers instead of
  pretending to set them.

**Hover pauses the timeout — always, and not through a setting.** Pointer-inside
calls `NotificationManager::pauseExpiry()` (`src/notification/notification_manager.cpp:762`),
which clears the expiry outright, and leaving calls `resumeExpiry(id, remainingMs)`
(`:781`) with what was left. No countdown timer is started while a card is hovered
(`notification_toast.cpp:824`), and focusing an inline reply input pauses it the same
way (`:1103`). There is no key to turn this off, so `iarch-doctor notify-test`
tells you to look for it rather than claiming to configure it.

**The progress bar is the timeout, and urgency decides whether it shows at all.**
`showToastProgressAccent()` (`:350`) draws the 3 px accent for any toast with a
deadline. A toast with none — `resolveDisplayDuration()` maps `timeout <= 0` to `-1`
(`:103`) — shows the bar full and static if it is critical, and hidden if it is not
(`:818`). Nothing here is configurable either.

**Urgency styling is real; urgency persistence is not.**

| Urgency | Border colour | Border width | Lifetime |
| --- | --- | --- | --- |
| low, normal | `[notification] border_color` (`outline_variant` as shipped) | `border_width`, 1.0 as shipped | the sender's timeout, or 6000 ms |
| critical | `ColorRole::Error`, ignoring `border_color` (`:127`) | at least `Style::emphasizedBorderWidth`, or `border_width` when that is larger (`:137`) | **the sender's timeout, or 6000 ms** |

`normalizeNotifyExpireTimeout()` (`src/notification/notification_manager.h:39`) maps
`0` to persistent and any negative value to `kDefaultNotificationTimeout = 6000`
**without looking at urgency**, so a critical toast that stays until it is dismissed
is a choice its application made, not something this theme can switch on. The two
levers that do exist are per sender, in `[notification.filter.<name>]`:
`override_duration` replaces the timeout for every toast from that sender, and
`allow_permanent = false` forces a sender's persistent toasts back to the standard
timeout. `border = false` removes the outline for every urgency including critical.
Both filter keys are recorded in `data/design/noctalia.json` and neither is emitted:
a filter needs a real application to match, and inventing one would ship a rule that
silently swallows somebody's notifications. `iarch-doctor notify-test` sends its
critical probe with `timeout_ms = 0` and says so in the body, which demonstrates the
one path that does keep a toast on screen without teaching anyone that urgency did it.

**Grouping, history and the corner it sits in.** What the shipped payload sets, and
why:

| Key | Value | Reason |
| --- | --- | --- |
| `position` | `top_right` | The bar's clock is centred and its session controls are right; toasts belong on the same side as the panel that lists them |
| `offset_x`, `offset_y` | 16, 16 | One margin on both axes. `offset_x` is split by `shell::surface_edge_inset::resolve()` (`src/shell/surface/edge_inset.h:15`) into a layer margin plus the card's own inner padding, so the painted edge lands 16 px out either way; `offset_y` is used verbatim as the layer margin (`notification_toast.cpp:521`). Whether that vertical margin is measured from the screen edge or from the bar above it is NOT-01 |
| `width` | 380 | Inside the 240–500 `kNotificationWidthRange`, and wide enough for three body lines at the shell's type scale |
| `background_opacity` | the intensity's `shell.notification_opacity` | 0.7 as shipped, so the compositor's blur shows through: this is a glass card, not a painted one |
| `border`, `border_color`, `border_width` | true, `outline_variant`, 1.0 | The same hairline every other floating surface carries, and a colour role so it follows the palette |
| `collapse_on_dismiss` | true | Dismissing one card slides the rest into a compact stack — the 200 ms re-stack above. `false` keeps stable slots instead |
| `max_visible` | 4 | Inside `Range{0, 20}`; 0 would fill the screen edge |
| `keep_dismissed_in_history`, `history_retention_hours` | true, 168 | A dismissed toast stays in the control-centre history for a week (upstream allows 0–8760, where 0 means forever) |
| `follow_focused_output`, `monitors` | false, `[]` | Toasts stay on the output they appeared on; an empty monitor list means every monitor |
| `layer` | `top` | Above normal windows. `overlay` would put them above fullscreen apps, which is a video call's worst moment |

Do Not Disturb has no config key at all in v5.4.1: `notification-dnd-set on|off`,
`notification-dnd-toggle` and `notification-dnd-status` are IPC verbs, and
`notificationSchema()` declares no schedule, no quiet hours and no exceptions. There
is therefore nothing to render and nothing to fake — `iarch-doctor dnd` wraps the
verbs, and anything that wants quiet hours has to call it. `[osd] kinds.dnd = true`
is the popup shown when the state changes, not the state. Sounds stay off through
`[audio] enable_notification_sounds = false`: the shell should not speak for
applications that already make their own noise.

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
| `iarch-doctor notify-test --dry-run` | Every probe builds and none is sent, Do Not Disturb is off, and no other notification daemon is in the process table. Suppression or a missing shell is a SKIP, never a FAIL |
| Run `iarch-doctor notify-test` for real | Three cards stack in the top-right corner, each revealing over 200 ms; hovering one pauses its countdown bar; the critical one keeps a red edge and stays until it is dismissed, because that probe asked for `timeout_ms = 0` |
| The `performance` intensity, then `notify-test` again | The same cards appear without sliding, since `[shell.animation] enabled = false` reaches the toast animations too — NOT-02 |
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
| `data/design/noctalia.json` | The shell settings that exist upstream, with their types and bounds — including `[lockscreen]` and `[idle]` |
| `data/design/hyprlock.json` | The hyprlock and hypridle variables, their types, defaults, enumerations and ranges |
| `data/design/greeter.json` | The login screen's surface, recorded and generated from by nothing: what Sync carries, what it cannot, and the four places the greeter's docs disagree with its code |
| `iarch/cli/gen_animations_lua.py` | Preset → Lua, plus `resolve_modifiers`, the one place the clamp, the cap and the forced preset live |
| `iarch/cli/iarch_anim.py` | `iarch-anim`: switch, verify against the compositor, roll back |
| `iarch/cli/render_gtk_css.py` | The GTK sheets, their transition groups and the `--reduce-motion` render |
| `iarch/cli/gen_glass_lua.py` | The glow and the rest of the decoration block |
| `iarch/cli/render_noctalia.py` | The shell's `config.toml`: `[shell.animation]`, every toast setting in the table above, `[lockscreen]` and `[idle]` |
| `iarch/cli/render_hyprlock.py` | The fallback lock screen and the unlaunched idle fallback: the intensity's blur recipe, and the preset's `fadeIn`/`fadeOut` in seconds |
| `iarch/cli/iarch_doctor.py` | `iarch-doctor notify-test` and `iarch-doctor dnd` — the only way to exercise any of this against a live session |
| `.config/noctalia/config.toml` | The shipped payload the two above render and CI checks |
| `.config/hypr/hyprlock.conf`, `.config/hypr/hypridle.conf` | The shipped fallback lock screen and the idle file that declares no timer |
| `iarch/cli/qa_motion.sh` | The walk-through above |

## What is not verified

Twenty items in [UNVERIFIED.md](UNVERIFIED.md), each with the evidence that does exist
and the claim it blocks. Five are about motion: [MOT-01](UNVERIFIED.md) the presets have
never been rendered where a window actually opens; [MOT-02](UNVERIFIED.md) whether a leaf set to
`enabled = false` really stops moving without affecting its parent or siblings;
[MOT-03](UNVERIFIED.md) how long a spring takes and how far it overshoots, since the
damping ratios quoted in the preset files are textbook arithmetic on the declared
stiffness, damping and mass rather than measurements of Hyprland's integrator;
[MOT-04](UNVERIFIED.md) whether an overshooting bezier is clamped when the value is
an opacity or a colour; and [MOT-05](UNVERIFIED.md) whether `hyprctl configerrors` is
empty in a stock session this project did not configure.

Five more are about notifications, and every one of them is a behaviour that has to be
watched rather than a value that can be checked: [NOT-01](UNVERIFIED.md) whether the
16 px `offset_y` is measured from the screen edge or from the bar that reserves its
exclusive zone above it; [NOT-02](UNVERIFIED.md) whether toast motion really follows
`[shell.animation]`, which the split between `animate()` and `animateTimer()` says it
should; [NOT-03](UNVERIFIED.md) hover-pause and the countdown accent as behaviour;
[NOT-04](UNVERIFIED.md) whether an installed `noctalia` accepts the JSON payload form
`iarch-doctor` sends, exercised here only against a fake shell on `PATH`; and
[NOT-05](UNVERIFIED.md) whether the seven process names in the competing-daemon check
are the ones that actually hold the bus.

Five more are about the two lock screens and the idle daemon, and they split the
same way: [LOCK-01](UNVERIFIED.md) whether a blurred desktop snapshot really
renders on Hyprland v0.57.2, where the protocol is verified in both source trees
and the gate that skips it when absent is verified, but no capture was ever taken;
[LOCK-02](UNVERIFIED.md) whether one named transition is really deterministic,
which is arithmetic on a verified `randomFloat(0, size)` rather than an
observation, and says nothing about the parameters that stay random;
[LOCK-03](UNVERIFIED.md) whether the resume command really brings the outputs
back, the spelling itself now settled from the compositor's own dispatch path
rather than from a manual that still documents a form v0.57.2 cannot compile; [LOCK-04](UNVERIFIED.md) whether hyprlock itself parses the
emitted file, which no hyprlock process has ever done here and which is recorded
against the current manual rather than a release tag; and
[LOCK-05](UNVERIFIED.md) whether the shell's `blur_intensity = 0.5` looks like the
intensity's blur recipe, which it is not claimed to — the multiplication by 40 px
is verified and no conversion to `decoration:blur:size` exists.

Five more are about the login screen, and none of them is a motion question —
which is itself the finding: [GRE-01](UNVERIFIED.md) whether a sync really
produces a login screen matching the session, where both halves of the
sixteen-colour contract are read out of source and no sync has ever run here;
[GRE-02](UNVERIFIED.md) whether the packaged polkit action really prompts on an
installed machine, the policy file being read at v1.7.0 while the installer pulls
the AUR `-git` build; [GRE-03](UNVERIFIED.md) the four places the greeter's
documentation disagrees with its code, each a code reading and none an
observation; [GRE-04](UNVERIFIED.md) whether the `-git` package is still the
release the record pins, `main` already carrying two `[clock]` keys v1.7.0 does
not have; and [GRE-05](UNVERIFIED.md) whether the state directory's mode is
already correct before an installer runs, two upstream paths agreeing on 0750 and
neither observed.

No duration, easing or effect in this document was chosen because it looked right in
a mockup and then written down. Where an effect is not supported it says so: GTK 3
gets no transform, the shell gets no per-event durations, the wallpaper crossfade
ignores the global speed switch, a toast has one 200 ms reveal rather than a
configurable in/out pair, hover-pause is unconditional and has no key, and no urgency
makes a notification persistent on its own, and the login screen has no motion
setting at all.
