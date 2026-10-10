#!/usr/bin/env python3
"""macOS-style system settings, styled like the fuzzel menus.

Usage: settings-panel.py [page]    (running it again while it's open closes it)

A normal window: drag it by its top bar, close it with esc or the × (or Super+W).
Changes to the sway config are applied right away but kept as unsaved changes in
~/.config/sway/settings.conf until they're saved from the bar at the bottom (see dotconfig.py).

Keys: up/down (or j/k) pick a category, right/enter/tab go into it,
      esc/left go back to the sidebar, esc there closes, alt+1-5 jump to a group.
"""
import importlib
import os
import sys
from string import Template

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

SCRIPTS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPTS)
import dotconfig  # noqa: E402
from settings_pages.common import V, button, dialog, label, load_theme  # noqa: E402

APP_ID = "dev.dotfiles.SettingsPanel"
WAL = os.path.expanduser("~/.cache/wal")
WIDTH, HEIGHT = 980, 740

# (module in settings_pages, class, sidebar group) in sidebar order
PAGES = [
    ("network", "WifiPage", "connections"),
    ("bluetooth", "BluetoothPage", "connections"),
    ("tailscale", "TailscalePage", "connections"),
    ("sound", "SoundPage", "devices"),
    ("displays", "DisplayPage", "devices"),
    ("trackpad", "TrackpadPage", "devices"),
    ("keyboard", "KeyboardPage", "devices"),
    ("battery", "BatteryPage", "devices"),
    ("appearance", "AppearancePage", "personal"),
    ("wallpaper", "WallpaperPage", "personal"),
    ("toolbar", "ToolbarPage", "personal"),
    ("notifications", "NotificationsPage", "personal"),
    ("idle", "IdlePage", "system"),
    ("datetime", "DateTimePage", "system"),
    ("defaults", "DefaultAppsPage", "system"),
    ("windowrules", "WindowRulesPage", "system"),
    ("storage", "StoragePage", "system"),
    ("packages", "PackagesPage", "manage"),
    ("maintenance", "MaintenancePage", "manage"),
    ("dotfiles", "DotfilesPage", "manage"),
    ("backups", "BackupsPage", "manage"),
    ("about", "AboutPage", "manage"),
]

