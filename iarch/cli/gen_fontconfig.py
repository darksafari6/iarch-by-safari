#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the fontconfig half of the glass design system.

Writes ``~/.config/fontconfig/fonts.conf`` from the ``font`` block of
``data/design/tokens.json``: the user-interface face (Inter) becomes the
preferred ``sans-serif``, the terminal face (JetBrainsMono Nerd Font) becomes the
preferred ``monospace``, and the token's fallback chain -- Noto Sans, Noto Sans
CJK SC, Noto Naskh Arabic, Noto Nastaliq Urdu, Noto Color Emoji, DejaVu Sans --
is appended to both, so a glyph the primary face lacks (Han, Arabic, Urdu, emoji)
still resolves instead of falling through to whatever the system default happens
to be.

fontconfig is read by GTK, Qt and most other toolkits regardless of desktop, so
this is the distribution-agnostic way to apply the font tokens: it does not
depend on a settings.ini, a gsettings key or a portal, and it works the same on
Arch and Fedora. The tokens name upstream *family* names, not package names;
fontconfig selects a family only if a font providing it is installed, and skips
it silently if not, which is why the installer has to provide them
(docs/UNVERIFIED.md, TP-13 and TP-18).

Everything the file may say is verified against the fontconfig configuration DTD
and recorded in ``data/design/fontconfig.json``: the element vocabulary, each
element's attributes and their enumerated values. That matters because fontconfig
is *forgiving*: it warns about an element or attribute it does not know and keeps
loading, and a family that matches no installed font is simply never selected. A
typo therefore does not fail -- it silently drops a rule or degrades to a system
default. This renderer treats both as errors and refuses to write.

Usage:
    python3 iarch/cli/gen_fontconfig.py                     # write into the user config dir
    python3 iarch/cli/gen_fontconfig.py --print             # fonts.conf to stdout
    python3 iarch/cli/gen_fontconfig.py --write-repo-default  # refresh the shipped payload
    python3 iarch/cli/gen_fontconfig.py --check             # shipped payload matches a render
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "fontconfig.json"
REPO_CONF = ROOT / ".config" / "fontconfig" / "fonts.conf"

# The generic families fontconfig resolves through an alias. These are targets,
# not design tokens: the tokens name the real faces that fill them.
GENERICS = ("sans-serif", "monospace", "serif")


class FontconfigError(RuntimeError):
    """Raised when a render would write something fontconfig does not accept."""


# --------------------------------------------------------------- inputs


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FontconfigError(f"{label(path)}: {exc}") from exc


def load_tokens() -> Dict[str, Any]:
    return load_json(TOKENS_PATH)


def load_surface() -> Dict[str, Any]:
    return load_json(SURFACE_PATH)


def label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# --------------------------------------------------------------- the font map


def token_families(font: Dict[str, Any]) -> List[str]:
    """Every real family the tokens name, in precedence order, duplicates removed.

    The user-interface face leads, then the terminal face and the emoji face, then
    the fallback chain. ``ui_display`` is included because a heading that asks for
    it by name is a family the design system chose, even though it needs no generic
    alias of its own.
    """
    ordered = [font["ui"], font["ui_display"], font["mono"], font["emoji"]]
    ordered += [entry["family"] for entry in font["fallback"]]
    seen: List[str] = []
    for family in ordered:
        if family not in seen:
            seen.append(family)
    return seen


def fallback_chain(font: Dict[str, Any]) -> List[str]:
    """The fallback families, in the order the tokens list them."""
    return [entry["family"] for entry in font["fallback"]]


