# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Contracts for the six data/themes packs and their runtime projections."""
from __future__ import annotations
import contextlib
import io
import json
import os
import shutil
import stat
import tomllib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iarch.cli import session_theme

ROOT = Path(__file__).resolve().parents[1]
IDS = ("greenhouse", "amber-bloom", "neon-rain", "forest-night", "violet-glass", "crimson-silk")


class ThemePacks(unittest.TestCase):
    def test_exact_six_pack_files_and_schema(self):
        self.assertEqual(list(IDS), session_theme.theme_ids())
        schema = json.loads((ROOT / "data/themes/schema.json").read_text())
        self.assertEqual("iArch session theme pack", schema["title"])
        for theme_id in IDS:
            with self.subTest(theme=theme_id):
                pack = session_theme.load_theme(theme_id)
                session_theme.validate_pack(pack, theme_id, ROOT / "data/themes" / f"{theme_id}.json")
                self.assertEqual(theme_id, pack["meta"]["id"])
                self.assertEqual(f"assets/wallpapers/themes/{theme_id}.webp", pack["wallpaper"])
                self.assertEqual(f"assets/sounds/{theme_id}/notify.ogg", pack["sound"]["notify"])
                self.assertEqual(set(f"color{i}" for i in range(16)),
                                 set(k for k in pack["terminal"] if k.startswith("color")))

    def test_saved_choice_is_separate_from_pack_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": tmp}
            self.assertEqual(("forest-night", False), session_theme.current_theme_id(env))
            choice = session_theme.choice_path(env)
            choice.parent.mkdir(parents=True, exist_ok=True)
            choice.write_text('{"id":"violet-glass"}\n', encoding="utf-8")
            self.assertEqual(("violet-glass", True), session_theme.current_theme_id(env))

    def test_list_and_current_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": tmp}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(0, session_theme.main(["list"]))
            for theme_id in IDS:
                self.assertIn(theme_id, out.getvalue())
            current = io.StringIO()
            with contextlib.redirect_stdout(current):
                self.assertEqual(0, session_theme.main(["current"]))
            self.assertIn("forest-night", current.getvalue())
            self.assertFalse((Path(tmp) / "theme.json").exists())

    def test_apply_writes_the_saved_choice_and_all_local_projections_without_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config_home = home / ".config"
            shutil.copytree(ROOT / ".config", config_home)
            env = {
                "HOME": tmp,
                "IARCH_CONFIG_DIR": str(config_home / "iarch"),
                "IARCH_STATE_DIR": str(home / ".local" / "state" / "iarch"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            }
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, env, clear=True):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = session_theme.main([
                        "apply", "forest-night", "--config-home", str(config_home), "--no-reload"
                    ])
            self.assertEqual(0, code, err.getvalue())
            self.assertEqual({"id": "forest-night"},
                             json.loads((config_home / "iarch" / "theme.json").read_text()))
            self.assertTrue((config_home / "hypr/generated/theme.lua").is_file())
            self.assertTrue((config_home / "noctalia/palettes/iarch-active.json").is_file())
            self.assertTrue((config_home / "kitty/theme.conf").is_file())
            self.assertIn("[palettes.forest-night]",
                          (config_home / "starship.toml").read_text())
            self.assertIn("BEGIN iArch session theme: forest-night",
                          (config_home / "gtk-3.0/gtk.css").read_text())
            updated = tomllib.loads((config_home / "noctalia/config.toml").read_text())
            self.assertEqual("iarch-active", updated["theme"]["custom_palette"])
            self.assertIn("audio: no playback command was run", out.getvalue())
            self.assertNotIn("pw-play", out.getvalue())
            self.assertFalse((config_home / "iarch/sounds/active-notify.ogg").exists())
            sound_index = home / ".local/share/sounds/iarch-session/index.theme"
            self.assertIn("Inherits=freedesktop", sound_index.read_text(encoding="utf-8"))


    def test_public_launcher_reaches_the_session_theme_cli(self):
        launcher = ROOT / "scripts" / "iarch-theme.sh"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR)
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HOME": tmp,
                "IARCH_CONFIG_DIR": str(Path(tmp) / ".config" / "iarch"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            }
            listed = subprocess.run([str(launcher), "list"], cwd=str(ROOT),
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, listed.returncode, listed.stdout + listed.stderr)
            for theme_id in IDS:
                self.assertIn(theme_id, listed.stdout)
            current = subprocess.run([str(launcher), "current"], cwd=str(ROOT),
                                     env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, current.returncode, current.stdout + current.stderr)
            self.assertIn("forest-night", current.stdout)
            self.assertFalse((Path(env["IARCH_CONFIG_DIR"]) / "theme.json").exists())


