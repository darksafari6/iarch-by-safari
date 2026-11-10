"""Branding and third-party credit tests.

These tests are static: no desktop session, shell or package manager is started.
They protect the two rules the product is built on - the everyday UI says
"iArch by Safari", and third-party credit is complete, generated and never
silently dropped.
"""
import importlib.util
import json
import xml.etree.ElementTree as ET
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


brand = load_tool("iarch_brand", "tools/iarch_brand.py")
notices = load_tool("notices", "tools/notices.py")


class ProductNaming(unittest.TestCase):
    def test_product_env_is_consistent(self):
        self.assertEqual(brand.check(ROOT), [])

    def test_product_name_and_ids(self):
        values = brand.product(ROOT)
        self.assertEqual(values["IARCH_PRODUCT_NAME"], "iArch by Safari")
        self.assertEqual(values["IARCH_PRODUCT_ID"], "iarch")
        self.assertEqual(values["IARCH_MAINTAINER"], "Safari")
        self.assertEqual(values["IARCH_LICENSE_ID"], "GPL-3.0-or-later")
        self.assertTrue(values["IARCH_COPYRIGHT_HEADER"].endswith(values["IARCH_LICENSE_ID"]),
                        "the copyright header and the SPDX expression must not disagree")

    def test_parser_rejects_sloppy_edits(self):
        with self.assertRaises(ValueError):
            brand.parse_env("IARCH_PRODUCT_NAME=iArch by Safari")
        with self.assertRaises(ValueError):
            brand.parse_env('IARCH_PRODUCT_NAME="a"\nIARCH_PRODUCT_NAME="b"')
        self.assertEqual(brand.parse_env('# comment\nA="1"\n\nexport B="2"\n'), {"A": "1", "B": "2"})

    def test_cli_check_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "iarch_brand.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_palette_identity_matches_shipped_config(self):
        values = brand.product(ROOT)
        palette = (
            ROOT / ".config" / values["IARCH_SHELL_CONFIG_DIR"]
            / "palettes" / f"{values['IARCH_PALETTE_ID']}.json"
        )
        self.assertTrue(palette.is_file(), palette)
        config = tomllib.loads((ROOT / ".config" / "noctalia" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["theme"]["source"], "custom")
        self.assertEqual(config["theme"]["custom_palette"], values["IARCH_PALETTE_ID"])
        colors = json.loads(palette.read_text(encoding="utf-8"))
        self.assertEqual(sorted(colors), ["dark", "light"])

    def test_staging_payload_ships_the_renamed_palette(self):
        staged = subprocess.run(
            ["bash", str(ROOT / "lib" / "stage-v5-config.sh"), str(ROOT / ".config"),
             str(self.tmp_stage)],
            capture_output=True, text=True,
        )
        self.assertEqual(staged.returncode, 0, staged.stderr)
        values = brand.product(ROOT)
        palette = self.tmp_stage / "noctalia" / "palettes" / f"{values['IARCH_PALETTE_ID']}.json"
        self.assertTrue(palette.is_file())
        self.assertEqual(list((self.tmp_stage / "noctalia" / "palettes").glob("minimaOS*")), [])

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_stage = Path(self._tmp.name) / "stage"
        self.tmp_stage.mkdir()


class ThirdPartyNotices(unittest.TestCase):
    def setUp(self):
        self.data = notices.load(ROOT)
        self.rendered = notices.render(self.data, ROOT)

    def test_notices_data_passes_validation(self):
        self.assertEqual(notices.validate(self.data, ROOT), [])

    def test_committed_file_matches_generated_output(self):
        self.assertEqual(notices.output_path(ROOT).read_text(encoding="utf-8"), self.rendered)

    def test_cli_check_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "notices.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_render_is_deterministic(self):
        self.assertEqual(notices.render(self.data, ROOT), self.rendered)

    def test_every_component_is_listed(self):
        for component in self.data["components"]:
            self.assertIn(component["name"], self.rendered)
            self.assertIn(component["license"], self.rendered)
            for path in component["used_by"]:
                self.assertIn(path, self.rendered)

    def test_unverified_licenses_are_registered(self):
        unverified = (ROOT / "docs" / "UNVERIFIED.md").read_text(encoding="utf-8")
        todo = [c for c in self.data["components"] if "TODO(verify)" in c["license"]]
        self.assertTrue(todo, "expected at least one asset with unestablished rights")
        for component in todo:
            self.assertTrue(component["verify_ids"], component["id"])
            for verify_id in component["verify_ids"]:
                self.assertIn(verify_id, unverified)

    def test_vendored_code_includes_its_license_text(self):
        vendored = [c for c in self.data["components"] if c["kind"] == "vendored-code"]
        self.assertTrue(vendored)
        for component in vendored:
            self.assertIn(self.data["license_texts"][component["license_text"]].splitlines()[0], self.rendered)


class CreditsArePreserved(unittest.TestCase):
    """The credit policy removes names from the UI, never from the record."""

    def test_product_license_file_is_gpl3_and_untouched(self):
        text = (ROOT / "LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)
        self.assertIn("Version 3", text)
        self.assertGreater(len(text), 30000)

    def test_vendored_plugin_manifest_keeps_author_and_license(self):
        manifest = json.loads(
            (ROOT / "legacy" / "config" / "noctalia" / "plugins" / "hyprland-keybinds" / "manifest.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["author"], "tonekneeo")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["id"], "hyprland-keybinds")

    def test_installer_contributor_credit_is_kept(self):
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("echilon, tonekneeo, xnyte", installer)

    def test_readme_points_at_the_notices_file(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("THIRD_PARTY_NOTICES.md", readme)
        self.assertIn("LICENSE.txt", readme)

    def test_notices_file_names_the_product_license(self):
        """Asserted against the brand definition, so the two cannot drift apart."""
        rendered = notices.render(notices.load(ROOT), ROOT)
        values = brand.product(ROOT)
        self.assertIn(values["IARCH_LICENSE_ID"], rendered)
        self.assertIn(values["IARCH_LICENSE_FILE"], rendered)
        self.assertIn(f"# Third-party notices — {values['IARCH_PRODUCT_NAME']}", rendered)


class ReadmeHeader(unittest.TestCase):
    """The top of the README is a product surface: title, badges, screenshots."""

    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_title_logo_badges_and_screenshots(self):
        self.assertIn("# iArch by Safari", self.readme)
        self.assertIn("assets/branding/iarch-logo.svg", self.readme)
        self.assertIn("## Screenshots", self.readme)
        for badge in ("license", "last-commit", "stars"):
            self.assertIn(
                f"img.shields.io/github/{badge}/darksafari6/iarch-by-safari",
                self.readme,
                f"README must carry the GitHub {badge} badge",
            )

    def test_no_embedded_video_and_no_gitlab_urls(self):
        """The trailer is linked, never embedded; no video file ships in the repo."""
        self.assertNotIn("img.youtube.com", self.readme, "no YouTube thumbnail embed")
        self.assertNotIn("<video", self.readme, "no embedded video player")
        self.assertNotIn(".mp4", self.readme, "no video file is shipped or linked as a file")
        self.assertNotIn("gitlab.com", self.readme)
        self.assertNotIn("trailer/", self.readme, "the trailer directory was removed")

    def test_the_trailer_link_points_at_the_video(self):
        self.assertIn("https://www.youtube.com/watch?v=HJhm0aT3lNw", self.readme)
        tracked = subprocess.run(["git", "ls-files", "trailer/"], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual("", tracked, "no video file may ship in the repository")

    def test_lineage_is_stated_once_in_the_credits_section(self):
        head, _, credits = self.readme.partition("## Credits & License")
        self.assertTrue(credits, "README must keep a Credits & License section")
        self.assertIn("GitLab", credits)
        self.assertNotIn("not as a fork", head + credits)


class BrandingAssets(unittest.TestCase):
    """The logo artwork ships in the repository and is original SVG."""

    def test_both_logos_are_wellformed_svg_with_the_same_geometry(self):
        for name in ("iarch-logo.svg", "iarch-logo-mono.svg"):
            with self.subTest(logo=name):
                root = ET.parse(ROOT / "assets" / "branding" / name).getroot()
                self.assertEqual(root.tag.split("}")[-1], "svg")
                self.assertEqual(root.get("viewBox"), "0 0 128 128")
                self.assertTrue((root.find("title") is not None) or any(
                    e.get("id", "").endswith("title") for e in root.iter()),
                    "the logo must carry an accessible title")

    def test_logos_are_original_and_unreferenced_by_other_marks(self):
        # Originality cannot be proven by a test; what can be pinned is that the
        # artwork is hand-written vector geometry in this repository and not a
        # downloaded raster or a traced third-party mark.
        for name in ("iarch-logo.svg", "iarch-logo-mono.svg"):
            text = (ROOT / "assets" / "branding" / name).read_text(encoding="utf-8")
            self.assertNotIn("base64", text)
            self.assertNotIn("<image", text)
            self.assertIn("Original artwork drawn for this repository", text)


if __name__ == "__main__":
    unittest.main()