def aliases(font: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    """The generic families this file fills, and what each prefers, in order.

    ``sans-serif`` prefers the UI face, ``monospace`` the terminal face, and both
    then prefer the same fallback chain, so a glyph the primary face lacks still
    resolves. ``serif`` is deliberately left alone: the tokens name no serif face,
    and inventing one would ship a family the design system never chose.
    """
    chain = fallback_chain(font)
    return [
        ("sans-serif", [font["ui"], *chain]),
        ("monospace", [font["mono"], *chain]),
    ]


# --------------------------------------------------------------- emission


def provenance(tokens: Dict[str, Any], surface: Dict[str, Any]) -> str:
    version = surface["verified_against"]["version"]
    return "\n".join([
        "<!-- Source: the font block of data/design/tokens.json. -->",
        f"<!-- Element vocabulary and attribute values verified against fontconfig "
        f"{version}; see data/design/fontconfig.json. -->",
        "<!-- Edit the tokens, then run iarch-theme apply. A family fontconfig is "
        "given but no installed font provides is skipped, so the installer must "
        "supply them. -->",
    ])


def build_document(tokens: Dict[str, Any], surface: Dict[str, Any]) -> str:
    """The fonts.conf body: provenance comments, then the <fontconfig> root.

    No XML declaration and no DOCTYPE. A leading comment would stop an ``<?xml?>``
    being the declaration, so there is none, and fontconfig parses with a SAX
    handler that never loads an external DTD, so the DOCTYPE would be decoration
    it does not read. The root element is all it needs.
    """
    font = tokens["font"]
    lines: List[str] = [provenance(tokens, surface), "<fontconfig>"]
    for generic, families in aliases(font):
        lines.append('  <alias binding="strong">')
        lines.append(f"    <family>{escape(generic)}</family>")
        lines.append("    <prefer>")
        for family in families:
            lines.append(f"      <family>{escape(family)}</family>")
        lines.append("    </prefer>")
        lines.append("  </alias>")
    lines.append("</fontconfig>")
    # No trailing newline: write_generated adds exactly one.
    return "\n".join(lines)


# --------------------------------------------------------------- validation


def validate(text: str, tokens: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Refuse any element, attribute, enumerated value or family fontconfig would not honour."""
    problems: List[str] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [f"the rendered file is not well-formed XML: {exc}"]

    if root.tag != "fontconfig":
        problems.append(f"the root element is <{root.tag}>, not <fontconfig>")

    elements = surface["elements"]
    allowed_families = set(token_families(tokens["font"])) | set(GENERICS)

    for node in root.iter():
        if node.tag not in elements:
            problems.append(f"<{node.tag}> is not an element the fontconfig DTD declares")
            continue
        declared = elements[node.tag].get("attributes", {})
        for attr, value in node.attrib.items():
            if attr not in declared:
                problems.append(f"<{node.tag}> has no attribute {attr!r} in the DTD")
                continue
            enum = declared[attr].get("values")
            if enum and value not in enum:
                problems.append(f"<{node.tag} {attr}={value!r}> is not one of {enum}")
        if node.tag == "family":
            name = (node.text or "").strip()
            if name not in allowed_families:
                problems.append(f"<family>{name}</family> is not a family the tokens name "
                                f"or a fontconfig generic")
    return problems


# --------------------------------------------------------------- writing


def restore(path: Path, blob: Optional[bytes]) -> None:
    """Put a file back the way it was, atomically, during a rollback."""
    try:
        if blob is None:
            path.unlink(missing_ok=True)
            return
        handle = tempfile.NamedTemporaryFile("wb", dir=str(path.parent),
                                             prefix=f".{path.name}.", suffix=".rollback",
                                             delete=False)
        tmp = Path(handle.name)
        try:
            with handle:
                handle.write(blob)
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    except OSError:
        pass  # the backups in ~/.local/state/iarch/backups are the second net


def write_all(targets: Sequence[Tuple[Path, str]],
              env: Optional[Dict[str, str]] = None) -> List[Path]:
    """Write every file, or leave the filesystem exactly as it was."""
    saved: List[Tuple[Path, Optional[bytes]]] = []
    written: List[Path] = []
    try:
        for path, body in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            saved.append((path, path.read_bytes() if path.is_file() else None))
            written.append(configstore.write_generated(path, body, env))
    except BaseException:
        for path, blob in reversed(saved):
            restore(path, blob)
        raise
    return written


def targets_for(tokens: Dict[str, Any], surface: Dict[str, Any],
                root: Optional[Path] = None) -> List[Tuple[Path, str]]:
    base = root or (configstore.config_dir() / "fontconfig")
    body = build_document(tokens, surface)
    problems = validate(rendered_text(base / "fonts.conf", body), tokens, surface)
    if problems:
        raise FontconfigError("rendered fonts.conf is not valid for fontconfig "
                              f"{surface['verified_against']['version']}:\n  " + "\n  ".join(problems))
    return [(base / "fonts.conf", body)]


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated puts on disk for ``body``."""
    return f"{configstore.header_for(path)}\n{body}\n"


# --------------------------------------------------------------- CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the rendered fonts.conf to stdout")
    parser.add_argument("--write-repo-default", action="store_true",
                        help="refresh the shipped payload under .config/fontconfig/")
    parser.add_argument("--check", action="store_true",
                        help="verify the shipped payload matches a fresh render")
    parser.add_argument("--output-dir", type=Path,
                        help="write into this directory instead of the user config dir")
    args = parser.parse_args(argv)

    try:
        tokens = load_tokens()
        surface = load_surface()
        if args.to_stdout:
            body = build_document(tokens, surface)
            problems = validate(rendered_text(REPO_CONF, body), tokens, surface)
            if problems:
                raise FontconfigError("render is not valid:\n  " + "\n  ".join(problems))
            sys.stdout.write(body + "\n")
            return 0
        root = REPO_CONF.parent if (args.write_repo_default or args.check) else args.output_dir
        targets = targets_for(tokens, surface, root)
    except FontconfigError as exc:
        print(f"fontconfig: {exc}", file=sys.stderr)
        return 2

    if args.check:
        drifted = []
        for path, body in targets:
            expected = rendered_text(path, body)
            if not path.is_file():
                drifted.append(f"{label(path)} is missing")
            elif path.read_text(encoding="utf-8") != expected:
                drifted.append(f"{label(path)} does not match a fresh render")
        if drifted:
            for line in drifted:
                print(f"fontconfig: {line}", file=sys.stderr)
            print("fontconfig: run --write-repo-default", file=sys.stderr)
            return 1
        print(f"fontconfig: the shipped file matches a fresh render of the "
              f"fontconfig {surface['verified_against']['version']} surface")
        return 0

    try:
        written = write_all(targets)
    except (OSError, configstore.ConfigError) as exc:
        print(f"fontconfig: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"fontconfig: wrote {label(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
