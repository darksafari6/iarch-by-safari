# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""data/licenses.json must be rendered from branding/notices.json, never by hand."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import notices as notices_tool  # noqa: E402

LICENSES = ROOT / "data" / "licenses.json"
NOTICES_MD = ROOT / "THIRD_PARTY_NOTICES.md"

# Projects the credit table must cover, by what a person would call them.
REQUIRED_PROJECTS = (
    "Hyprland", "Noctalia", "kitty", "fish shell", "Starship", "fastfetch", "Satty",
    "JetBrains Mono", "Nerd Fonts", "Papirus icon theme", "Bibata cursor theme", "adw-gtk3",
    "The original dotfiles this repository started from",
)


class LicensesData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(LICENSES.read_text(encoding="utf-8"))
        cls.source = json.loads((ROOT / "branding" / "notices.json").read_text(encoding="utf-8"))

    def test_the_generated_files_match_their_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "notices.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_every_component_of_the_source_is_present(self):
        source_ids = {c["id"] for c in self.source["components"]}
        rendered_ids = {c["id"] for c in self.data["components"]}
        self.assertEqual(source_ids, rendered_ids)

    def test_required_projects_are_credited(self):
        names = " · ".join(c["name"] for c in self.data["components"])
        for project in REQUIRED_PROJECTS:
            self.assertIn(project, names, f"missing from the credit table: {project}")

    def test_no_license_field_is_empty_or_guessed(self):
        for component in self.data["components"]:
            with self.subTest(component=component["id"]):
                self.assertTrue(component["license"].strip())
                self.assertTrue(component["purpose"].strip())
                self.assertTrue(component["used_by"], "credit without a use is noise")
                if component["unverified"]:
                    self.assertIn("TODO(verify)", component["license"])
                    self.assertTrue(component["open_items"],
                                    "an unverified license must point at docs/UNVERIFIED.md")

    def test_unverified_licenses_are_registered_in_the_unverified_log(self):
        text = (ROOT / "docs" / "UNVERIFIED.md").read_text(encoding="utf-8")
        unverified = [c for c in self.data["components"] if c["unverified"]]
        self.assertTrue(unverified, "expected at least the AUR font packages to be unverified")
        for component in unverified:
            for verify_id in component["open_items"]:
                self.assertIn(verify_id, text, f"{component['id']}: {verify_id} is not registered")

    def test_provenance_entry_names_the_earlier_publication(self):
        provenance = [c for c in self.data["components"] if c["kind"] == "provenance"]
        self.assertEqual(1, len(provenance), "exactly one provenance entry")
        entry = provenance[0]
        self.assertIn("gitlab.com/minimalinux/minimaDots", entry["upstream"])
        self.assertIn("Safari", entry["copyright"])

    def test_product_block_matches_the_brand_definition(self):
        values = notices_tool.product(ROOT)
        product = self.data["product"]
        self.assertEqual(product["name"], values["IARCH_PRODUCT_NAME"])
        self.assertEqual(product["license"], values["IARCH_LICENSE_ID"])
        self.assertEqual(product["license_file"], values["IARCH_LICENSE_FILE"])
        self.assertEqual(product["repository"], values["IARCH_REPO_URL"])
        self.assertTrue((ROOT / values["IARCH_LICENSE_FILE"]).is_file())

    def test_the_markdown_notices_render_the_same_set(self):
        text = NOTICES_MD.read_text(encoding="utf-8")
        for component in self.data["components"]:
            self.assertIn(component["name"], text, f"{component['name']} is not in the rendered notices")
        self.assertIn("Where this repository came from", text)

    def test_schema_shape(self):
        schema = json.loads((ROOT / "data" / "schemas" / "licenses.schema.json").read_text(encoding="utf-8"))
        for key in schema["required"]:
            self.assertIn(key, self.data)
        allowed = set(schema["properties"]["components"]["items"]["properties"])
        for component in self.data["components"]:
            self.assertEqual(set(), set(component) - allowed,
                             f"{component['id']} has keys the schema does not allow")
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed; CI validates it with the library")
        jsonschema.validate(self.data, schema)


if __name__ == "__main__":
    unittest.main()
