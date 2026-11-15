#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""``Super+H``: the shortcut overlay.

What it draws, and from where
-----------------------------
The same record everything else is rendered from. ``data/keybinds.default.json``
plus your differences in ``~/.config/iarch/keybinds.json`` are merged by
``iarch_keybinds.merge`` -- the very function that renders the Lua the compositor
reads -- so the overlay cannot show a map the session does not have. Nothing is
scraped out of the generated file and nothing is transcribed here: a fourth
copy of the table is a fourth thing that can drift.

Rows are grouped by the record's own ``category``, in the order
``iarch_keybinds.categories_in_order`` gives, which is the order
``docs/SHORTCUTS.md`` and the Settings page use. Keys held but not bound --
reserved, or disabled -- get their own group at the end rather than being
dropped, because a person looking for ``Super+Shift+H`` and finding nothing
concludes the key is broken when it is only unassigned.

The colours are not chosen here. They are read out of the shipped
``midnight-glass`` preset, so the overlay is the same dark glass and the same
neon blue as the rest of the session, and a palette change reaches it without an
edit. ``palette()`` answers a colour per *role* and refuses a role the preset
does not define, which is what stops a hex value being invented here.

Where it draws
--------------
The bind fires with no terminal attached, so the first job is deciding where the
overlay can appear. ``draw_plan()`` answers an ordered list of candidates with the
reason each is or is not available, and every branch is testable without a
display: draw into the terminal this process already has, else open one of the
terminals the compositor's own emergency mode probes for -- in its order, so the
two fallbacks agree -- else ``notify-send``, else stderr and a non-zero exit. A
key that silently does nothing is how a safety net becomes a rumour.

It closes when you press ``q``, ``Q``, Escape or Enter, and when the terminal it
opened exits. ``--no-wait`` prints and leaves, which is what a pipe or a test
wants.

What is *not* built, said plainly
---------------------------------
This is a terminal overlay: real, working, and the reliable fallback the brief
asked for. The glass **window** overlay -- a layer-shell surface with a search
box you type into -- is not here, and the reason is specific rather than a
missing afternoon. The settings application draws from a ``PagePlan``, and a plan
row is deliberately unable to carry behaviour: ``pages/plan.py`` has no callback
field and ``Context.resolve`` only answers names from two written-down lists, so
a row that filtered a list as you typed cannot be expressed in it at all. Doing
it honestly means a page module inside ``iarch_settings`` with its own source
functions, which is the Part 7 work ``docs/ROADMAP.md:205-211`` describes and
``docs/UNVERIFIED.md`` carries as UI-02. Filtering is real here and now -- as
``--query``, in every rendering, tested -- it just is not driven by keystrokes
inside a glass window yet.

Nothing in this file was run on a session: there is no compositor, no display and
no terminal in the sandbox it was written in. The model, the grouping, the
filter, the palette, the rendering and the whole fallback decision are unit
tested; that a window actually opens is not, and is recorded as such.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.cli import iarch_keybinds as keybinds  # noqa: E402

#: The preset the overlay is tinted with. It is the shipped default profile, so the
#: overlay matches the session it appears in rather than picking its own colours.
PRESET = "midnight-glass"

#: The terminals to look for, in the order the compositor's own emergency mode looks
#: for them (Hyprland v0.57.2 ``src/config/lua/Emergency.hpp:5-10``, recorded in
#: ``data/design/keybinds.json -> recovery.emergency_mode``). Sharing the order means
#: the two fallbacks a session has disagree about nothing.
TERMINALS = ("kitty", "alacritty", "foot", "wezterm", "gnome-terminal", "xterm")

#: The heading for keys that are in the record but not bound to anything.
HELD = "Held but not bound"

