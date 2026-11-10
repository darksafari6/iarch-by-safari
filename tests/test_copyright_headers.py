# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Every new file carries the one defined copyright header; nothing is guessed."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import iarch_brand as brand  # noqa: E402

HEADER = brand.product(ROOT)["IARCH_COPYRIGHT_HEADER"]

# Files this work added. Pre-existing files keep whatever header they have, and
# vendored upstream code under legacy/ keeps its own copyright untouched.
NEW_SOURCE_FILES = (
    "iarch/lib/__init__.py",
    "iarch/lib/configstore.py",
    "iarch/lib/renderers.py",
    "tools/extract_keybinds.py",
    "tools/profile_preset.py",
    "profiles/performance.toml",
    "tests/test_config_store.py",
    "tests/test_profile_preset.py",
    "tests/test_keybinds_data.py",
    "tests/test_architecture_docs.py",
    "tests/test_copyright_headers.py",
    "tests/test_licenses_data.py",
)


def header_line(text: str) -> str:
    lines = text.splitlines()
    for line in lines[:4]:
        if line.startswith("#!") or not line.strip():
            continue
        return line
    return ""


class CopyrightHeaders(unittest.TestCase):
    def test_new_source_files_start_with_the_defined_header(self):
        for relative in NEW_SOURCE_FILES:
            path = ROOT / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file(), f"missing: {relative}")
                first = header_line(path.read_text(encoding="utf-8"))
                self.assertEqual(first, f"# {HEADER}", f"{relative} does not carry the header")

    def test_new_markdown_files_carry_it_as_a_comment_free_line_or_note(self):
        for relative in ("iarch/README.md", "iarch/cli/README.md", "iarch/settings-app/README.md"):
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_every_data_json_carries_the_header_key(self):
        files = sorted((ROOT / "data").rglob("*.json"))
        self.assertTrue(files, "data/ has no JSON at all")
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertEqual(payload.get("_copyright"), HEADER,
                                 "data files carry the header as their _copyright key")

    def test_vendored_upstream_copyright_is_untouched(self):
        """legacy/ must not be stamped with this repository's header."""
        result = subprocess.run(["git", "ls-files", "-z", "legacy/"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        for relative in result.stdout.split("\0"):
            if not relative or not relative.endswith((".py", ".sh", ".conf", ".ini", ".toml")):
                continue
            text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=relative):
                self.assertNotIn(HEADER, text, "frozen legacy files keep their own headers")

    def test_the_header_and_the_license_text_agree(self):
        license_text = (ROOT / brand.product(ROOT)["IARCH_LICENSE_FILE"]).read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3", license_text)
        self.assertIn("GPL-3.0-or-later", HEADER,
                      "the header must name the SPDX expression it relies on")
        self.assertTrue(re.search(r"any later version", license_text),
                        "GPL-3.0 text offers the 'or later' option the header uses")


if __name__ == "__main__":
    unittest.main()
