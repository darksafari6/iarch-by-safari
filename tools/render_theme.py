#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the selected theme pack without reloading the running session."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.cli.session_theme import main  # noqa: E402
if __name__ == "__main__":
    sys.exit(main(["render", *sys.argv[1:]]))