CSS = """
window.settings-panel, window.settings-dialog { background: $bg; }

.frame { background: $bg; color: $fg; }
window.settings-panel > .frame, window.settings-dialog > .frame { border: 1px solid $border; }
.frame, .frame *, popover.choices, popover.choices * {
    font-family: "BlexMono Nerd Font", monospace;
    font-size: 11pt;
    border-radius: 0;
    box-shadow: none;
    text-shadow: none;
    outline-style: none;
    -gtk-icon-shadow: none;
}
.frame label { color: inherit; }

.prompt { padding: 10px 16px 8px 16px; }
.hints, .footer { padding: 6px 16px 8px 16px; color: $dim; }
.hsep { background: $faint; min-height: 1px; }
.vsep { background: $faint; min-width: 1px; }
.dim, .detail { color: $dim; }
.warn { color: $c1; }
.accent { color: $accent; }
.mono { font-family: "BlexMono Nerd Font", monospace; }

/* sidebar: the fuzzel list. The selection is dimmed while the keyboard is in a page. */
list.sidebar { background: transparent; color: $fg; padding: 6px 8px; }
list.sidebar row { background: transparent; color: $fg; padding: 1px 8px; min-height: 0; }
list.sidebar row:hover { background: $hover; }
list.sidebar row:selected { background: $faint; color: $fg; }
list.sidebar .group { color: $dim; font-size: 9pt; padding: 8px 8px 1px 8px; }
list.sidebar row:first-child .group { padding-top: 2px; }
list.sidebar:focus-within row:selected { background: $sel; color: $sel_fg; }
list.sidebar:focus-within row:selected .dim { color: $sel_fg; }

scrolledwindow, viewport { background: transparent; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: $faint; border: none; min-width: 4px; min-height: 4px; }

.page { padding: 8px 12px 16px 12px; }
.section-row { margin-top: 14px; padding: 0 8px; }
.page > .section-row:first-child { margin-top: 0; }
.section { color: $accent; font-weight: bold; }
.row { padding: 3px 8px; min-height: 22px; }

/* the unsaved changes bar */
.pending-bar { background: $hover; border-top: 1px solid $faint; padding: 4px 12px; }
.pending-bar label.count { color: $accent; font-weight: bold; }

/* text buttons, toggles, dropdowns and list items: fuzzel's selection colors when focused */
button.flat, button.toggle, button.item, button.tab, menubutton.choice > button {
    background: transparent;
    color: $fg;
    border: none;
    padding: 2px 8px;
    min-height: 0;
    min-width: 0;
}
button.toggle { color: $dim; }
button.toggle.on { color: $accent; font-weight: bold; }
button.item { padding: 3px 8px; }
button.tab { color: $dim; }
button.tab.on { color: $accent; font-weight: bold; }
button.flat:hover, button.toggle:hover, button.item:hover, button.tab:hover, menubutton.choice > button:hover { background: $hover; }
button.flat:focus-visible, button.toggle:focus-visible, button.item:focus-visible,
menubutton.choice > button:focus-visible {
    background: $sel;
    color: $sel_fg;
}
button.item:focus-visible .detail { color: $sel_fg; }
button:disabled { color: $dim; }
button.danger { color: $c1; }

popover.choices > contents { background: $bg; color: $fg; border: 1px solid $border; padding: 4px; }
popover.choices button.item { color: $fg; }

scale { padding: 8px 0; min-height: 0; }
scale trough { background: $faint; border: none; margin: 0; min-height: 4px; }
scale highlight { background: $accent; border: none; margin: 0; min-width: 0; min-height: 4px; }
scale slider { background: $fg; border: none; min-width: 10px; min-height: 10px; margin: -3px; }
scale:hover slider { background: $accent; }
scale:focus-visible slider { background: $sel; }
.row:focus-within > .title, .row:focus-within .title { color: $accent; }

levelbar trough { background: $faint; border: none; padding: 0; min-height: 6px; }
levelbar block { border: none; min-height: 6px; }
levelbar block.filled { background: $accent; }
levelbar block.empty { background: transparent; }

entry, spinbutton { background: $bg; color: $fg; border: 1px solid $faint; padding: 2px 6px; min-height: 0; }
entry:focus-within, spinbutton:focus-within { border-color: $border; }
spinbutton button { background: transparent; border: none; color: $dim; min-height: 0; padding: 0 4px; }
textview.diff, textview.diff text { background: $bg; color: $fg; font-family: "BlexMono Nerd Font", monospace; font-size: 10pt; }

flowbox, flowboxchild { background: transparent; }
flowboxchild { padding: 2px; border: 1px solid transparent; }
flowboxchild:hover { border-color: $faint; }
flowboxchild:selected, flowboxchild.current { border-color: $accent; }
flowbox:focus-within flowboxchild:selected { background: $sel; border-color: $sel; }
.grid { padding: 4px 4px 12px 4px; }
/* the wallpaper gallery's source link, under its categories */
.credit { padding: 6px 16px 8px 16px; }
.credit link { color: $accent; text-decoration: underline; }
.credit link:hover { color: $fg; }
"""