#: What the overlay asks of the preset, as role -> the palette keys that may answer
#: it, most specific first. A role nothing answers is an error rather than a guess.
COLOR_ROLES: Dict[str, Tuple[str, ...]] = {
    "background": ("background",),
    "surface": ("surface",),
    "surface_variant": ("surface_variant",),
    "outline": ("outline", "outline_variant"),
    "text": ("on_background", "on_surface"),
    "text_dim": ("on_surface_variant", "text_disabled"),
    "accent": ("accent.primary", "primary"),
    "accent_soft": ("accent.secondary", "secondary"),
    "on_accent": ("on_accent.primary",),
}

RESET = "\x1b[0m"


# ----------------------------------------------------------------- the model


def overlay_rows(env: Optional[Dict[str, str]] = None,
                 root: Path = ROOT) -> List[Dict[str, Any]]:
    """Every entry the session actually has, merged, as flat rows.

    Merged by the same function that renders the Lua, so the overlay and the
    compositor are reading one map.
    """
    environment = dict(os.environ if env is None else env)
    defaults = keybinds.default_record(root)
    overrides = keybinds.user_overrides(environment)
    rows: List[Dict[str, Any]] = []
    for binding in keybinds.merge(defaults, overrides):
        action = binding.get("action") or {}
        bound = bool(binding.get("enabled")) and action.get("type") != "none"
        rows.append({
            "id": binding.get("id", ""),
            "keys": keybinds.key_string(binding),
            "description": (binding.get("description") or "").strip(),
            "category": (binding.get("category") or "").strip() or "Uncategorised",
            "bound": bound,
            "reserved": bool(binding.get("reserved")),
            "locked": bool(binding.get("locked")),
            "static": bool(binding.get("static")),
            "action": action.get("type", "none"),
            "detail": _action_detail(binding),
        })
    return rows


def _action_detail(binding: Dict[str, Any]) -> str:
    """One short phrase saying what the bind does, for the row's right-hand side."""
    action = binding.get("action") or {}
    kind = action.get("type")
    if kind == "dispatch":
        return str(action.get("dispatcher") or "").replace("hl.dsp.", "")
    if kind in ("exec", "shell"):
        command = action.get("command") or []
        return " ".join(str(part) for part in command)[:60]
    if kind == "noctalia":
        verb = action.get("verb") or ""
        args = action.get("args") or []
        return f"noctalia {verb} {' '.join(str(a) for a in args)}".strip()
    if kind == "lua":
        return "lua"
    if kind == "none":
        return "not bound"
    return str(kind or "")


