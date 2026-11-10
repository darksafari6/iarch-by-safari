# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Every JSON and TOML file in the repository parses, and data/ has no gaps.

CI runs the same invariants with the jsonschema library installed; this file
makes them runnable locally without it, so a bad data file is caught before push
rather than after.
"""
import json
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import iarch_brand as brand  # noqa: E402

PAIRS = {
    "data/settings.default.json": "data/schemas/settings.schema.json",
    "data/contacts.default.json": "data/schemas/contacts.schema.json",
    "data/keybinds.default.json": "data/schemas/keybinds.schema.json",
    "data/design/glass.tokens.json": "data/schemas/design-tokens.schema.json",
    "data/licenses.json": "data/schemas/licenses.schema.json",
}

PALETTE_FIELDS = {
    "mPrimary", "mOnPrimary", "mSecondary", "mOnSecondary", "mTertiary",
    "mOnTertiary", "mError", "mOnError", "mSurface", "mOnSurface",
    "mSurfaceVariant", "mOnSurfaceVariant", "mOutline", "mShadow", "mHover",
    "mOnHover",
}


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class DataFiles(unittest.TestCase):
    def test_every_json_file_in_data_parses(self):
        files = sorted((ROOT / "data").rglob("*.json"))
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                json.loads(path.read_text(encoding="utf-8"))

    def test_every_document_in_data_has_a_schema(self):
        documents = {p.relative_to(ROOT).as_posix() for p in (ROOT / "data").rglob("*.json")}
        schemas = {p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "schemas").glob("*.json")}
        unmapped = documents - schemas - set(PAIRS)
        self.assertEqual(set(), unmapped, "data/ ships a JSON file nothing validates")
        for schema in schemas:
            self.assertIn(schema, PAIRS.values(), f"schema is not used by any document: {schema}")

    def test_schemas_are_wellformed_draft7(self):
        for schema_path in PAIRS.values():
            schema = read_json(schema_path)
            with self.subTest(schema=schema_path):
                self.assertEqual("http://json-schema.org/draft-07/schema#", schema.get("$schema"))
                self.assertEqual("object", schema.get("type"))
                self.assertTrue(schema.get("properties"))
                self.assertTrue(schema.get("required"))
        try:
            import jsonschema  # type: ignore
        except ImportError:
            return
        for schema_path in PAIRS.values():
            jsonschema.Draft7Validator.check_schema(read_json(schema_path))

    def test_documents_validate_against_their_schemas(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed; CI validates with the library")
        for document_path, schema_path in PAIRS.items():
            with self.subTest(document=document_path):
                jsonschema.validate(read_json(document_path), read_json(schema_path))

    def test_every_toml_file_parses(self):
        files = sorted((ROOT / ".config" / "noctalia").glob("*.toml"))
        files += sorted((ROOT / "profiles").glob("*.toml"))
        files += [ROOT / ".config" / "starship.toml"]
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                tomllib.loads(path.read_text(encoding="utf-8"))


class GlassProfile(unittest.TestCase):
    """The keys that make the shipped profile glass, asserted from the file."""

    @classmethod
    def setUpClass(cls):
        cls.config = tomllib.loads(
            (ROOT / ".config" / "noctalia" / "config.toml").read_text(encoding="utf-8"))
        cls.overlay = tomllib.loads((ROOT / "profiles" / "performance.toml").read_text(encoding="utf-8"))

    def test_the_glass_keys_are_set(self):
        values = brand.product(ROOT)
        self.assertEqual(values["IARCH_PALETTE_ID"], self.config["theme"]["custom_palette"])
        self.assertTrue(self.config["shell"]["settings_window_translucent"])
        self.assertEqual("glass", self.config["shell"]["panel"]["transparency_mode"])
        self.assertTrue(self.config["bar"]["default"]["compositor_blur"])
        self.assertTrue(self.config["dock"]["enabled"])
        self.assertTrue(self.config["notification"]["enable_daemon"])
        self.assertFalse(self.config["audio"]["enable_notification_sounds"])

    def flatten(self, model, prefix=()):
        flat = {}
        for key, value in model.items():
            path = prefix + (key,)
            if isinstance(value, dict):
                flat.update(self.flatten(value, path))
            else:
                flat[path] = value
        return flat

    def test_the_performance_overlay_cannot_invent_keys(self):
        base, overlay = self.flatten(self.config), self.flatten(self.overlay)
        self.assertTrue(overlay, "the overlay is empty")
        self.assertEqual([], [".".join(k) for k in overlay if k not in base])
        self.assertEqual([], [".".join(k) for k in overlay if type(overlay[k]) is not type(base[k])])

    def test_the_palette_is_complete_in_both_variants(self):
        palette = read_json(".config/noctalia/palettes/iarch-midnight.json")
        for variant in ("dark", "light"):
            self.assertTrue(PALETTE_FIELDS <= set(palette[variant]),
                            f"{variant} variant is missing palette fields")
            for key in PALETTE_FIELDS:
                value = palette[variant][key]
                with self.subTest(variant=variant, key=key):
                    self.assertIsInstance(value, str)
                    self.assertRegex(value, r"^#[0-9a-fA-F]{6}$")


if __name__ == "__main__":
    unittest.main()
