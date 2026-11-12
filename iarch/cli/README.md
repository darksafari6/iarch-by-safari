# iarch/cli — command line tools

Generators that are shipped and tested today. Each one reads the design tokens or
a preset, renders a configuration file, and can verify what it previously wrote:

| Command | Renders | Checks |
| :--- | :--- | :--- |
| `python3 iarch/cli/contrast_check.py` | nothing — it gates | that every preset clears 4.5:1 for text and 3:1 for non-text UI |
| `python3 iarch/cli/gen_wallpapers.py` | `assets/wallpapers/generated/*.webp` | that the shipped art is 4K, WebP, inside 600 KB and rendered by some preset |
| `python3 iarch/cli/gen_glass_lua.py` | `~/.config/hypr/generated/glass.lua` | that the committed default matches a fresh render of the tokens |
| `python3 iarch/cli/gen_animations_lua.py` | `~/.config/hypr/generated/animations.lua` | that the committed default matches a fresh render of the default intensity's motion preset |
| `python3 iarch/cli/gen_startup_lua.py` | `~/.config/hypr/startup.lua` | that the committed module matches a fresh render of `data/design/startup.json`, that every event it registers is one Hyprland dispatches, and that the two lines `install.sh` and `fedora_install.sh` rewrite with `sed` are each still in it exactly once |
| `python3 iarch/cli/render_noctalia.py` | `~/.config/noctalia/config.toml` and its palette | that the committed shell config and all six palettes match a fresh render |
| `python3 iarch/cli/render_hyprlock.py` | `~/.config/hypr/hyprlock.conf` and `~/.config/hypr/hypridle.conf` | that the committed lock screen and the unlaunched idle fallback match a fresh render, and that neither leaves the recorded surface |
| `python3 iarch/cli/render_gtk_css.py` | `~/.config/gtk-4.0/gtk.css` and `~/.config/gtk-3.0/gtk.css` | that the committed sheets match a fresh render of the tokens |
| `python3 iarch/cli/render_kvantum.py` | `~/.config/Kvantum/kvantum.kvconfig` and `~/.config/Kvantum/iarch/iarch.kvconfig` | that the committed theme matches a fresh render of the tokens |
| `python3 iarch/cli/gen_fontconfig.py` | `~/.config/fontconfig/fonts.conf` | that the committed file matches a fresh render of the tokens |
| `python3 iarch/cli/theme.py apply [PRESET]` | all of the above at once, under the live `~/.config`, from one preset and intensity | the contrast gate before it writes, then skips any file whose rendered bytes already match |
| `python3 iarch/cli/theme.py current` | nothing — it reports | which preset and intensity an `apply` would use, and where it would write |
| `python3 iarch/cli/iarch_anim.py list` | nothing — it reports | the five motion presets, how many events each animates, and which one is active |
| `python3 iarch/cli/iarch_anim.py set PRESET` | `~/.config/hypr/generated/animations.lua` | the render against the animation surface, then `luac -p`, then the compositor's own `configerrors` after a reload — and rolls the file back if that reports anything new |
| `python3 iarch/cli/iarch_anim.py speed N` | the same file | that `N` clamps into 0.5–2.0 and that the clamped value is what gets stored |
| `python3 iarch/cli/iarch_anim.py toggle EVENT` | the same file | that the event is one the active preset declares |
| `python3 iarch/cli/iarch_anim.py reduce-motion on\|off` | the same file | that reduce-motion renders the forced preset with every duration under the cap |
| `python3 iarch/cli/iarch_anim.py current [--live]` | nothing — it reports | the recorded state, the resolved per-event plan, whether the file matches it, and with `--live` what the compositor says it is animating with |
| `python3 iarch/cli/iarch_doctor.py notify-test` | nothing — it asks | that the shell answers IPC, that Do Not Disturb is off, that no other daemon holds the bus, and that low, normal and critical toasts are acknowledged |
| `python3 iarch/cli/iarch_doctor.py dnd on\|off\|toggle\|status` | nothing — it asks | that the shell took the change, by reading the state back |
| `python3 iarch/cli/iarch_gamemode.py on\|off\|toggle` | nothing of its own — it runs `theme.py apply` and `iarch_anim.py set` | that the four leaves the applied state decides are the four the compositor says it runs |
| `python3 iarch/cli/iarch_gamemode.py status` | nothing — it reports | the record against the settings against the session, and says which of the three disagrees |
| `python3 iarch/cli/iarch_focus.py on\|off\|toggle` | nothing at all — it writes no file | that Do Not Disturb read back as set, and that the two dim leaves read back as the tokens say |
| `python3 iarch/cli/iarch_focus.py status` | nothing — it reports | the record against the shell and the compositor now, which is how the drift a reload causes shows up |

Every command exits 0 on success, 1 when the repository or the host is out of
step — for `iarch-theme`, a preset the contrast gate refuses; for `iarch-anim`, a
render `luac` rejects or a config error the compositor reports after the reload —
and 2 on a usage or data error. None of them starts a desktop or edits a file it
did not generate. The per-surface generators never shell out; `iarch-theme` and
`iarch-anim` import their render functions and shell out only to ask the running
compositor and shell to reload, guarded so a missing binary is a warning rather
than a failure — and a warning that says the change is unverified, not that it
worked.