def grouped(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows into categories, in the record's own order, held keys last."""
    order = keybinds.categories_in_order([{"category": r["category"], "enabled": True}
                                          for r in rows])
    seen = [c for c in order if any(r["category"] == c and r["bound"] for r in rows)]
    for row in rows:
        if row["bound"] and row["category"] not in seen:
            seen.append(row["category"])

    groups: List[Dict[str, Any]] = []
    for category in seen:
        members = [r for r in rows if r["bound"] and r["category"] == category]
        if members:
            groups.append({"category": category, "rows": members})
    held = [r for r in rows if not r["bound"]]
    if held:
        groups.append({"category": HELD, "rows": held})
    return groups


def key_tokens(keys: str) -> List[str]:
    """``SUPER + SHIFT + T`` as ``["super", "shift", "t"]``, case-folded."""
    return [part.strip().casefold() for part in str(keys).split("+") if part.strip()]


def matches(row: Dict[str, Any], terms: Sequence[str]) -> bool:
    """Whether every term matches the row, case-folded. Terms are anded, so a longer
    query narrows instead of widening.

    A term may match the key, the description, the category, the id or the action,
    which is what makes ``lock`` find the lock-screen bind and the locked ones alike.

    One rule is special and worth stating: **a single character has to be a key.**
    ``t`` matches a row whose key string contains a ``T`` token, and does not match
    every row whose description happens to contain the letter -- because on an
    overlay of keyboard shortcuts a lone character is the name of a key, not a search
    word. Without that, ``super t`` answers with most of the map, which is the one
    reply a cheatsheet must never give.
    """
    haystack = " ".join((row["keys"], row["description"], row["category"],
                         row["id"], row["detail"])).casefold()
    tokens = key_tokens(row["keys"])
    for term in terms:
        if len(term) == 1:
            if term not in tokens:
                return False
        elif term not in haystack:
            return False
    return True


def terms_of(query: str) -> List[str]:
    """A query into the terms ``matches`` ands together."""
    return [part.casefold() for part in str(query).split() if part.strip()]


def filter_groups(groups: Sequence[Dict[str, Any]],
                  query: str) -> List[Dict[str, Any]]:
    """The same shape, narrowed. A category with nothing left in it disappears."""
    terms = terms_of(query)
    if not terms:
        return [dict(group) for group in groups]
    kept: List[Dict[str, Any]] = []
    for group in groups:
        members = [row for row in group["rows"] if matches(row, terms)]
        if members:
            kept.append({"category": group["category"], "rows": members})
    return kept


# ---------------------------------------------------------------- the palette


def palette(root: Path = ROOT, preset: str = PRESET) -> Dict[str, str]:
    """A colour per role, read out of the shipped preset.

    Refuses rather than guesses: a role the preset does not define is a
    ``KeyError`` naming the role and the preset, because the alternative is a hex
    value somebody invented in this file, which is exactly how an overlay ends up
    a different blue from the session it floats over.
    """
    path = root / "data" / "design" / "presets" / f"{preset}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    colors = document.get("palette") or {}
    resolved: Dict[str, str] = {}
    for role, candidates in COLOR_ROLES.items():
        for name in candidates:
            value: Any = colors
            for part in name.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if isinstance(value, str) and value.startswith("#"):
                resolved[role] = value
                break
        else:
            raise KeyError(f"the {preset} preset defines no colour for the {role!r} "
                           f"role; looked for {', '.join(candidates)} in {path}. The "
                           "palette nests its accents under 'accent', so a candidate "
                           "is a dotted path")
    return resolved


def rgb(hex_color: str) -> Tuple[int, int, int]:
    """``#rrggbb`` as three ints, for a 24-bit ANSI escape."""
    text = hex_color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def fg(hex_color: str) -> str:
    red, green, blue = rgb(hex_color)
    return f"\x1b[38;2;{red};{green};{blue}m"


def bg(hex_color: str) -> str:
    red, green, blue = rgb(hex_color)
    return f"\x1b[48;2;{red};{green};{blue}m"


# ------------------------------------------------------------- the renderings


def render_text(groups: Sequence[Dict[str, Any]], *, colors: bool = True,
                query: str = "", paint: Optional[Dict[str, str]] = None,
                width: int = 78) -> str:
    """The overlay as text: dark glass, neon-blue keys, one block per category."""
    # Resolved only when it will be used: a plain-text overlay has no business
    # failing because a preset is missing a colour.
    tone = paint or (palette() if colors else {})
    accent = fg(tone["accent"]) if colors else ""
    soft = fg(tone["accent_soft"]) if colors else ""
    text = fg(tone["text"]) if colors else ""
    dim = fg(tone["text_dim"]) if colors else ""
    chip = (bg(tone["surface_variant"]) + fg(tone["accent"])) if colors else ""
    band = bg(tone["surface"]) if colors else ""
    rule_color = fg(tone["outline"]) if colors else ""
    end = RESET if colors else ""

    total = sum(len(group["rows"]) for group in groups)
    lines: List[str] = []
    rule = "─" * max(20, min(width, 78))
    lines.append(f"{accent}{band} iArch shortcuts {end}"
                 f"{dim}{band} {total} shown · {len(groups)} "
                 f"{'category' if len(groups) == 1 else 'categories'} {end}")
    shown = terms_of(query)
    hint = f"filter: {' '.join(shown)}" if shown else "filter: none"
    lines.append(f"{dim}{band} {hint} · q closes · Super+H opens {end}")
    lines.append(f"{rule_color}{rule}{end}")

    for group in groups:
        lines.append("")
        lines.append(f"{soft}{group['category'].upper()}{end}")
        widest = max((len(row["keys"]) for row in group["rows"]), default=0)
        for row in group["rows"]:
            key = row["keys"].ljust(widest)
            marks = []
            if row["locked"]:
                marks.append("locked")
            if row["static"]:
                marks.append("hand-written")
            if row["reserved"]:
                marks.append("reserved")
            tail = f"  {dim}({', '.join(marks)}){end}" if marks else ""
            detail = f" {dim}· {row['detail']}{end}" if row["detail"] else ""
            lines.append(f"  {chip} {key} {end}  {text}{row['description']}{end}"
                         f"{detail}{tail}")
    if not groups:
        # No count of the unfiltered map here: render_text is handed the narrowed
        # groups and cannot know what was filtered out, and a number it made up
        # would be wrong in the one place a person is already confused.
        lines.append("")
        lines.append(f"{dim}  Nothing matches {query!r}.{end}")
        lines.append(f"{dim}  Every term has to match. Drop one, or use a single "
                     f"letter for a key -- 't' is the T key, not the word.{end}")
    lines.append("")
    return "\n".join(lines)


def render_json(groups: Sequence[Dict[str, Any]], query: str = "") -> str:
    """The same overlay as data, for anything that would rather draw it itself."""
    return json.dumps({
        "query": query,
        "terms": terms_of(query),
        "categories": [
            {"category": group["category"],
             "rows": [{k: v for k, v in row.items()} for row in group["rows"]]}
            for group in groups
        ],
        "count": sum(len(group["rows"]) for group in groups),
        "source": "data/keybinds.default.json + ~/.config/iarch/keybinds.json",
    }, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------- where it can draw


def draw_plan(*, is_tty: bool, query: str = "",
              probe: Callable[[str], Optional[str]] = shutil.which,
              notify: bool = True) -> List[Tuple[str, str]]:
    """Where the overlay can appear, best first, each with the reason.

    A list rather than a decision, so the choice is inspectable -- ``--plan``
    prints it -- and so a test can ask what would happen on a machine with no
    terminal and no notification daemon instead of hoping.
    """
    plan: List[Tuple[str, str]] = []
    if is_tty:
        plan.append(("here", "this process already has a terminal to draw into"))
    for name in TERMINALS:
        found = probe(name)
        if found:
            plan.append((f"terminal:{name}",
                         f"{name} is installed at {found}, the same order the "
                         "compositor's emergency mode probes in"))
            break
    if notify and probe("notify-send"):
        plan.append(("notify", "notify-send can say the overlay could not open, "
                               "which is better than a key that does nothing"))
    plan.append(("stderr", "the last resort: say why on stderr and exit non-zero, "
                           "so the failure is visible in the compositor's log"))
    return plan


def terminal_command(terminal: str, self_argv: Sequence[str]) -> List[str]:
    """How to ask a terminal to run this overlay and keep it open.

    ``-e`` is the flag every terminal in :data:`TERMINALS` accepts for "run this
    command", and the command is passed as one argument list rather than a shell
    string, so a query with a space or a quote in it cannot become shell syntax.
    """
    return [terminal, "-e", *self_argv]


def notify_command(message: str) -> List[str]:
    return ["notify-send", "-a", "iArch", "iArch shortcuts", message]


def closing(reply: str) -> bool:
    """Whether what a person pressed means "close the overlay"."""
    return str(reply).strip().lower() in ("", "q", "quit", "exit", "\x1b")


# ------------------------------------------------------------------- the CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="iarch-cheatsheet",
        description="The Super+H shortcut overlay: every bind, grouped by category, "
                    "read from the same record the compositor's map is rendered from.")
    parser.add_argument("--query", "-q", default="",
                        help="narrow to rows matching every term, in the key, the "
                             "description, the category or the id")
    parser.add_argument("--json", action="store_true",
                        help="the overlay as data instead of as a drawing")
    parser.add_argument("--text", action="store_true",
                        help="draw here, in this terminal, and do not look for another")
    parser.add_argument("--plan", action="store_true",
                        help="print where the overlay would appear, and why, then stop")
    parser.add_argument("--no-color", action="store_true",
                        help="plain text, for a terminal without 24-bit colour or a pipe")
    parser.add_argument("--no-wait", action="store_true",
                        help="print and leave instead of waiting for q")
    parser.add_argument("--width", type=int, default=78,
                        help="the rule width to draw to (default 78)")
    parser.add_argument("--config-home", type=Path, default=None,
                        help="work against another home, which is what the tests use")
    args = parser.parse_args(list(argv) if argv is not None else None)

    env = dict(os.environ)
    if args.config_home is not None:
        env["HOME"] = str(args.config_home)
        env.pop("IARCH_CONFIG_DIR", None)

    try:
        rows = overlay_rows(env)
    except (OSError, ValueError, keybinds.configstore.ConfigError) as exc:
        print(f"iarch-cheatsheet: could not read the keyboard map: {exc}",
              file=sys.stderr)
        return 1
    groups = filter_groups(grouped(rows), args.query)

    if args.json:
        sys.stdout.write(render_json(groups, args.query))
        return 0

    is_tty = bool(sys.stdout.isatty())
    if args.plan:
        for kind, reason in draw_plan(is_tty=is_tty, query=args.query):
            print(f"{kind}\t{reason}")
        return 0

    painting = None if args.no_color else palette()
    if args.text or is_tty:
        sys.stdout.write(render_text(groups, colors=not args.no_color,
                                     query=args.query, paint=painting,
                                     width=args.width))
        if args.no_wait or not is_tty:
            return 0
        # Waiting is what makes this an overlay rather than a printout: q closes, and
        # anything else is read as a new filter and redrawn. Typing to narrow is the
        # one half of "searchable" a terminal can honestly do, and it needs no toolkit.
        prompt = (f"{fg(painting['accent'])}q closes · type to filter "
                  f"{RESET}") if painting else "q closes; type to filter: "
        current = args.query
        while True:
            try:
                reply = input(prompt)
            except (EOFError, KeyboardInterrupt):
                break
            if closing(reply):
                break
            current = reply
            groups = filter_groups(grouped(rows), current)
            sys.stdout.write(render_text(groups, colors=not args.no_color,
                                         query=current, paint=painting,
                                         width=args.width))
        return 0

    # No terminal here: this is the bind's case, so open one, or say why we could not.
    for kind, reason in draw_plan(is_tty=False, query=args.query):
        if kind.startswith("terminal:"):
            terminal = kind.split(":", 1)[1]
            command = terminal_command(
                terminal, [sys.executable or "python3", str(Path(__file__).resolve()),
                           "--text", "--query", args.query])
            print(f"iarch-cheatsheet: opening {terminal} ({reason})", file=sys.stderr)
            return _spawn(command)
        if kind == "notify":
            message = ("the shortcut overlay needs a terminal and none is installed; "
                       f"run 'iarch-cheatsheet --text' from one. ({args.query or 'no filter'})")
            return _spawn(notify_command(message))
    print("iarch-cheatsheet: no terminal and no notification daemon, so the overlay "
          "cannot appear. Run 'iarch-cheatsheet --text' from a terminal, or install "
          f"one of {', '.join(TERMINALS)}.", file=sys.stderr)
    return 1


def _spawn(command: Sequence[str]) -> int:
    """Start a command the overlay decided on, without waiting for it.

    Not waited on, and that is deliberate twice over. A terminal running the overlay
    is waiting for a person to press q, so a timeout would close the overlay out from
    under them; and this path is reached from a bind, whose exec should hand the
    window to the compositor and return rather than hold the key down. Only the
    failure to start is reported, because that is the only part this process knows.
    """
    import subprocess  # noqa: PLC0415  late: only the drawing path needs it

    try:
        subprocess.Popen(list(command), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print(f"iarch-cheatsheet: could not start {command[0]}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