class Panel(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Settings", css_classes=["settings-panel"],
                         decorated=False, default_width=WIDTH, default_height=HEIGHT)
        self.app = app
        self.current = None
        self.flash_timer = 0

        frame = Gtk.Box(orientation=V, css_classes=["frame"])
        header = Gtk.Box(spacing=8)
        self.prompt = label("settings", "prompt", hexpand=True)
        header.append(self.prompt)
        close = Gtk.Button(label="×", css_classes=["tab"], focusable=False, tooltip_text="Close (Esc)",
                           valign=Gtk.Align.CENTER, margin_end=8)
        close.connect("clicked", lambda _: self.close())
        header.append(close)
        frame.append(Gtk.WindowHandle(child=header))  # drag the window by its top bar
        frame.append(Gtk.Box(css_classes=["hsep"]))

        body = Gtk.Box(vexpand=True)
        self.sidebar = Gtk.ListBox(css_classes=["sidebar"], selection_mode=Gtk.SelectionMode.BROWSE)
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.pages = []
        self.group_starts = []  # index of the first page in each group, for alt+number
        for module_name, class_name, group in PAGES:
            try:
                cls = getattr(importlib.import_module(f"settings_pages.{module_name}"), class_name)
                page = cls(self)
            except Exception as e:  # one broken page shouldn't take the panel down
                print(f"settings: {module_name}: {e!r}", file=sys.stderr)
                continue
            if not self.pages or self.pages[-1].group != group:
                self.group_starts.append(len(self.pages))
            page.group = group
            self.pages.append(page)
            self.sidebar.append(Gtk.ListBoxRow(child=label(page.name)))
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=page)
            page.scroller = scroller
            self.stack.add_named(scroller, page.name)
        self.sidebar.connect("row-selected", self._row_selected)
        self.sidebar.set_header_func(self._group_header)
        sidebar_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.sidebar,
                                              width_request=190)
        body.append(sidebar_scroller)
        body.append(Gtk.Box(css_classes=["vsep"]))
        body.append(self.stack)
        frame.append(body)

        # unsaved changes: shown only while there are some
        self.pending_bar = Gtk.Box(spacing=8, css_classes=["pending-bar"], visible=False)
        self.pending_count = label("", "count")
        self.pending_text = label("", "dim", hexpand=True, ellipsize=True)
        self.pending_bar.append(self.pending_count)
        self.pending_bar.append(self.pending_text)
        for text, action in (("review", self.review_pending), ("discard", self.discard_pending),
                             ("save", self.save_pending)):
            self.pending_bar.append(button(text, action))
        frame.append(self.pending_bar)

        frame.append(Gtk.Box(css_classes=["hsep"]))
        self.hints = label("↑↓ category   → open   ← back   esc close", "hints")
        frame.append(self.hints)
        self.set_child(frame)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        self.update_pending()

    # ----- pages -----

    def _group_header(self, row, before):
        """A group title above the first page of each group."""
        group = self.pages[row.get_index()].group
        if before is None or self.pages[before.get_index()].group != group:
            row.set_header(label(group, "group"))
        else:
            row.set_header(None)

    def show_page(self, name):
        index = next((i for i, page in enumerate(self.pages) if page.name == name
                      or type(page).__module__.endswith("." + (name or ""))), 0)
        self.select(index)

    def select(self, index):
        row = self.sidebar.get_row_at_index(max(0, min(index, len(self.pages) - 1)))
        if row:
            self.sidebar.select_row(row)
            row.grab_focus()

    def _row_selected(self, _, row):
        if row is None or self.pages[row.get_index()] is self.current:
            return
        if self.current:
            self.current.hidden()
        self.current = self.pages[row.get_index()]
        self.stack.set_visible_child_name(self.current.name)
        self.prompt.set_label(f"settings > {self.current.name}")
        self.current.shown()

    def focus_sidebar(self):
        self.sidebar.get_selected_row().grab_focus()

    def focus_page(self):
        # pages with nothing to focus keep the keyboard in the sidebar
        if not self.stack.get_visible_child().child_focus(Gtk.DirectionType.TAB_FORWARD):
            self.focus_sidebar()

    # ----- unsaved changes -----

    def update_pending(self):
        count = dotconfig.pending_count()
        self.pending_bar.set_visible(bool(count))
        if count:
            self.pending_count.set_label(f"{count} unsaved change{'s' if count != 1 else ''}")
            self.pending_text.set_label("  ·  ".join(dotconfig.pending_summary()))

    def flash(self, text, seconds=6):
        """Show a short message where the key hints are."""
        self.hints.set_label(text)
        if self.flash_timer:
            GLib.source_remove(self.flash_timer)

        def reset():
            self.flash_timer = 0
            self.hints.set_label("↑↓ category   → open   ← back   esc close")
            return False

        self.flash_timer = GLib.timeout_add_seconds(seconds, reset)

    def review_pending(self):
        view = Gtk.TextView(editable=False, monospace=True, css_classes=["diff"], left_margin=12,
                            right_margin=12, top_margin=8, bottom_margin=8)
        buffer = view.get_buffer()
        theme = load_theme()
        tags = {"+": buffer.create_tag(foreground=theme["accent"]), "-": buffer.create_tag(foreground=theme["c1"]),
                "@": buffer.create_tag(foreground=theme["dim"])}
        for line in (dotconfig.full_diff() or "no changes\n").splitlines(True):
            tag = tags.get(line[:1]) if not line.startswith(("+++", "---")) else tags["@"]
            end = buffer.get_end_iter()
            if tag:
                buffer.insert_with_tags(end, line, tag)
            else:
                buffer.insert(end, line)
        scroller = Gtk.ScrolledWindow(child=view, min_content_height=380)
        dialog(self, "unsaved changes", scroller, [("close", None), ("discard", "discard"), ("save", "save")],
               lambda r: self.save_pending() if r == "save" else self.discard_pending() if r == "discard" else None,
               width=760, height=520)

    def save_pending(self):
        ok, message = dotconfig.save_all()
        self.flash(message if not ok else f"saved · the old config is in {dotconfig.BACKUPS.replace(os.path.expanduser('~'), '~')}")
        self.update_pending()
        if self.current:
            self.current.refresh()

    def discard_pending(self):
        dotconfig.discard_all()
        self.flash("changes discarded")
        self.update_pending()
        if self.current:
            self.current.refresh()

    # ----- keys -----

    def _key_pressed(self, _, keyval, _keycode, state):
        name = Gdk.keyval_name(keyval) or ""
        mods = state & Gtk.accelerator_get_default_mod_mask()
        focus = self.get_focus()
        row = self.sidebar.get_selected_row()
        index = row.get_index() if row else 0
        # GTK only turns on focus rings for keys it handles itself, and these get caught first
        self.set_focus_visible(True)

        if mods == Gdk.ModifierType.ALT_MASK and len(name) == 1 and name in "123456789":
            if int(name) <= len(self.group_starts):
                self.select(self.group_starts[int(name) - 1])
            return True
        if mods == Gdk.ModifierType.CONTROL_MASK and name == "s" and dotconfig.pending_count():
            self.save_pending()
            return True

        in_sidebar = focus is None or focus.is_ancestor(self.sidebar)
        if in_sidebar and not mods:
            if name == "Escape":
                self.close()
            elif name in ("Up", "k"):
                self.select(index - 1)
            elif name in ("Down", "j"):
                self.select(index + 1)
            elif name == "Home":
                self.select(0)
            elif name == "End":
                self.select(len(self.pages) - 1)
            elif name in ("Right", "l", "Return", "KP_Enter", "Tab"):
                self.focus_page()
            else:
                return False
            return True

        if name == "Escape":
            if not self.current.escape(focus):
                self.focus_sidebar()
            return True
        if handler := getattr(self.current, "handle_key", None):
            if handler(keyval, state):
                return True
        if mods:
            return False
        # sliders would take up/down as value changes; keep those for moving between rows
        if name in ("Up", "Down") and isinstance(focus, Gtk.Scale):
            self.emit("move-focus", Gtk.DirectionType.UP if name == "Up" else Gtk.DirectionType.DOWN)
            return True
        if name == "Left" and not self.uses_left(focus):
            self.focus_sidebar()
            return True
        return False

    @staticmethod
    def uses_left(focus):
        """Whether left arrow means something to the focused widget, instead of going back to the sidebar."""
        if isinstance(focus, (Gtk.Scale, Gtk.Text)):
            return True
        grid = focus.get_ancestor(Gtk.FlowBox) if focus else None
        return grid is not None and focus.get_index() % grid.get_max_children_per_line() != 0


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.css = Gtk.CssProvider()
        self.theme_monitor = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.load_css()
        # above ~/.config/gtk-4.0/gtk.css, which is also generated by pywal
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.theme_monitor = Gio.File.new_for_path(WAL).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.theme_monitor.connect("changed", lambda _m, f, *_: f.get_basename() == "colors.json"
                                   and GLib.timeout_add(200, lambda: self.load_css() or False))

    def load_css(self):
        self.css.load_from_string(Template(CSS).substitute(load_theme()))

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        page = args[0] if args else None
        if page in ("-h", "--help"):
            command_line.print_literal(__doc__)
        elif self.window is None:
            self.window = Panel(self)
            self.window.connect("close-request", lambda *_: self.quit() or False)
            self.window.present()
            self.window.show_page(page)
        elif page and self.window.current and page != self.window.current.name:
            self.window.show_page(page)
            self.window.present()
        else:
            self.quit()
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
