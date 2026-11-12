# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The README is a product surface: fixed order, fixed budget, no overclaiming."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LINE_BUDGET = 250

# The order a reader is promised: what it is, what it looks like, what it does,
# what you need, how to install, how to drive it, how to change it, how to undo
# it, what to do when it breaks, who made it.
REQUIRED_ORDER = (
    "Screenshots",
    "Features",
    "Requirements",
    "Install",
    "Shortcuts",
    "Customization",
    "Uninstall and rollback",
    "Troubleshooting",
    "Credits & License",
)


class ReadmeStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = README.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()
        cls.headings = re.findall(r"^## (.+)$", cls.text, re.M)

    def test_it_stays_under_the_line_budget(self):
        self.assertLess(len(self.lines), LINE_BUDGET,
                        f"README is {len(self.lines)} lines; the budget is {LINE_BUDGET}")

    def test_sections_appear_in_the_promised_order(self):
        self.assertEqual(list(REQUIRED_ORDER), self.headings,
                         "README sections must appear in this order and no others")

    def test_title_logo_and_badges_come_before_any_section(self):
        first_heading = self.text.index("## ")
        head = self.text[:first_heading]
        self.assertIn("# iArch by Safari", head)
        self.assertIn("assets/branding/iarch-logo.svg", head)
        self.assertIn("img.shields.io", head)

    def test_install_section_gives_the_real_command(self):
        section = self.section("Install")
        self.assertIn("sudo ./install.sh", section)
        self.assertIn("git clone https://github.com/darksafari6/iarch-by-safari.git", section)
        self.assertIn("sudo ./fedora_install.sh", section)

    def test_dry_run_is_described_as_not_existing_yet(self):
        section = self.section("Install")
        self.assertIn("--dry-run", section)
        self.assertIn("does not exist yet", section)
        self.assertIn("Part 6", section)

    def test_requirements_name_both_distributions_and_the_fresh_install_rule(self):
        section = self.section("Requirements")
        for phrase in ("archinstall", "Hyprland", "Fedora", "fresh", "sddm"):
            self.assertIn(phrase, section)

    def test_shortcuts_section_links_the_generated_table(self):
        section = self.section("Shortcuts")
        self.assertIn("docs/SHORTCUTS.md", section)
        self.assertIn("SUPER + H", section, "the overlay key must be mentioned")
        self.assertIn("reserved", section, "and it must be described as not bound yet")

    def test_features_do_not_overclaim(self):
        """Anything not built must say so in the same row."""
        section = self.section("Features")
        self.assertIn("Settings app", section)
        self.assertIn("Game mode", section)
        self.assertIn("Focus mode", section)
        self.assertIn("Contact page", section)
        for row in section.splitlines():
            if row.startswith("| Settings app"):
                self.assertRegex(row, r"Part \d")
            if row.startswith("| Contact page"):
                self.assertRegex(row, r"Part \d")

    def test_the_two_modes_say_they_are_commands_and_say_what_they_cannot_do(self):
        """A mode that ships as a command must not read like a button, or like a proof.

        Both rows name the file you run, and both carry the limitation that makes
        the claim honest: game mode has no key bound and no measured saving, focus
        mode is runtime state that a reload ends. A row that said only "one switch
        that drops effects for latency" would be the overclaim this test exists to
        catch, in the other direction from "Not built".
        """
        section = self.section("Features")
        rows = {row.split("|")[1].strip(): row for row in section.splitlines()
                if row.startswith("|") and row.count("|") >= 4}
        game, focus = rows["Game mode"], rows["Focus mode"]
        self.assertIn("iarch/cli/iarch_gamemode.py", game)
        self.assertIn("iarch/cli/iarch_focus.py", focus)
        self.assertRegex(game, r"PERF-01")
        self.assertIn("no key is bound", game)
        self.assertIn("runtime state", focus)
        self.assertIn("relogin", focus)
        for row in (game, focus):
            self.assertNotIn("Not built", row)
            self.assertIn("Command ships today", row)

    def test_the_honest_summary_does_not_claim_a_mode_nobody_has_watch(self):
        section = self.section("Features")
        summary = section.split("| Contact page")[1]
        self.assertIn("commands you run rather than buttons you click", summary)
        self.assertIn("neither has been watched on a live session", summary)
        self.assertNotIn("game mode are not built yet", summary)

    def test_credits_section_is_the_short_factual_one(self):
        section = self.section("Credits & License")
        self.assertIn("licensed under GPL-3.0", section)
        self.assertIn("THIRD_PARTY_NOTICES.md", section)
        self.assertIn("LICENSE.txt", section)
        self.assertLess(len(section.splitlines()), 30, "the credits section stays short")

    def test_no_emoji_headings_and_no_html_headings(self):
        for heading in re.findall(r"^#{1,3} (.+)$", self.text, re.M):
            self.assertFalse(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", heading),
                             f"heading carries an emoji: {heading}")
        self.assertNotIn("<h1", self.text)

    def test_every_relative_link_resolves(self):
        for target in re.findall(r"\]\(([^)]+)\)", self.text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0]
            with self.subTest(link=path):
                self.assertTrue((ROOT / path).exists(), f"README links something missing: {path}")

    def test_every_image_source_exists(self):
        for source in re.findall(r'<img src="([^"]+)"', self.text):
            if source.startswith(("http://", "https://")):
                continue
            with self.subTest(image=source):
                self.assertTrue((ROOT / source).is_file(), f"README shows a missing image: {source}")

    def section(self, name: str) -> str:
        pattern = rf"^## {re.escape(name)}$(.*?)(?=^## |\Z)"
        match = re.search(pattern, self.text, re.M | re.S)
        self.assertIsNotNone(match, f"README has no section: {name}")
        return match.group(1)


if __name__ == "__main__":
    unittest.main()
