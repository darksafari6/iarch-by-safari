# Shell motion helpers

The pure QtQuick motion primitives in `components/motion/` are:

- `HoverLift`, `PressSquish`, `SlideIn`, `ScaleIn` and `CrossFade`: wrappers
  that transform or fade caller-supplied content.
- `Stagger`: schedules a reveal by index and step duration.
- `ChamferReveal`: masks caller content with an angled animated reveal when shaders
  are enabled, and shows or hides it immediately in reduced-motion/low quality.
- `NumberRoll`, `RingSweep`, `SpectrumSmoothing` and `ShimmerLoading`: animate
  numeric displays, an assigned ring value, spectrum samples and a loading sheen.

They use the shared Theme durations and reduce or disable animation when
`reduceMotion` is enabled or quality is low. The mask rendering and pointer behavior are untested. Static qmllint passes in this sandbox; offscreen and live session
behavior remains UNTESTED-LIVE because the native Qt runtime libraries are absent.

The Theme quality policy retains the chosen level while game mode or low battery
temporarily selects low, restoring the preference when both clear. Blur, shadow,
shader, spectrum-rate and animation-scale recommendations are exposed as tokens.
Battery and game-mode inputs are wired to event-driven adapters but have not been
verified in a live session. These settings are not evidence of measured
performance. UNTESTED-LIVE.

Theme colour tokens have 300 ms Qt colour interpolation; low quality,
reduce-motion and explicit immediate requests set the duration to zero. Pack
transition effects and this interpolation are UNTESTED-LIVE.