Six of them also refuse to write what the upstream project would not read.
`gen_glass_lua.py` checks every key against the Hyprland config leaves, which
error out on an unknown key. `gen_animations_lua.py` checks every leaf, curve and
style against `data/design/animations.json`, the animation tree read out of the
same release, because Hyprland refuses the whole config on an unknown leaf, an
unregistered curve or a style that leaf does not accept — and it derives every
`speed` as `duration_ms / 100` rather than picking a number by hand.
`render_noctalia.py` checks against
`data/design/noctalia.json`, extracted from the shell's own schema at a recorded
release, because that side is forgiving in the wrong direction: an unknown
setting only warns and is ignored, and an out-of-range number is clamped with a
warning, so a mistake there ships as a design that silently does not match the
tokens. `render_gtk_css.py` does the same against `data/design/gtk.json`, which
keeps the GTK 4 and GTK 3 surfaces apart because they are not the same language:
`backdrop-filter`, `filter`, `transform` and `@media` exist only in GTK 4, and
`transition-property` is checked against the properties GTK actually declares
animatable, since a shorthand there interpolates nothing. `render_kvantum.py` does
the same against `data/design/kvantum.json`, every key `ThemeConfig.cpp` reads at a
recorded release, because Kvantum is forgiving the same way: QSettings parses an
unknown key and the engine ignores it, and an integer outside its bound is clamped.
`gen_fontconfig.py` does the same against `data/design/fontconfig.json`, the
configuration DTD, because fontconfig warns about an element it does not know and
keeps loading, and a family no installed font provides is silently skipped.
A setting the pinned release really does declare, and that this project refuses to
emit, is not the same as a setting that does not exist, and `render_noctalia.py` no
longer says so: a section's `withheld` map carries the reason, the record that covers
it and the citation, so `shell.polkit_agent` and `shell.greeter_sync` are refused as
withheld on purpose rather than as keys Noctalia v5.4.1 never had. Both are recorded
in `data/design/greeter.json`, which is the one surface file in `data/design/` with no
generator behind it — the login screen's config is root-owned, wins over the shell's
own Sync for every key it sets, and is mostly facts about one machine.

`render_hyprlock.py` does the same against `data/design/hyprlock.json`, and
hyprlock is forgiving in the same direction as the shell: an unknown variable is a
warning and the lock screen still appears, so a misspelled `blur_passses` ships as
a lock screen with no blur and no error. The record covers hypridle's two blocks as
well, because that file is generated too — and because hyprlock's only published
specification is its manual page, the record names the page it was read from rather
than a release tag it did not fetch.
A render that does not
validate is refused before anything is written, and a write that fails part way
through puts every file back byte for byte. `iarch-theme apply` runs all six
renderers and the contrast gate before it writes anything, so one command is
refused if any single surface — or the palette's contrast — would be, and its
write across the nine files is all-or-nothing the same way. See
`docs/GTK-NOTES.md`, `docs/KVANTUM-NOTES.md` and `docs/FONTS.md`.

The two mode switches compose what already exists and add only the round trip:
read the state, record it, apply it, verify it, restore it. `iarch-gamemode`
applies `tokens.modes.game.intensity` — the `performance` intensity — and the
motion preset that intensity is already paired with, by calling
`iarch-theme apply --intensity performance --no-reload` and then
`iarch-anim set off`, so there is one reload and no second copy of the pairing. It
never touches `animation.reduce_motion`: with reduce-motion on, the motion half
renders `minimal` instead and the report says so, because a performance mode that
switched off an accessibility setting would be a bug wearing a feature's name.
`iarch-focus` writes no file at all — it asks the shell for Do Not Disturb and
caffeine and asks the compositor to dim every unfocused window at
`tokens.modes.focus.dim_strength`, which is Hyprland's own default for that leaf
handed back to it while this profile's intensities lower it to a whisper.

Both keep the honesty rules the rest of this directory keeps, and add two of their
own. A missing `hyprctl` or `noctalia` is a check that could not run, never a
pass and never a failure, and `getoption` answering `no such option` is quoted
rather than read as a value. A session that *was* asked and disagreed exits 1 and
leaves the files and the record alone: rolling back would put the disk in a third
state and leave both sides describing something nobody asked for. When one half of
a bundle refuses, the other half goes back to what this run found — not to the
saved restore point, which is the same thing the first time and a different thing
the second. And `iarch-focus status` compares the record with the session instead
of repeating the record, because focus mode is runtime state: any reload, relogin
or `iarch-theme apply` puts the intensity's own dim back, and a mode that could
not tell you that would be a mode you cannot trust.

`iarch-doctor` is the one command here that writes nothing at all: it asks a
running session what it is actually doing, because a render that validates is not
proof the desktop changed. It follows the same rule about a missing binary — no
`noctalia`, no `notify-send`, no `pgrep` means a check that could not run, which
is reported as such and never as a pass. The two mode switches read user state
through `iarch.lib.configstore` and share `iarch/lib/modes.py`, which owns the
compositor and shell calls, the `modes.<name>` record, and the vocabulary a report
uses — `matches`, `differs`, `unverified` — so the two cannot drift apart in what
they claim. The remaining commands are `iarch-keybinds` and the rest of
`iarch-doctor` (Part 5). Each one reads user state through
`iarch.lib.configstore` and writes only generated files, under the contract in
`iarch/lib/renderers.py`.

Nothing here may be renamed to an older product name; the conventions live in
`branding/product.env`.