class ThemeRenderers(unittest.TestCase):
    def setUp(self):
        self.pack = session_theme.load_theme("forest-night")

    def test_hyprland_output_contains_pack_geometry_blur_and_motion(self):
        rendered = session_theme.render_hypr_theme(self.pack)
        self.assertIn("gaps_in = 4", rendered)
        self.assertIn("rounding = 12", rendered)
        self.assertIn('hl.curve("iarch-forest-night"', rendered)
        self.assertIn('leaf = "workspaces", enabled = false', rendered)
        self.assertIn('leaf = "windowsIn"', rendered)

    def test_game_mode_disables_animation_blur_shadow_and_dim(self):
        rendered = session_theme.render_hypr_theme(self.pack, game_mode=True)
        self.assertIn("hl.config({ animations = { enabled = false } })", rendered)
        self.assertIn("enabled = false", rendered)
        self.assertIn("inactive_opacity = 1.0", rendered)
        self.assertIn("dim_strength = 0.0", rendered)
        self.assertIn("range = 0", rendered)

    def test_focus_mode_uses_focus_token_dim(self):
        rendered = session_theme.render_hypr_theme(self.pack, focus_mode=True)
        self.assertIn("dim_inactive = true", rendered)
        self.assertIn("dim_strength = 0.5", rendered)

    def test_render_active_can_stage_game_override_before_the_mode_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_home = root / "config"
            env = {
                "HOME": tmp,
                "IARCH_CONFIG_DIR": str(root / "iarch"),
                "IARCH_STATE_DIR": str(root / "state"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            }
            session_theme.render_active(config_home, env, game_mode_override=True)
            generated = config_home / "hypr" / "generated" / "theme.lua"
            self.assertTrue(generated.is_file())
            content = generated.read_text(encoding="utf-8")
            self.assertIn("hl.config({ animations = { enabled = false } })", content)
            self.assertIn("dim_strength = 0.0", content)
            self.assertFalse((Path(env["IARCH_CONFIG_DIR"]) / "theme.json").exists())

    def test_noctalia_palette_matches_existing_custom_palette_shape(self):
        payload = json.loads(session_theme.render_noctalia_palette(self.pack))
        self.assertEqual({"dark", "light"}, set(payload))
        for mode_name, mode in payload.items():
            for key in ("mPrimary", "mOnPrimary", "mSurface", "mOnSurface", "mOutline", "terminal"):
                self.assertIn(key, mode)
            if mode_name == "dark":
                palette = self.pack["noctalia"]["palette"]
                self.assertEqual(palette["bar"], mode["mSurfaceVariant"])
                self.assertEqual(palette["dock"], mode["mTertiary"])
                self.assertEqual(palette["notification"], mode["mHover"])
            self.assertEqual(8, len(mode["terminal"]["normal"]))
            self.assertEqual(8, len(mode["terminal"]["bright"]))
            self.assertRegex(mode["mSurface"], r"^#[0-9A-Fa-f]{6}$")

    def test_noctalia_config_updates_only_supported_existing_keys(self):
        source = (ROOT / ".config/noctalia/config.toml").read_text(encoding="utf-8")
        updated = session_theme.render_noctalia_config(source, self.pack)
        self.assertIn('custom_palette = "iarch-active"', updated)
        self.assertIn('position = "top"', updated)
        self.assertIn('sidebar = "compact"', updated)
        self.assertIn('enable_notification_sounds = true', updated)
        self.assertIn('sound_volume = 0.32', updated)
        self.assertIn('sound_theme = "iarch-session"', updated)
        self.assertIn('background_opacity = 0.82', updated)
        self.assertIn('[idle.behavior.lock]', updated)

    def test_violet_glass_surface_alpha_uses_shell_opacity_not_palette_alpha_hex(self):
        violet = session_theme.load_theme("violet-glass")
        self.assertEqual("#24102E", violet["noctalia"]["palette"]["surface"])
        self.assertEqual(0.72, violet["noctalia"]["surface_alpha"])
        palette = json.loads(session_theme.render_noctalia_palette(violet))
        self.assertEqual("#24102E", palette["dark"]["mSurface"])
        config = (ROOT / ".config/noctalia/config.toml").read_text(encoding="utf-8")
        updated = session_theme.render_noctalia_config(config, violet)
        self.assertEqual(3, updated.count("background_opacity = 0.72"))

    def test_kitty_and_starship_render_complete_palette(self):
        kitty = session_theme.render_kitty_theme(self.pack)
        self.assertEqual(16, sum(1 for line in kitty.splitlines() if line.startswith("color")))
        starship = session_theme.render_starship_config("[character]\nsuccess_symbol = \"❯\"\n", self.pack)
        self.assertIn('palette = "forest-night"', starship)
        self.assertIn('[palettes.forest-night]', starship)
        self.assertIn('bright-white = "#F4FAF2"', starship)

    def test_gtk_theme_block_preserves_shipped_glass_css_and_is_idempotent(self):
        source = "/* GENERATED BY iArch. DO NOT EDIT. */\n.iarch-glass-card { border-radius: 16px; }\n"
        first = session_theme.render_gtk_css(source, self.pack)
        second = session_theme.render_gtk_css(first, self.pack)
        self.assertIn(".iarch-glass-card { border-radius: 16px; }", second)
        self.assertIn("BEGIN iArch session theme: forest-night", second)
        self.assertEqual(first, second)

    def test_kvantum_changes_only_existing_general_colors(self):
        source = (ROOT / ".config/Kvantum/iarch/iarch.kvconfig").read_text(encoding="utf-8")
        updated = session_theme.render_kvantum_config(source, self.pack)
        self.assertIn("highlight.color=#8FCB6A", updated)
        self.assertIn("[GeneralColors]", updated)
        self.assertIn("animate_states=true", updated)


if __name__ == "__main__":
    unittest.main()
