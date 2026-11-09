#!/usr/bin/env python3
"""minimaLinux's session customization center (GTK 3)."""
import argparse
import configparser
import json
import os
import sys
from pathlib import Path

import backend


def main():
    parser = argparse.ArgumentParser(description='minimaLinux customization center')
    parser.add_argument('--welcome-once', action='store_true')
    parser.add_argument('--shortcuts', action='store_true')
    args = parser.parse_args()
    state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'minimalinux/welcome-shown'
    if args.welcome_once and state.exists():
        return 0
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GdkPixbuf
    except (ImportError, ValueError) as exc:
        print(f'Customization Center requires python-gobject and GTK 3: {exc}', file=sys.stderr)
        return 1
    initialized, _ = Gtk.init_check([])
    if not initialized:
        print('Customization Center requires a graphical session.', file=sys.stderr)
        return 1

    class Center(Gtk.Window):
        def __init__(self):
            super().__init__(title='minimaLinux · Customize')
            self.set_default_size(820, 650)
            self.set_border_width(18)
            self.connect('destroy', Gtk.main_quit)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(outer)
            title = Gtk.Label()
            title.set_markup('<span size="x-large" weight="bold">Make minimaLinux yours</span>')
            title.set_xalign(0)
            outer.pack_start(title, False, False, 0)
            subtitle = Gtk.Label(label='Choose your look, discover shortcuts, and set up your desktop.')
            subtitle.set_xalign(0)
            outer.pack_start(subtitle, False, False, 0)
            self.notebook = Gtk.Notebook()
            self.notebook.set_scrollable(True)
            outer.pack_start(self.notebook, True, True, 0)
            self.status = Gtk.Label(label='Changes stay in your minimaLinux session.')
            self.status.set_xalign(0)
            self.status.set_line_wrap(True)
            try:
                self.current = json.loads((backend.ROOT / 'noctalia/settings.json').read_text(encoding='utf-8'))
                if not isinstance(self.current, dict):
                    self.current = {}
            except (OSError, ValueError):
                self.current = {}
            outer.pack_start(self.status, False, False, 0)
            self.welcome_page()
            self.appearance_page()
            self.wallpaper_page()
            self.terminal_page()
            self.desktop_page()
            self.shortcuts_page()
            self.apps_page()
            if args.shortcuts:
                self.notebook.set_current_page(5)

        def page(self, label):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_border_width(16)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.add(box)
            self.notebook.append_page(scroll, Gtk.Label(label=label))
            return box

        def label(self, box, text):
            label = Gtk.Label(label=text)
            label.set_xalign(0)
            label.set_line_wrap(True)
            box.pack_start(label, False, False, 0)
            return label

        def button(self, box, label, callback):
            button = Gtk.Button(label=label)
            button.set_halign(Gtk.Align.START)
            button.connect('clicked', lambda *_: self.run(callback))
            box.pack_start(button, False, False, 0)
            return button

        def run(self, callback):
            try:
                result = callback()
                if result:
                    self.status.set_text(result)
            except (OSError, ValueError, RuntimeError) as exc:
                self.status.set_text('Could not apply: ' + str(exc))

        def combo(self, box, label, values, active=0):
            self.label(box, label)
            control = Gtk.ComboBoxText()
            for value in values:
                control.append_text(value)
            control.set_active(active)
            box.pack_start(control, False, False, 0)
            return control

        def welcome_page(self):
            box = self.page('Welcome')
            self.label(box, 'Welcome! This is your setup wizard and customization center. You can return any time with Super+K.')
            self.label(box, '1. Choose a theme, icons and font in Appearance.\n2. Pick a wallpaper and terminal profile.\n3. Explore shortcuts or install optional apps.')
            self.label(box, 'Quick start: Super+Return opens a terminal; Super+D opens the app launcher; Super+H searches shortcuts; Super+Shift+M logs out.')
            self.button(box, 'Start setup → Appearance', lambda: self.notebook.set_current_page(1))
            self.button(box, 'Show keyboard shortcuts', lambda: self.notebook.set_current_page(5))

        def appearance_page(self):
            box = self.page('Appearance')
            self.label(box, 'Choose a coordinated color scheme, GTK icon pack and desktop font.')
            names = list(backend.THEMES)
            colors = self.current.get('colorSchemes', {})
            selected = next((name for name, value in backend.THEMES.items() if value['scheme'] == colors.get('predefinedScheme') and value['dark'] == colors.get('darkMode', True)), 'Tokyo Night')
            self.theme = self.combo(box, 'Color scheme', names, names.index(selected))
            preview = self.label(box, '')
            def update_preview(*_):
                preset = backend.THEMES[self.theme.get_active_text()]
                preview.set_text('Preview: background #' + preset['bg'] + '  •  accent #' + preset['accent'] + '  •  text #' + preset['fg'] + '\nComponents: Noctalia, Hyprland border, Kitty colors, GTK preference.')
            self.theme.connect('changed', update_preview)
            update_preview()
            icon_names = list(backend.ICONS)
            gtk = configparser.ConfigParser(interpolation=None)
            gtk.read(backend.ROOT / 'gtk-3.0/settings.ini', encoding='utf-8')
            icon_value = gtk.get('Settings', 'gtk-icon-theme-name', fallback='Papirus-Dark')
            icon_name = next((name for name, value in backend.ICONS.items() if value == icon_value), 'Papirus Dark')
            self.icon = self.combo(box, 'Icon pack', icon_names, icon_names.index(icon_name))
            self.label(box, 'GTK application font')
            self.font = Gtk.FontButton.new_with_font(gtk.get('Settings', 'gtk-font-name', fallback='Noto Sans 10'))
            box.pack_start(self.font, False, False, 0)
            def apply():
                warnings = backend.theme(self.theme.get_active_text(), backend.ICONS[self.icon.get_active_text()], self.font.get_font_name())
                suffix = (' Skipped: ' + '; '.join(warnings) + '.') if warnings else ''
                return 'Theme saved. Restart applications and terminals for GTK and Kitty changes.' + suffix
            self.button(box, 'Apply appearance', apply)
            self.label(box, 'GTK 4/libadwaita and sandboxed apps may use their own theme. Noctalia colors follow the selected scheme, not the wallpaper.')

        def wallpaper_page(self):
            box = self.page('Wallpaper')
            self.label(box, 'Choose an image for all monitors. Your lock screen uses the same wallpaper.')
            self.file = Gtk.FileChooserButton(title='Choose a wallpaper', action=Gtk.FileChooserAction.OPEN)
            image_filter = Gtk.FileFilter()
            image_filter.set_name('Images')
            image_filter.add_pixbuf_formats()
            self.file.add_filter(image_filter)
            box.pack_start(self.file, False, False, 0)
            self.preview = Gtk.Image()
            box.pack_start(self.preview, False, False, 0)
            def preview(control):
                path = control.get_filename()
                if path:
                    try:
                        self.preview.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 400, 220, True))
                    except Exception:
                        self.preview.clear()
            self.file.connect('file-set', preview)
            def apply():
                path = self.file.get_filename()
                if not path or not Path(path).is_file():
                    raise ValueError('Choose an existing image first.')
                backend.ipc('wallpaper', 'set', path, 'all')
                return 'Wallpaper sent to Noctalia for all monitors. Keep the image at this path.'
            self.button(box, 'Set wallpaper', apply)
            self.button(box, 'Open Noctalia wallpaper picker', lambda: (backend.ipc('wallpaper', 'toggle') or 'Opened wallpaper picker.'))
            self.label(box, 'Noctalia must be running. For wallpaper-generated colors, enable “use wallpaper colors” in Noctalia settings.')

        def terminal_page(self):
            box = self.page('Terminal')
            self.label(box, 'Choose a Kitty font, size and Fish prompt for new terminals.')
            profiles = ['JetBrains Mono', 'Monospace']
            theme_names = list(backend.THEMES)
            try:
                color_file = (backend.ROOT / 'kitty/minima-colors.conf').read_text(encoding='utf-8')
                color_name = color_file.splitlines()[0].removeprefix('# ').split(' — ')[0]
                profile_file = (backend.ROOT / 'kitty/minima-profile.conf').read_text(encoding='utf-8')
                prompt_file = (backend.ROOT / 'fish/conf.d/minimalinux-prompt.fish').read_text(encoding='utf-8')
            except OSError:
                color_name, profile_file, prompt_file = '', '', ''
            self.term_theme = self.combo(box, 'Terminal colors', theme_names, theme_names.index(color_name) if color_name in theme_names else 0)
            self.term_font = self.combo(box, 'Terminal font', profiles, 1 if 'font_family monospace' in profile_file else 0)
            self.label(box, 'Font size (8–24)')
            self.size = Gtk.SpinButton.new_with_range(8, 24, 0.5)
            try:
                font_size = next(float(line.split()[1]) for line in profile_file.splitlines() if line.startswith('font_size '))
            except (ValueError, StopIteration, IndexError):
                font_size = 11.5
            self.size.set_value(font_size)
            box.pack_start(self.size, False, False, 0)
            self.prompt = self.combo(box, 'Starship prompt', ['Detailed', 'Minimal'], 1 if 'starship-minimal.toml' in prompt_file else 0)
            def apply():
                backend.terminal_profile(self.term_font.get_active_text(), self.size.get_value(), self.prompt.get_active_text())
                backend.terminal_colors(self.term_theme.get_active_text())
                return 'Terminal profile saved. Open a new Kitty window to use it.'
            self.button(box, 'Apply terminal profile', apply)
            self.label(box, 'Fish: Right accepts suggestions, Tab completes, Ctrl+R searches history, and z jumps to recent directories.')

        def desktop_page(self):
            box = self.page('Bar & lock')
            self.label(box, 'Adjust Noctalia’s bar and lock screen. The lock screen uses your wallpaper and system authentication.')
            positions = ['top', 'bottom', 'left', 'right']
            densities = ['comfortable', 'default', 'compact']
            clocks = ['digital', 'analog', 'custom']
            bar = self.current.get('bar', {})
            general = self.current.get('general', {})
            self.bar_pos = self.combo(box, 'Bar position', positions, positions.index(bar.get('position')) if bar.get('position') in positions else 0)
            self.density = self.combo(box, 'Bar density', densities, densities.index(bar.get('density')) if bar.get('density') in densities else 0)
            self.clock = self.combo(box, 'Lock screen clock', clocks, clocks.index(general.get('clockStyle')) if general.get('clockStyle') in clocks else 0)
            self.avatar = Gtk.FileChooserButton(title='Choose an avatar (optional)', action=Gtk.FileChooserAction.OPEN)
            box.pack_start(self.avatar, False, False, 0)
            def apply():
                general = {'clockStyle': self.clock.get_active_text()}
                if self.avatar.get_filename():
                    general['avatarImage'] = self.avatar.get_filename()
                backend.desktop_settings({'bar': {'position': self.bar_pos.get_active_text(), 'density': self.density.get_active_text()}, 'general': general})
                return 'Bar and lock screen settings saved. Noctalia reloads its settings.'
            self.button(box, 'Apply bar and lock settings', apply)
            self.button(box, 'Open advanced Noctalia settings', lambda: (backend.ipc('settings', 'toggle') or 'Opened Noctalia settings.'))
            self.label(box, 'Use advanced Noctalia settings to choose bar widgets, system stats, and power controls.')

        def shortcuts_page(self):
            box = self.page('Shortcuts')
            self.label(box, 'Search the keybindings in your current Hyprland configuration.')
            search = Gtk.SearchEntry()
            box.pack_start(search, False, False, 0)
            result = Gtk.ListBox()
            result.set_selection_mode(Gtk.SelectionMode.NONE)
            box.pack_start(result, False, False, 0)
            def refresh(*_):
                for child in result.get_children():
                    result.remove(child)
                query = search.get_text().casefold()
                try:
                    rows = backend.shortcuts()
                except OSError as exc:
                    self.status.set_text('Could not read shortcuts: ' + str(exc))
                    rows = []
                for keys, description in rows:
                    if query not in (keys + ' ' + description).casefold():
                        continue
                    row = Gtk.Label(label=f'{keys}  —  {description}')
                    row.set_xalign(0)
                    row.set_margin_top(5)
                    row.set_margin_bottom(5)
                    result.add(row)
                result.show_all()
            search.connect('search-changed', refresh)
            refresh()

        def apps_page(self):
            box = self.page('Optional apps')
            self.label(box, 'Select optional Arch packages. Installation opens a terminal and asks for sudo confirmation; nothing is installed automatically.')
            self.app_checks = {}
            for name in backend.OPTIONAL_APPS:
                check = Gtk.CheckButton(label=name + ' (' + backend.OPTIONAL_APPS[name] + ')')
                box.pack_start(check, False, False, 0)
                self.app_checks[name] = check
            def install():
                backend.install_optional([name for name, check in self.app_checks.items() if check.get_active()])
                return 'Package installation opened in Kitty. Review the pacman prompt and result there.'
            self.button(box, 'Install selected apps…', install)

    window = Center()
    window.show_all()
    if args.welcome_once:
        try:
            backend.write(state, 'shown\n')
        except OSError as exc:
            print(f'Could not save welcome state: {exc}', file=sys.stderr)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
