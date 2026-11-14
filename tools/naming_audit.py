#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Audit the repository for previous product names and the upstream shell name.

`tools/branding_lint.py` answers "does a person see an old name on screen?".
This answers the wider question the acceptance check asks: after excluding
`.git/`, `legacy/`, `THIRD_PARTY_NOTICES.md` and `LICENSE.txt`, where do the old
tokens still appear, and is every one of those places intentional?

Every surviving occurrence must belong to an allowlisted file with a stated
reason. A new hit in a file that is not on the list fails, and an allowlist entry
that no longer matches anything also fails, so the list cannot rot.

    python3 tools/naming_audit.py --check   # CI: only allowlisted files match
    python3 tools/naming_audit.py --report  # print every hit with its reason
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Previous product names, in every capitalisation seen in the history, plus the
# upstream shell's own repository name (the product is not that project).
TOKENS = ("minimalinux", "minimadots", "minimaos", "noctalia-shell")

# Never scanned: version control, the frozen v4 payload (its identifiers are the
# point of keeping it), the generated credit file and the license text, both of
# which must name upstream projects and earlier publications accurately.
EXCLUDED_PATHS = ("THIRD_PARTY_NOTICES.md", "LICENSE.txt")
EXCLUDED_DIRS = {".git", "legacy", "__pycache__", ".venv", "venv"}
BINARY_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".wav",
                   ".mp4", ".zip", ".tar", ".gz", ".zst", ".icon", ".woff", ".woff2"}

FROZEN = "frozen runtime identifier another program matches on"
POLICY = "defines or enforces the naming policy"
PROVENANCE = "credits the earlier publication this repository grew out of"
HISTORY = "historical document, banner-marked as not current"
TEST = "test asserting the frozen identifier stays frozen"

ALLOWLIST: Dict[str, str] = {
    # --- Frozen runtime identifiers -------------------------------------
    ".config/kitty/kitty.conf": FROZEN + " (includes minima-colors.conf and minima-profile.conf)",
    ".config/kitty/minima-colors.conf": FROZEN + " (generated include name; renaming orphans installs)",
    ".config/kitty/minima-profile.conf": FROZEN + " (generated include name; renaming orphans installs)",
    "lib/managed-files.sh": FROZEN + " (the '# Managed by minimaLinux session installer' marker)",
    "tools/diagnose.py": FROZEN + " (~/.config/minimalinux of the legacy session)",
    "tools/glass_preset.py": FROZEN + " (~/.config/minimalinux of the legacy session)",
    "tools/preflight.py": FROZEN + " (~/.config/minimalinux of the legacy session)",
    "tools/recover_session.py": FROZEN + " (~/.config/minimalinux of the legacy session)",
    "data/design/greeter.json": FROZEN + " (records that the login screen can select the legacy "
                                "session by its desktop entry name, and cites the file by path)",
    "data/design/autostart.json": FROZEN + " (the autostart record cites this repository's own "
                                  "shipped desktop entries under legacy/session/ as the evidence "
                                  "for the keys it writes and for the ownership marker, and those "
                                  "file names are the frozen ones)",
    # --- Policy and enforcement -----------------------------------------
    "branding/product.env": POLICY,
    "tools/branding_lint.py": POLICY,
    "tools/naming_audit.py": POLICY + " (this file lists the tokens it looks for)",
    "docs/BRANDING.md": POLICY,
    "CONTRIBUTING.md": POLICY + " (tells contributors not to rename them)",
    "docs/ARCHITECTURE.md": POLICY + " (documents the frozen identifiers and the two payloads)",
    "docs/UNVERIFIED.md": POLICY + " (verification rows quote the frozen paths)",
    ".github/workflows/iarch-checks.yml": POLICY + " (checks the legacy launchers exist)",
    # --- Provenance ------------------------------------------------------
    "branding/notices.json": PROVENANCE,
    "data/licenses.json": PROVENANCE + " (rendered from branding/notices.json)",
    "README.md": PROVENANCE + " (one sentence in Credits & License)",
    # --- Historical documents -------------------------------------------
    "docs/AUDIT.md": HISTORY,
    "docs/STATUS-2.0.md": HISTORY,
    "docs/V5-PORT-STATUS.md": HISTORY,
    # --- Tests that keep the identifiers frozen --------------------------
    "tests/managed-files.sh": TEST,
    "tests/session-install.sh": TEST,
    "tests/test_branding.py": TEST,
    "tests/test_branding_lint.py": TEST,
    "tests/test_customization.py": TEST,
    "tests/test_diagnostics.py": TEST,
    "tests/test_glass_preset.py": TEST,
    "tests/test_installer_cli.py": TEST,
    "tests/test_licenses_data.py": TEST,
    "tests/test_naming_audit.py": TEST,
    "tests/test_recovery.py": TEST,
    "tests/test_shortcuts_doc.py": TEST,
    "tests/test_v5_staging.py": TEST,
}


def scanned_files(root: Path = ROOT) -> List[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if relative in EXCLUDED_PATHS or path.suffix in BINARY_SUFFIXES:
            continue
        files.append(path)
    return files


def hits(root: Path = ROOT) -> List[Tuple[str, int, str, str]]:
    """(relative path, line number, token, line) for every occurrence."""
    found = []
    for path in scanned_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            for token in TOKENS:
                if token in lowered:
                    found.append((path.relative_to(root).as_posix(), number, token, line.strip()))
    return found


def audit(root: Path = ROOT) -> Tuple[List[Tuple[str, int, str, str]], List[str], List[str]]:
    """Return (all hits, unexpected files, stale allowlist entries)."""
    found = hits(root)
    matched_files = {relative for relative, _, _, _ in found}
    unexpected = sorted(matched_files - set(ALLOWLIST))
    stale = sorted(path for path in ALLOWLIST
                   if path not in matched_files and (root / path).is_file())
    missing = sorted(path for path in ALLOWLIST if not (root / path).is_file())
    return found, unexpected, stale + [f"{p} (file does not exist)" for p in missing]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    found, unexpected, stale = audit()

    if args.report:
        for relative, number, token, line in found:
            reason = ALLOWLIST.get(relative, "*** NOT ALLOWLISTED ***")
            print(f"{relative}:{number} [{token}] {reason}\n    {line[:110]}")
        print(f"\n{len(found)} occurrence(s) in {len({f[0] for f in found})} file(s); "
              f"{len(ALLOWLIST)} allowlisted")
        return 0

    problems = []
    for relative in unexpected:
        lines = [n for r, n, _, _ in found if r == relative]
        problems.append(f"previous product name in a file that is not allowlisted: "
                        f"{relative} (line {', '.join(str(n) for n in lines[:5])})")
    for entry in stale:
        problems.append(f"allowlist entry no longer needed: {entry}")

    if problems:
        for problem in problems:
            print(f"naming audit: {problem}", file=sys.stderr)
        print("naming audit: add the file to ALLOWLIST in tools/naming_audit.py with a "
              "reason, or remove the name from it", file=sys.stderr)
        return 1

    print(f"naming audit: {len(found)} occurrence(s), all of them allowlisted "
          f"({len(ALLOWLIST)} files classified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
