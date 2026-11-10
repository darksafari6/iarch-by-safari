# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Old product names survive only where a reason is recorded for them."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_audit  # noqa: E402


class NamingAudit(unittest.TestCase):
    def test_every_hit_in_the_repository_is_allowlisted(self):
        found, unexpected, stale = naming_audit.audit(ROOT)
        self.assertTrue(found, "the audit found nothing at all; is it scanning?")
        self.assertEqual([], unexpected, "unclassified files carry a previous product name")
        self.assertEqual([], stale, "allowlist entries no longer match anything")

    def test_the_cli_check_exits_zero(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "naming_audit.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("all of them allowlisted", result.stdout)

    def test_excluded_paths_are_not_scanned(self):
        scanned = {p.relative_to(ROOT).as_posix() for p in naming_audit.scanned_files(ROOT)}
        self.assertNotIn("THIRD_PARTY_NOTICES.md", scanned)
        self.assertNotIn("LICENSE.txt", scanned)
        self.assertFalse(any(p.startswith("legacy/") for p in scanned), "legacy/ is frozen")
        self.assertFalse(any(p.startswith(".git/") for p in scanned))
        self.assertFalse(any(p.endswith(".png") or p.endswith(".webp") for p in scanned))

    def test_the_tokens_cover_the_previous_names(self):
        for token in ("minimalinux", "minimadots", "minimaos", "noctalia-shell"):
            self.assertIn(token, naming_audit.TOKENS)

    def test_a_new_unclassified_hit_is_caught(self):
        """The audit must fail on a file nobody thought about, not just on known ones."""
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            (sandbox / "docs").mkdir()
            fresh = sandbox / "docs" / "NEW.md"
            fresh.write_text("Installed by minimaLinux.\n", encoding="utf-8")
            allowlisted = sandbox / "README.md"
            allowlisted.write_text("Earlier name: minimaDots.\n", encoding="utf-8")
            found, unexpected, stale = naming_audit.audit(sandbox)
            self.assertEqual(["docs/NEW.md"], unexpected)
            self.assertIn("README.md", {f[0] for f in found})

    def test_every_allowlisted_file_exists_and_is_classified_with_a_reason(self):
        for path, reason in naming_audit.ALLOWLIST.items():
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), f"allowlist names a missing file: {path}")
                self.assertGreater(len(reason.split()), 2, f"{path} has no real reason recorded")
                categories = (naming_audit.FROZEN, naming_audit.POLICY, naming_audit.PROVENANCE,
                              naming_audit.HISTORY, naming_audit.TEST)
                self.assertTrue(reason.startswith(categories),
                                f"{path}: reason must start with one of the defined categories")


if __name__ == "__main__":
    unittest.main()
