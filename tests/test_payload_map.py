"""Prove which files the v5 Hyprland session loads, and that the payload is closed.

Two independent facts are asserted from the repository itself:

1. the load graph -- every ``require()`` reachable from ``hyprland.lua`` resolves
   to a file that exists, reaches every Lua file that ships, and the scripts the
   keybindings exec exist too;
2. the payload -- the tree ``lib/stage-v5-config.sh`` builds equals an explicit
   list, and nothing the legacy v4 session owns can appear in it.

Keeping the list explicit is the point: adding a file to ``.config`` without
teaching the staging script about it, or dropping one it still copies, fails
here instead of silently changing what gets installed.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / '.config/hypr'
LEGACY_CONFIG = ROOT / 'legacy/config'
STAGE_SCRIPT = ROOT / 'lib/stage-v5-config.sh'

# Everything the v5 installer deploys, relative to the staged root.
EXPECTED_PAYLOAD = {
    'fastfetch/config.jsonc',
    'fastfetch/logo/agk_clan.icon',
    'fastfetch/logo/aisaka.icon',
    'fastfetch/logo/geass.icon',
    'fastfetch/logo/hyprland.icon',
    'fastfetch/logo/loli.icon',
    'fastfetch/logo/pochita.icon',
    'fastfetch/logo/ryuzaki.icon',
    'fish/config.fish',
    'hypr/Scripts/browser-launcher.sh',
    'hypr/Scripts/workspace.sh',
    'hypr/animations.lua',
    'hypr/animations/default.lua',
    'hypr/generated/glass.lua',
    'hypr/hyprland.lua',
    'hypr/inputs.lua',
    'hypr/keybind.lua',
    'hypr/monitors.lua',
    'hypr/startup.lua',
    'hypr/themes/theme.lua',
    'hypr/windowrules.lua',
    'kitty/kitty.conf',
    'kitty/minima-colors.conf',
    'kitty/minima-profile.conf',
    'gtk-3.0/gtk.css',
    'gtk-4.0/gtk.css',
    'noctalia/config.toml',
    # One palette per colour preset: iarch-theme apply <preset> points
    # theme.custom_palette at that preset's palette, so all of them ship.
    'noctalia/palettes/iarch-aurora.json',
    'noctalia/palettes/iarch-crimson-plasma.json',
    'noctalia/palettes/iarch-frosted-light.json',
    'noctalia/palettes/iarch-midnight.json',
    'noctalia/palettes/iarch-mono-ice.json',
    'noctalia/palettes/iarch-tokyo-night.json',
    'starship.toml',
}


def module_paths(module: str):
    """Resolve a Lua module name the way the package.path in hyprland.lua does."""
    relative = module.replace('.', '/')
    return (HYPR / f'{relative}.lua', HYPR / relative / 'init.lua')


def required_modules(text: str):
    return re.findall(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text)


def load_graph(entry: Path):
    """Walk require() from entry and return (reached files, unresolved names)."""
    reached, unresolved, pending = set(), set(), [entry]
    while pending:
        current = pending.pop()
        reached.add(current)
        for module in required_modules(current.read_text(encoding='utf-8')):
            for candidate in module_paths(module):
                if candidate.is_file():
                    if candidate not in reached:
                        pending.append(candidate)
                    break
            else:
                unresolved.add(module)
    return reached, unresolved


class HyprlandLoadGraph(unittest.TestCase):
    def test_every_require_resolves_and_reaches_every_shipped_lua_file(self):
        entry = HYPR / 'hyprland.lua'
        self.assertTrue(entry.is_file(), 'hyprland.lua is the session entry point')
        reached, unresolved = load_graph(entry)
        self.assertEqual(set(), unresolved, 'require() targets that resolve to no file')
        shipped = {p for p in HYPR.rglob('*.lua') if p.is_file()}
        self.assertEqual(shipped, reached,
                         'Lua files that ship but are never required, or vice versa')

    def test_scripts_executed_by_keybindings_exist(self):
        keybind = (HYPR / 'keybind.lua').read_text(encoding='utf-8')
        scripts = set(re.findall(r'scrPath\s*\.\.\s*"/([^"]+)"', keybind))
        self.assertTrue(scripts, 'keybind.lua is expected to exec helper scripts')
        for script in sorted(scripts):
            path = HYPR / 'Scripts' / script
            self.assertTrue(path.is_file(), f'keybind.lua execs a missing script: {script}')

    def test_no_hyprlang_file_ships_next_to_the_lua_configuration(self):
        leftovers = sorted(str(p.relative_to(HYPR)) for p in HYPR.rglob('*.conf'))
        self.assertEqual([], leftovers,
                         'Hyprlang files beside the Lua payload are not loaded by v5; '
                         'they belong under legacy/config/hypr/')


class StagedPayload(unittest.TestCase):
    def stage(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / 'stage'
        dest.mkdir()
        result = subprocess.run(['bash', str(STAGE_SCRIPT), str(ROOT / '.config'), str(dest)],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return {str(p.relative_to(dest)) for p in dest.rglob('*') if p.is_file()}

    def test_payload_is_exactly_the_expected_file_list(self):
        staged = self.stage()
        self.assertEqual(EXPECTED_PAYLOAD, staged)

    def test_legacy_v4_files_cannot_reach_the_payload(self):
        staged = self.stage()
        self.assertTrue(LEGACY_CONFIG.is_dir(), 'legacy/config holds the v4-only payload')
        legacy = {str(p.relative_to(LEGACY_CONFIG)) for p in LEGACY_CONFIG.rglob('*') if p.is_file()}
        self.assertTrue(legacy, 'legacy/config unexpectedly holds no files')
        self.assertEqual(set(), legacy & staged,
                         'a file the legacy v4 session owns was staged into the v5 payload')

    def test_staging_script_names_the_same_files_as_this_test(self):
        # The list inside the staging script is the deployment source of truth;
        # if it drifts from EXPECTED_PAYLOAD the two checks above can both pass
        # while the installer ships something else.
        text = STAGE_SCRIPT.read_text(encoding='utf-8')
        listed = set(re.search(r'for path in (.+?); do', text, re.S).group(1).split())
        expanded = set()
        for entry in listed:
            if (ROOT / '.config' / entry).is_dir():
                expanded |= {str(p.relative_to(ROOT / '.config'))
                             for p in (ROOT / '.config' / entry).rglob('*') if p.is_file()}
            else:
                expanded.add(entry)
        self.assertEqual(EXPECTED_PAYLOAD, expanded)


if __name__ == '__main__':
    unittest.main()
