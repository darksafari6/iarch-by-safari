#!/usr/bin/env python3
"""Enforce the iArch by Safari naming policy on everyday-UI surfaces.

The policy (docs/BRANDING.md): the desktop says "iArch by Safari". Upstream
project names and the previous product names are not shown to the user. Credit
lives in THIRD_PARTY_NOTICES.md and in Settings -> About -> Open-source
licenses, and accurate upstream names stay in documentation, installer code and
in the identifiers programs match on.

This tool extracts *display strings only* - keybind descriptions, the terminal
greeting, system-information labels, session menu entries, window titles and
what the runtime scripts print. It never scans whole files, so a command such
as `noctalia msg ...` or a path such as `~/.config/minimalinux` is not a
violation, while a label that says "minimaOS Control Center" is.

    python3 tools/branding_lint.py            # human report, exit 1 on findings
    python3 tools/branding_lint.py --json     # machine report
    python3 tools/branding_lint.py --surfaces # list what is scanned and what is not
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable, Dict, Iterable, List, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iarch_brand import product, repo_root  # noqa: E402

# Previous product names. Matched case-sensitively: the lowercase spellings are
# frozen runtime identifiers (paths, session names) and must keep working.
PREVIOUS_PRODUCT = ("minimaOS", "minimaLinux", "minimaDots", "MinimaLinux", "MinimaOS")
# Names of the upstream shell project. Banned only on product-level surfaces,
# where the product itself is speaking; allowed on identity-level surfaces such
# as diagnostics that probe the shell binary by name.
UPSTREAM_SHELL = ("Noctalia", "noctalia-shell", "Quickshell")

LEVELS: Dict[str, tuple] = {
    "product": PREVIOUS_PRODUCT + UPSTREAM_SHELL,
    "identity": PREVIOUS_PRODUCT,
}


# --- extractors: text -> display strings ---------------------------------

def lua_descriptions(text: str) -> List[str]:
    """`description = "..."` values of the Hyprland Lua configuration."""
    return re.findall(r'description\s*=\s*"((?:[^"\\]|\\.)*)"', text)


def fish_greeting(text: str) -> List[str]:
    return re.findall(r'fish_greeting\s+"((?:[^"\\]|\\.)*)"', text)


def fastfetch_display(text: str) -> List[str]:
    """Keys, formats and titles shown by the system information module.

    JSONC comments and trailing commas make this file unparseable as JSON, and
    a naive comment stripper would eat the `https://` in the schema URL, so the
    display fields are extracted directly.
    """
    return re.findall(r'"(?:key|format|title)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)


def toml_string_values(text: str) -> List[str]:
    """Every string value of the shell profile (labels, formats, font names)."""
    values: List[str] = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            values.append(node)

    try:
        walk(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return []
    return values


def desktop_display_fields(text: str) -> List[str]:
    """Name/Comment/GenericName/Keywords of a desktop entry, localized variants
    included. The `# Managed by ...` marker line is deliberately ignored: it is
    an ownership identifier, not a label."""
    found = []
    for line in text.splitlines():
        match = re.match(r"^(Name|Comment|GenericName|Keywords)(\[[^\]]+\])?\s*=\s*(.*)$", line.strip())
        if match:
            found.append(match.group(3))
    return found


def unescape(value: str) -> str:
    """Turn literal escape sequences from shell quoting into readable text."""
    return re.sub(r"\s+", " ", value.replace("\\n", " ").replace("\\t", " ")).strip()


def shell_printed_strings(text: str) -> List[str]:
    """Quoted arguments of echo/printf/info/warn/die lines in a shell script.

    Escape sequences are normalized so that a report quotes readable copy
    instead of a string full of backslashes.
    """
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if not re.match(r"^(echo|printf|info|warn|detail|heading|die|log_line)\b", stripped):
            continue
        found.extend(re.findall(r"'([^']*)'", stripped))
        found.extend(re.findall(r'"((?:[^"\\]|\\.)*)"', stripped))
    return [value for value in map(unescape, found) if value]


def gtk_ui_strings(text: str) -> List[str]:
    """Window titles, labels, markup and CLI help of the customization center."""
    found = []
    for line in text.splitlines():
        if not re.search(r"\b(title|label|markup|description|text)\b", line):
            continue
        found.extend(re.findall(r"'([^']*)'", line))
        found.extend(re.findall(r'"((?:[^"\\]|\\.)*)"', line))
    return found


class Surface(NamedTuple):
    """One everyday-UI surface: where to look, what to pull out, how strict.

    A NamedTuple rather than a dataclass so that the module can be loaded with
    importlib.util without being registered in sys.modules first.
    """

    surface_id: str
    pattern: str
    extract: Callable[[str], List[str]]
    level: str
    why: str


SURFACES: List[Surface] = (lambda: [
    Surface(
        "keybind-descriptions",
        ".config/hypr/**/*.lua",
        lua_descriptions,
        "product",
        "Shortcut labels are rendered by the shell and by the shortcut overlay.",
    ),
    Surface(
        "terminal-greeting",
        ".config/fish/config.fish",
        fish_greeting,
        "product",
        "Printed in every new terminal window.",
    ),
    Surface(
        "system-information",
        ".config/fastfetch/config.jsonc",
        fastfetch_display,
        "product",
        "Labels and formats printed on screen by the system information module.",
    ),
    Surface(
        "shell-profile-strings",
        ".config/noctalia/config.toml",
        toml_string_values,
        "identity",
        "String values of the shipped profile; keys are upstream identifiers and are not scanned.",
    ),
    Surface(
        "session-menu-entries",
        "session/*.desktop",
        desktop_display_fields,
        "product",
        "Shown in the display manager session list and in the application menu.",
    ),
    Surface(
        "runtime-script-output",
        "scripts/*.sh",
        shell_printed_strings,
        "identity",
        "What the runtime helpers print. Naming the shell binary they probe stays allowed.",
    ),
    Surface(
        "customization-center-ui",
        ".config/minimalinux/center.py",
        gtk_ui_strings,
        "product",
        "Window titles, labels and help text of the customization center.",
    ),
])()

# Surfaces that must not only avoid old names but must carry the product name.
REQUIRED: List[tuple] = [
    ("terminal-greeting", ".config/fish/config.fish", "IARCH_PRODUCT_NAME"),
    ("session-menu-entries", "session/minimalinux.desktop", "IARCH_PRODUCT_NAME"),
    ("runtime-script-output", "scripts/iarch-healthcheck.sh", "IARCH_PRODUCT_NAME"),
]

EXCLUDED: List[tuple] = [
    (".config/noctalia/plugins/**", "Vendored third-party plugin code; its own names are its own credit."),
    (".config/minimalinux/backend.py", "Frozen legacy generator: writes identifiers other programs match on."),
    (".config/hypr/*.conf, .config/hypr/themes/*.conf", "Legacy v4 payload; superseded by the Lua configuration."),
    (".config/kitty/minima-*.conf", "Generated by the frozen legacy appearance tool; internal include names."),
    ("session/minimalinux-session, session/minimalinux-customize", "Launcher scripts: paths and markers, no display strings."),
    ("install.sh, fedora_install.sh, legacy/legacy-install.sh, install-v4-session.sh, uninstall*.sh", "Installer code and review output, not the desktop UI."),
    ("tools/**, tests/**, lib/**", "Developer surfaces."),
    ("README.md, InstallNotes.md, docs/**", "Technical documentation: accurate upstream names are required here."),
    ("THIRD_PARTY_NOTICES.md, branding/notices.json", "The credit record itself."),
]


class Finding(NamedTuple):
    """A single naming violation, or a missing required product name."""

    surface_id: str
    path: str
    level: str
    token: str
    text: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "surface": self.surface_id,
            "path": self.path,
            "level": self.level,
            "token": self.token,
            "string": self.text,
        }


def surface_files(surface: Surface, root: Path) -> List[Path]:
    return sorted(p for p in root.glob(surface.pattern) if p.is_file())


def scan(root: Path | None = None) -> List[Finding]:
    """Return every naming violation found on the scanned surfaces."""
    root_path = root or repo_root()
    findings: List[Finding] = []
    values = product(root_path)
    product_name = values["IARCH_PRODUCT_NAME"]

    for surface in SURFACES:
        forbidden = LEVELS[surface.level]
        for path in surface_files(surface, root_path):
            text = path.read_text(encoding="utf-8", errors="replace")
            for extracted in surface.extract(text):
                for token in forbidden:
                    if token in extracted:
                        findings.append(
                            Finding(
                                surface.surface_id,
                                str(path.relative_to(root_path)),
                                surface.level,
                                token,
                                extracted,
                            )
                        )

    for surface_id, relative, key in REQUIRED:
        needle = values[key] if key.startswith("IARCH_") else key
        path = root_path / relative
        surface = next(s for s in SURFACES if s.surface_id == surface_id)
        if not path.is_file():
            findings.append(Finding(surface_id, relative, "required", needle, "<file missing>"))
            continue
        strings = surface.extract(path.read_text(encoding="utf-8", errors="replace"))
        if not any(needle in s for s in strings):
            findings.append(
                Finding(surface_id, relative, "required", needle, "no display string carries the product name")
            )
    return findings


def report(findings: Iterable[Finding]) -> str:
    findings = list(findings)
    lines = [f"branding lint: {len(findings)} finding(s)"]
    for finding in findings:
        lines.append(
            f"  [{finding.level}] {finding.path} ({finding.surface_id}): "
            f"{finding.token!r} in {finding.text!r}"
        )
    if not findings:
        lines.append("  everyday-UI surfaces are clean")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--surfaces", action="store_true", help="list scanned and excluded surfaces")
    args = parser.parse_args(argv)

    root = repo_root()
    if args.surfaces:
        print("Scanned surfaces (display strings only):")
        for surface in SURFACES:
            files = surface_files(surface, root)
            print(f"  {surface.surface_id:<26} {surface.pattern} [{surface.level}] - {len(files)} file(s)")
            print(f"      why: {surface.why}")
        print("\nNot scanned:")
        for pattern, reason in EXCLUDED:
            print(f"  {pattern}\n      why: {reason}")
        return 0

    findings = scan(root)
    if args.json:
        json.dump([f.as_dict() for f in findings], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
