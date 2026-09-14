#!/usr/bin/env python3
"""macOS-style system settings popup, styled like the fuzzel menus.

Usage: settings-panel.py [page]    (running it again while it's open closes it)

Keys: up/down (or j/k) pick a category, right/enter/tab go into it,
      esc/left go back to the sidebar, esc there closes, alt+1-9 jump to a category.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from ctypes import CDLL
from string import Template

# gtk4-layer-shell has to be loaded before libwayland-client, i.e. before Gtk
CDLL("libgtk4-layer-shell.so.0")

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from gi.repository import Gtk4LayerShell as LayerShell

APP_ID = "dev.dotfiles.SettingsPanel"
WAL = os.path.expanduser("~/.cache/wal")
WIDTH, HEIGHT = 780, 500
V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL

#############
### THEME ###
#############


def lighten(color, amount):
    """pywal's lighten(): move each channel `amount` of the way to white."""
    rgb = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * amount) for c in rgb)


def load_theme():
    """The fuzzel colors: pywal's palette, then fuzzel's own border/selection colors on top."""
    theme = {"bg": "#1b1c19", "fg": "#c6c6c5", "accent": "#897130", "dim": "#6a745f",
             "border": "#896822", "sel": "#896822", "sel_fg": "#1b1c19"}
    try:
        with open(f"{WAL}/colors.json") as f:
            wal = json.load(f)
        special, colors = wal["special"], wal["colors"]
        theme.update(bg=special["background"], fg=special["foreground"], accent=colors["color2"],
                     dim=colors["color8"], border=colors["color1"], sel=colors["color1"],
                     sel_fg=special["background"])
    except (OSError, KeyError, ValueError):
        pass
    fuzzel_keys = {"border": "border", "selection": "sel", "selection-text": "sel_fg"}
    try:
        with open(f"{WAL}/colors-fuzzel.ini") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key in fuzzel_keys and len(value) >= 6:
                    theme[fuzzel_keys[key]] = "#" + value[:6]
    except OSError:
        pass
    theme["faint"] = lighten(theme["bg"], 0.10)  # waybar's bracket color
    theme["hover"] = lighten(theme["bg"], 0.05)
    return theme


CSS = """
window.settings-panel { background: transparent; }

.frame { background: $bg; color: $fg; border: 1px solid $border; }
.frame, .frame * {
    font-family: "BlexMono Nerd Font", monospace;
    font-size: 11pt;
    border-radius: 0;
    box-shadow: none;
    text-shadow: none;
    outline-style: none;
    -gtk-icon-shadow: none;
}
.frame label { color: inherit; }

.prompt { padding: 12px 16px 8px 16px; }
.hints { padding: 6px 16px 8px 16px; color: $dim; }
.hsep { background: $faint; min-height: 1px; }
.vsep { background: $faint; min-width: 1px; }
.dim, .detail { color: $dim; }

/* sidebar: the fuzzel list. The selection is dimmed while the keyboard is in a page. */
list.sidebar { background: transparent; color: $fg; padding: 8px 8px 8px 8px; }
list.sidebar row { background: transparent; color: $fg; padding: 3px 8px; min-height: 0; }
list.sidebar row:hover { background: $hover; }
list.sidebar row:selected { background: $faint; color: $fg; }
list.sidebar:focus-within row:selected { background: $sel; color: $sel_fg; }

scrolledwindow, viewport { background: transparent; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: $faint; border: none; min-width: 4px; min-height: 4px; }

.page { padding: 8px 12px 12px 12px; }
.section-row { margin-top: 12px; padding: 0 8px; }
.page > .section-row:first-child { margin-top: 0; }
.section { color: $accent; font-weight: bold; }
.row { padding: 3px 8px; min-height: 22px; }

/* text buttons, toggles and list items: fuzzel's selection colors when focused */
button.flat, button.toggle, button.item {
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
button.flat:hover, button.toggle:hover, button.item:hover { background: $hover; }
button.flat:focus-visible, button.toggle:focus-visible, button.item:focus-visible {
    background: $sel;
    color: $sel_fg;
}
button.item:focus-visible .detail { color: $sel_fg; }
button:disabled { color: $dim; }

scale { padding: 8px 0; min-height: 0; }
scale trough { background: $faint; border: none; margin: 0; min-height: 4px; }
scale highlight { background: $accent; border: none; margin: 0; min-width: 0; min-height: 4px; }
scale slider { background: $fg; border: none; min-width: 10px; min-height: 10px; margin: -3px; }
scale:hover slider { background: $accent; }
scale:focus-visible slider { background: $sel; }
.row:focus-within > .title { color: $accent; }

levelbar trough { background: $faint; border: none; padding: 0; min-height: 6px; }
levelbar block { border: none; min-height: 6px; }
levelbar block.filled { background: $accent; }
levelbar block.empty { background: transparent; }

entry { background: $bg; color: $fg; border: 1px solid $faint; padding: 2px 6px; min-height: 0; }
entry:focus-within { border-color: $border; }

flowbox, flowboxchild { background: transparent; }
flowboxchild { padding: 3px; border: 1px solid transparent; }
flowboxchild:hover { border-color: $faint; }
flowboxchild.current { border-color: $accent; }
flowboxchild:focus-visible { background: $sel; border-color: $sel; }
"""

###############
### HELPERS ###
###############


def run(*cmd, timeout=10):
    """Run a command and return its stdout ('' if it failed or isn't installed)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def run_ok(*cmd, timeout=30):
    """Run a command and return (succeeded, its last line of output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    lines = (p.stderr.strip() or p.stdout.strip()).splitlines()
    return p.returncode == 0, lines[-1] if lines else ""


def spawn(*cmd):
    """Start a program that outlives the panel."""
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def in_background(work, done=None):
    """Run work() on a thread, then done(result) back on the GTK thread."""
    def target():
        result = work()
        if done:
            GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=target, daemon=True).start()


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


###############
### WIDGETS ###
###############


def label(text="", *classes, xalign=0.0, hexpand=False, ellipsize=False):
    widget = Gtk.Label(label=text, xalign=xalign, hexpand=hexpand, css_classes=list(classes))
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    return widget


def button(text, on_click):
    widget = Gtk.Button(label=f"[ {text} ]", css_classes=["flat"], valign=Gtk.Align.CENTER)
    widget.connect("clicked", lambda _: on_click())
    return widget


def row(title, *end, sub=None):
    """A settings line: title (and an optional subtitle widget) on the left, controls on the right."""
    box = Gtk.Box(spacing=12, css_classes=["row"])
    text = Gtk.Box(orientation=V, hexpand=True, valign=Gtk.Align.CENTER)
    text.append(label(title, "title"))
    if sub is not None:
        text.append(sub)
    box.append(text)
    for widget in end:
        box.append(widget)
    return box


class Toggle(Gtk.Button):
    """A text switch, [on ] / [off]."""

    def __init__(self, on_change):
        super().__init__(css_classes=["toggle"], valign=Gtk.Align.CENTER)
        self.on_change = on_change
        self.active = False
        self.set_active(False)
        self.connect("clicked", self._clicked)

    def _clicked(self, _):
        self.set_active(not self.active)
        self.on_change(self.active)

    def set_active(self, active):
        self.active = active
        self.set_label("[on ]" if active else "[off]")
        (self.add_css_class if active else self.remove_css_class)("on")


class Slider(Gtk.Box):
    """A 0-100% scale. on_change runs at most every 50ms while dragging."""

    def __init__(self, title, on_change):
        super().__init__(spacing=12, css_classes=["row"])
        self.on_change = on_change
        self.pending = None
        self.updating = False
        title_label = label(title, "title")
        title_label.set_width_chars(12)
        self.scale = Gtk.Scale.new_with_range(H, 0, 100, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.get_adjustment().set_step_increment(5)
        self.scale.connect("value-changed", self._changed)
        self.value = label("", "dim", xalign=1.0)
        self.value.set_width_chars(5)
        for widget in (title_label, self.scale, self.value):
            self.append(widget)

    def _changed(self, scale):
        value = round(scale.get_value())
        self.value.set_label(f"{value}%")
        if self.updating:
            return
        if self.pending is None:
            GLib.timeout_add(50, self._flush)
        self.pending = value

    def _flush(self):
        value, self.pending = self.pending, None
        self.on_change(value)
        return False

    def set_value(self, value):
        # don't yank the slider out from under a drag
        if self.pending is not None or self.scale.get_state_flags() & Gtk.StateFlags.ACTIVE:
            return
        self.updating = True
        self.scale.set_value(value)
        self.updating = False
        self.value.set_label(f"{round(value)}%")


class ItemList(Gtk.Box):
    """Clickable '* name   detail' lines. Only rebuilt when the items change, and keeps keyboard focus."""

    def __init__(self, on_activate, empty="nothing here"):
        super().__init__(orientation=V)
        self.on_activate = on_activate
        self.empty = empty
        self.items = None
        self.buttons = {}

    def set_items(self, items):
        """items: (key, name, detail, active) tuples."""
        items = list(items)
        if items == self.items:
            return
        focused = next((key for key, b in self.buttons.items() if b.has_focus()), None)
        self.items = items
        self.buttons = {}
        while child := self.get_first_child():
            self.remove(child)
        if not items:
            self.append(label(self.empty, "dim", "row"))
        for key, name, detail, active in items:
            box = Gtk.Box(spacing=12)
            box.append(label(("* " if active else "  ") + name, hexpand=True, ellipsize=True))
            box.append(label(detail, "detail"))
            item = Gtk.Button(child=box, css_classes=["item"])
            item.connect("clicked", lambda _, key=key: self.on_activate(key))
            self.append(item)
            self.buttons[key] = item
        if focused is not None and self.buttons:
            self.buttons.get(focused, next(iter(self.buttons.values()))).grab_focus()


class Page(Gtk.Box):
    name = ""
    interval = 0  # seconds between refresh() calls while the page is visible

    def __init__(self, panel):
        super().__init__(orientation=V, css_classes=["page"])
        self.panel = panel
        self.timer = 0

    def section(self, text, *end):
        box = Gtk.Box(spacing=12, css_classes=["section-row"])
        box.append(label(text + ":", "section", hexpand=True))
        for widget in end:
            box.append(widget)
        self.append(box)

    def add(self, *widgets):
        for widget in widgets:
            self.append(widget)

    def shown(self):
        self.refresh()
        if self.interval:
            self.timer = GLib.timeout_add_seconds(self.interval, lambda: self.refresh() or True)

    def hidden(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def refresh(self):
        pass

    def escape(self, focus):
        """Handle esc inside the page; return True to keep the keyboard here."""
        return False


#############
### PANEL ###
#############


class Panel(Gtk.ApplicationWindow):
    def __init__(self, app, page_classes):
        super().__init__(application=app, title="settings", css_classes=["settings-panel"])
        self.app = app
        self.current = None

        # a transparent overlay over the whole screen, so clicking outside the panel closes it
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "settings-panel")
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self, edge, True)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

        frame = Gtk.Box(orientation=V, css_classes=["frame"], halign=Gtk.Align.CENTER,
                        valign=Gtk.Align.CENTER, width_request=WIDTH, height_request=HEIGHT)
        self.prompt = label("", "prompt")
        frame.append(self.prompt)
        frame.append(Gtk.Box(css_classes=["hsep"]))

        body = Gtk.Box(vexpand=True)
        self.sidebar = Gtk.ListBox(css_classes=["sidebar"], selection_mode=Gtk.SelectionMode.BROWSE)
        self.sidebar.set_size_request(170, -1)
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.pages = []
        for cls in page_classes:
            page = cls(self)
            self.pages.append(page)
            self.sidebar.append(Gtk.ListBoxRow(child=label(page.name)))
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=page)
            self.stack.add_named(scroller, page.name)
        self.sidebar.connect("row-selected", self._row_selected)
        body.append(self.sidebar)
        body.append(Gtk.Box(css_classes=["vsep"]))
        body.append(self.stack)
        frame.append(body)

        frame.append(Gtk.Box(css_classes=["hsep"]))
        frame.append(label("↑↓ category   →/enter open   ←/esc back   esc close", "hints"))
        self.set_child(frame)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("pressed", self._clicked)
        self.add_controller(click)

    def show_page(self, name):
        index = next((i for i, page in enumerate(self.pages) if page.name == name), 0)
        self.select(index)

    def select(self, index):
        row = self.sidebar.get_row_at_index(max(0, min(index, len(self.pages) - 1)))
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
        # pages with nothing to focus (about) keep the keyboard in the sidebar
        if not self.stack.get_visible_child().child_focus(Gtk.DirectionType.TAB_FORWARD):
            self.focus_sidebar()

    def _key_pressed(self, _, keyval, _keycode, state):
        name = Gdk.keyval_name(keyval) or ""
        mods = state & Gtk.accelerator_get_default_mod_mask()
        focus = self.get_focus()
        index = self.sidebar.get_selected_row().get_index()
        # GTK only turns on focus rings for keys it handles itself, and these get caught first
        self.set_focus_visible(True)

        if mods == Gdk.ModifierType.ALT_MASK and name in "123456789" and len(name) == 1:
            self.select(int(name) - 1)
            return True
        if mods:
            return False

        if focus is None or focus.is_ancestor(self.sidebar):
            if name == "Escape":
                self.app.quit()
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
        # sliders would take up/down as volume changes; keep those for moving between rows
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
        grid = focus.get_ancestor(Gtk.FlowBox)
        return grid is not None and focus.get_index() % grid.get_max_children_per_line() != 0

    def _clicked(self, gesture, _n, x, y):
        if self.pick(x, y, Gtk.PickFlags.DEFAULT) in (None, self):
            self.app.quit()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.css = Gtk.CssProvider()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        self.load_css()
        # above ~/.config/gtk-4.0/gtk.css, which is also generated by pywal
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

    def load_css(self):
        self.css.load_from_string(Template(CSS).substitute(load_theme()))

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        page = args[0] if args else None
        if page in ("-h", "--help"):
            command_line.print_literal(__doc__)
        elif self.window is None:
            self.window = Panel(self, PAGES)
            self.window.present()
            self.window.show_page(page)
        elif page and page != self.window.current.name:
            self.window.show_page(page)
        else:
            self.quit()
        return 0


#############
### PAGES ###
#############


SWAY_CONFIG = os.path.expanduser("~/.config/sway/config")
WALLPAPERS = os.path.expanduser("~/wallpapers")
BG_LINE = re.compile(r'^(output \* bg )("[^"]*"|\S+)(.*)$', re.M)
THUMB_W, THUMB_H = 176, 110


class WallpaperPage(Page):
    """Sets the `output * bg` line in the sway config, then regenerates the colors with wal.sh."""
    name = "wallpaper"

    def __init__(self, panel):
        super().__init__(panel)
        self.paths = []
        self.applying = False
        self.current = label("", "dim", ellipsize=True)
        self.section("wallpaper")
        self.add(row("current", self.current))
        self.section("pick one")
        self.grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=4,
                                column_spacing=4, min_children_per_line=3, max_children_per_line=3,
                                activate_on_single_click=True)
        self.grid.connect("child-activated", self.apply)
        self.status = label("", "dim", "row", ellipsize=True)
        self.add(self.grid, self.status)

    def current_path(self):
        match = BG_LINE.search(read(SWAY_CONFIG))
        return os.path.expanduser(match.group(2).strip('"')) if match else None

    def shown(self):
        if not self.paths:
            self.load_thumbnails()
        self.mark_current(self.current_path())

    def mark_current(self, current):
        """Outline the wallpaper in use. Not a selection, since arrow keys move the selection."""
        self.current.set_label(os.path.basename(current) if current else "not set in the sway config")
        for index, path in enumerate(self.paths):
            child = self.grid.get_child_at_index(index)
            (child.add_css_class if path == current else child.remove_css_class)("current")

    def load_thumbnails(self):
        try:
            names = sorted(os.listdir(WALLPAPERS))
        except OSError:
            names = []
        self.paths = [os.path.join(WALLPAPERS, n) for n in names if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        pictures = []
        for path in self.paths:
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
            picture.set_size_request(THUMB_W, THUMB_H)
            picture.set_tooltip_text(os.path.basename(path))
            self.grid.append(picture)
            pictures.append(picture)
        if not self.paths:
            self.status.set_label(f"no images in {WALLPAPERS}")

        def load():
            scale = 2  # sharp on the scaled laptop panel
            for path, picture in zip(self.paths, pictures):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, THUMB_W * 2 * scale, THUMB_H * 2 * scale, True)
                except GLib.Error:
                    continue
                GLib.idle_add(lambda picture=picture, pixbuf=pixbuf: picture.set_paintable(texture(pixbuf)) and False)

        in_background(load)

    def apply(self, _grid, child):
        path = self.paths[child.get_index()]
        if self.applying or path == self.current_path():
            return
        home = os.path.expanduser("~")
        short = "~" + path[len(home):] if path.startswith(home + "/") else path
        if " " in short:
            short = f'"{short}"'
        try:
            with open(SWAY_CONFIG) as f:
                config = f.read()
            config, found = BG_LINE.subn(lambda m: m.group(1) + short + m.group(3), config, count=1)
            if not found:
                self.status.set_label("no `output * bg` line in the sway config")
                return
            with open(SWAY_CONFIG, "w") as f:
                f.write(config)
        except OSError as e:
            self.status.set_label(f"couldn't update the sway config: {e.strerror.lower()}")
            return

        self.applying = True
        self.mark_current(path)
        self.status.set_label("generating colors...")
        in_background(lambda: run_ok(os.path.expanduser("~/.local/bin/wal.sh"), path, timeout=300), self._applied)

    def _applied(self, result):
        ok, output = result
        self.applying = False
        self.status.set_label("done" if ok else f"wal.sh failed: {output.lower()}")
        self.panel.app.load_css()  # pick up the new colors


def texture(pixbuf):
    fmt = Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pixbuf.get_width(), pixbuf.get_height(), fmt,
                                 pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())


class NotificationsPage(Page):
    name = "notifications"
    interval = 3

    def __init__(self, panel):
        super().__init__(panel)
        self.dnd = Toggle(lambda on: run("swaync-client", "-dn" if on else "-df"))
        self.count = label("", "dim")
        self.section("notifications")
        self.add(
            row("do not disturb", self.dnd, sub=label("no popups, they still land in the center", "dim")),
            row("waiting", button("clear all", self.clear), sub=self.count),
            row("notification center", button("open", self.open_center)),
        )

    def refresh(self):
        self.dnd.set_active(run("swaync-client", "-D", timeout=3).strip() == "true")
        count = run("swaync-client", "-c", timeout=3).strip()
        self.count.set_label(f"{count or 0} notification{'' if count == '1' else 's'}")

    def clear(self):
        run("swaync-client", "-C")
        self.refresh()

    def open_center(self):
        self.panel.app.quit()
        spawn("swaync-client", "-op")


class AboutPage(Page):
    name = "about"

    def __init__(self, panel):
        super().__init__(panel)
        os_release = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read("/etc/os-release"), re.M))
        self.section("this computer")
        self.add(
            row("model", label(read("/proc/device-tree/model").rstrip("\0"), "dim")),
            row("os", label(os_release.get("PRETTY_NAME", "linux").lower(), "dim")),
            row("kernel", label(os.uname().release, "dim")),
            row("hostname", label(os.uname().nodename, "dim")),
            row("cpu", label(f"{os.cpu_count()} cores", "dim")),
        )
        self.memory = label("", "dim")
        self.disk = label("", "dim")
        self.uptime = label("", "dim")
        self.section("usage")
        self.add(row("memory", self.memory), row("disk", self.disk), row("uptime", self.uptime))

    def refresh(self):
        meminfo = dict(re.findall(r"^(\w+):\s+(\d+)", read("/proc/meminfo"), re.M))
        total, available = int(meminfo.get("MemTotal", 0)), int(meminfo.get("MemAvailable", 0))
        self.memory.set_label(f"{(total - available) / 2**20:.1f} / {total / 2**20:.1f} gb used")
        disk = os.statvfs("/")
        size, free = disk.f_blocks * disk.f_frsize, disk.f_bavail * disk.f_frsize
        self.disk.set_label(f"{(size - free) / 2**30:.0f} / {size / 2**30:.0f} gb used")
        minutes = int(float(read("/proc/uptime", "0").split()[0])) // 60
        self.uptime.set_label(f"{minutes // 1440}d {minutes // 60 % 24}h {minutes % 60}m")


def nmcli_fields(line):
    """Split a line of `nmcli -t` output on its unescaped colons."""
    return [field.replace("\\:", ":").replace("\\\\", "\\") for field in re.split(r"(?<!\\):", line)]


class WifiPage(Page):
    name = "wi-fi"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        self.active_ssid = None
        self.saved = set()
        self.security = {}
        self.pending_ssid = None
        self.busy = False

        self.toggle = Toggle(self.set_radio)
        self.connection = label("", "dim", ellipsize=True)
        self.disconnect = button("disconnect", self.disconnect_current)
        self.add(row("wi-fi", self.toggle), row("network", self.disconnect, sub=self.connection))

        self.section("networks", button("scan", lambda: self.refresh(rescan=True)))
        self.networks = ItemList(self.pick, empty="no networks found")
        self.password_label = label("", "title", ellipsize=True)
        self.password = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True, placeholder_text="password")
        self.password.connect("activate", lambda _: self.connect_to(self.pending_ssid, self.password.get_text()))
        self.password_row = Gtk.Box(spacing=12, css_classes=["row"], visible=False)
        self.password_row.append(self.password_label)
        self.password_row.append(self.password)
        self.status = label("", "dim", "row", ellipsize=True)
        self.add(self.networks, self.password_row, self.status)

    def refresh(self, rescan=False):
        if self.busy:
            return
        self.busy = True
        if rescan:
            self.status.set_label("scanning...")

        def work():
            radio = run("nmcli", "radio", "wifi").strip() == "enabled"
            networks = run("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                           "--rescan", "yes" if rescan else "no", timeout=30)
            saved = [nmcli_fields(line) for line in run("nmcli", "-t", "-f", "NAME,TYPE", "con", "show").splitlines()]
            return radio, networks.splitlines(), {f[0] for f in saved if f[-1] == "802-11-wireless"}

        in_background(work, self._update)

    def _update(self, result):
        radio, lines, self.saved = result
        self.busy = False
        networks = {}  # ssid: [in use, signal, security]
        for line in lines:
            in_use, ssid, signal, security = (nmcli_fields(line) + ["", "", "0", ""])[:4]
            if not ssid:
                continue
            old = networks.get(ssid, [False, 0, security])
            networks[ssid] = [old[0] or in_use == "*", max(old[1], int(signal or 0)), security]
        self.security = {ssid: n[2] for ssid, n in networks.items()}
        self.active_ssid = next((ssid for ssid, n in networks.items() if n[0]), None)

        self.toggle.set_active(radio)
        if not radio:
            self.connection.set_label("wi-fi is off")
        else:
            self.connection.set_label(f"connected to {self.active_ssid}" if self.active_ssid else "not connected")
        self.disconnect.set_visible(self.active_ssid is not None)
        self.networks.empty = "no networks found" if radio else "wi-fi is off"
        ordered = sorted(networks.items(), key=lambda kv: (not kv[1][0], -kv[1][1]))[:20] if radio else []
        self.networks.set_items(
            (ssid, ssid, f"{(security or 'open').lower()}  {signal:>3}%", in_use)
            for ssid, (in_use, signal, security) in ordered)
        if self.status.get_label() == "scanning...":
            self.status.set_label("")

    def set_radio(self, on):
        self.busy = True
        in_background(lambda: run("nmcli", "radio", "wifi", "on" if on else "off"),
                      lambda _: GLib.timeout_add(1000, self._after_action))

    def _after_action(self):
        self.busy = False
        self.refresh()
        return False

    def disconnect_current(self):
        devices = [nmcli_fields(line) for line in run("nmcli", "-t", "-f", "DEVICE,TYPE", "dev").splitlines()]
        for device, kind in (d for d in devices if len(d) == 2):
            if kind == "wifi":
                run("nmcli", "dev", "disconnect", device)
        self.refresh()

    def pick(self, ssid):
        if ssid == self.active_ssid:
            return
        if ssid in self.saved or not self.security.get(ssid):
            self.connect_to(ssid)
            return
        self.pending_ssid = ssid
        self.password_label.set_label(ssid)
        self.password.set_text("")
        self.password_row.set_visible(True)
        self.password.grab_focus()

    def connect_to(self, ssid, password=None):
        self.hide_password()
        self.status.set_label(f"connecting to {ssid}...")
        self.busy = True
        was_saved = ssid in self.saved

        def work():
            if password is None and was_saved:
                return run_ok("nmcli", "con", "up", "id", ssid, timeout=60)
            cmd = ["nmcli", "dev", "wifi", "connect", ssid]
            ok, message = run_ok(*cmd, *(["password", password] if password else []), timeout=60)
            if not ok and not was_saved:
                # don't leave a profile with a wrong password behind
                run("nmcli", "con", "delete", "id", ssid)
            return ok, message

        def done(result):
            ok, message = result
            self.status.set_label(f"connected to {ssid}" if ok else f"failed: {message.lower()}")
            self._after_action()

        in_background(work, done)

    def hide_password(self):
        if self.password_row.get_visible():
            self.password_row.set_visible(False)
            if item := self.networks.buttons.get(self.pending_ssid):
                item.grab_focus()

    def escape(self, focus):
        if self.password_row.get_visible() and focus.is_ancestor(self.password_row):
            self.hide_password()
            return True
        return False


class BluetoothPage(Page):
    name = "bluetooth"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        self.busy = False
        self.powered = None
        self.known = {}  # mac: (connected, paired)

        self.toggle = Toggle(self.set_power)
        self.add(row("bluetooth", self.toggle))
        self.scan_button = button("scan", self.scan)
        self.section("devices", self.scan_button)
        self.devices = ItemList(self.pick)
        self.status = label("", "dim", "row", ellipsize=True)
        self.add(self.devices, self.status)

    def refresh(self):
        if self.busy:
            return
        in_background(self._read, self._update)

    @staticmethod
    def _read():
        powered = "Powered: yes" in run("bluetoothctl", "show", timeout=5)
        devices = []
        for line in run("bluetoothctl", "devices", timeout=5).splitlines() if powered else []:
            parts = line.split(" ", 2)
            if len(parts) < 3 or parts[0] != "Device":
                continue
            info = run("bluetoothctl", "info", parts[1], timeout=5)
            connected, paired = "Connected: yes" in info, "Paired: yes" in info
            # scans turn up lots of nameless devices, only show those if they're paired
            if paired or parts[2].replace("-", ":") != parts[1]:
                devices.append((parts[1], parts[2], connected, paired))
        return powered, devices

    def _update(self, result):
        powered, devices = result
        if powered != self.powered:
            self.powered = powered
            self.devices.items = None  # force a rebuild for the new empty text
            self.devices.empty = "no devices yet, try scanning" if powered else "bluetooth is off"
        self.toggle.set_active(powered)
        self.scan_button.set_sensitive(powered)
        self.known = {mac: (connected, paired) for mac, _, connected, paired in devices}
        devices.sort(key=lambda d: (not d[2], not d[3], d[1].lower()))
        self.devices.set_items((mac, name, "connected" if connected else "paired" if paired else "", connected)
                               for mac, name, connected, paired in devices)

    def run_steps(self, message, steps):
        """Run bluetoothctl commands in order on a thread, stopping at the first failure."""
        self.busy = True
        self.status.set_label(message)

        def work():
            for step in steps:
                ok, output = step() if callable(step) else run_ok("bluetoothctl", *step, timeout=30)
                if not ok:
                    return False, output
            return True, ""

        def done(result):
            ok, output = result
            self.busy = False
            self.status.set_label("" if ok else f"failed: {output.lower()}")
            self.refresh()

        in_background(work, done)

    def set_power(self, on):
        def power_on():
            # bluez can take a moment to notice the adapter after the rfkill unblock
            run("rfkill", "unblock", "bluetooth")
            for _ in range(10):
                ok, output = run_ok("bluetoothctl", "power", "on", timeout=5)
                if ok:
                    break
                time.sleep(0.5)
            return ok, output

        if on:
            self.run_steps("turning on...", [power_on])
        else:
            self.run_steps("turning off...", [("power", "off")])

    def scan(self):
        self.run_steps("scanning for 10 seconds...",
                       [lambda: run_ok("bluetoothctl", "--timeout", "10", "scan", "on", timeout=20) and (True, "")])

    def pick(self, mac):
        connected, paired = self.known.get(mac, (False, False))
        if connected:
            self.run_steps("disconnecting...", [("disconnect", mac)])
        elif paired:
            self.run_steps("connecting...", [("connect", mac)])
        else:
            self.run_steps("pairing...", [("pair", mac), ("trust", mac), ("connect", mac)])


def wpctl_volume(node):
    """(percent, muted) for a wpctl node such as @DEFAULT_AUDIO_SINK@."""
    output = run("wpctl", "get-volume", node, timeout=3)
    match = re.search(r"Volume: ([\d.]+)", output)
    return (round(float(match.group(1)) * 100) if match else 0), "MUTED" in output


class SoundPage(Page):
    name = "sound"
    interval = 2

    def __init__(self, panel):
        super().__init__(panel)
        self.controls = {}
        for kind, node in (("sink", "@DEFAULT_AUDIO_SINK@"), ("source", "@DEFAULT_AUDIO_SOURCE@")):
            title = "output" if kind == "sink" else "input"
            end = [button("mixer", self.open_mixer)] if kind == "sink" else []
            self.section(title, *end)
            volume = Slider("volume", lambda v, node=node: run("wpctl", "set-volume", "-l", "1.0", node, f"{v / 100:.2f}"))
            mute = Toggle(lambda on, node=node: run("wpctl", "set-mute", node, "1" if on else "0"))
            devices = ItemList(lambda name, kind=kind: self.set_default(kind, name), empty=f"no {title} devices")
            self.add(volume, row("mute", mute), devices)
            self.controls[kind] = (node, volume, mute, devices)

    def refresh(self):
        for kind, (node, volume, mute, devices) in self.controls.items():
            percent, muted = wpctl_volume(node)
            volume.set_value(percent)
            mute.set_active(muted)
            default = run("pactl", f"get-default-{kind}", timeout=3).strip()
            try:
                nodes = json.loads(run("pactl", "-f", "json", "list", f"{kind}s", timeout=3) or "[]")
            except ValueError:
                nodes = []
            devices.set_items((n["name"], n.get("description") or n["name"], "", n["name"] == default)
                              for n in nodes if not n["name"].endswith(".monitor"))

    def set_default(self, kind, name):
        run("pactl", f"set-default-{kind}", name)
        self.refresh()

    def open_mixer(self):
        spawn("pavucontrol")
        self.panel.app.quit()


def brightness(*device):
    """Percent brightness of a brightnessctl device, or None if there isn't one."""
    fields = run("brightnessctl", "-m", *device, timeout=3).partition("\n")[0].split(",")
    try:
        return round(int(fields[2]) * 100 / int(fields[4]))
    except (IndexError, ValueError, ZeroDivisionError):
        return None


class DisplayPage(Page):
    name = "displays"
    interval = 2

    def __init__(self, panel):
        super().__init__(panel)
        self.section("brightness")
        # never all the way to 0%, that turns the panel off
        self.screen = Slider("display", lambda v: run("brightnessctl", "-q", "-c", "backlight", "set", f"{max(v, 1)}%"))
        self.keyboard = Slider("keyboard", lambda v: run("brightnessctl", "-q", "-d", "kbd_backlight", "set", f"{v}%"))
        self.keyboard.set_visible(brightness("-d", "kbd_backlight") is not None)
        self.add(self.screen, self.keyboard)
        self.section("outputs")
        self.outputs = Gtk.Box(orientation=V)
        self.add(self.outputs)

    def shown(self):
        while child := self.outputs.get_first_child():
            self.outputs.remove(child)
        try:
            outputs = json.loads(run("swaymsg", "-r", "-t", "get_outputs", timeout=3) or "[]")
        except ValueError:
            outputs = []
        for output in outputs:
            mode = output.get("current_mode") or {}
            size = f"{mode.get('width', '?')}x{mode.get('height', '?')} @ {mode.get('refresh', 0) / 1000:.0f}hz"
            model = f"{output.get('make', '')} {output.get('model', '')}".strip()
            self.outputs.append(row(output["name"], label(f"{size}, scale {output.get('scale', 1):g}", "dim"),
                                    sub=label(model.lower(), "dim")))
        super().shown()

    def refresh(self):
        if (value := brightness("-c", "backlight")) is not None:
            self.screen.set_value(value)
        if self.keyboard.get_visible() and (value := brightness("-d", "kbd_backlight")) is not None:
            self.keyboard.set_value(value)


def duration(seconds):
    return f"{seconds // 3600}h {seconds // 60 % 60:02d}m"


class BatteryPage(Page):
    name = "battery"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        supplies = "/sys/class/power_supply"
        names = sorted(os.listdir(supplies)) if os.path.isdir(supplies) else []
        self.path = next((f"{supplies}/{n}" for n in names if read(f"{supplies}/{n}/type") == "Battery"), None)
        self.section("battery")
        if not self.path:
            self.add(label("no battery", "dim", "row"))
            return

        self.level = Gtk.LevelBar(hexpand=True, valign=Gtk.Align.CENTER, min_value=0, max_value=100)
        for offset in (Gtk.LEVEL_BAR_OFFSET_LOW, Gtk.LEVEL_BAR_OFFSET_HIGH, Gtk.LEVEL_BAR_OFFSET_FULL):
            self.level.remove_offset_value(offset)
        self.percent = label("", "dim", xalign=1.0)
        self.percent.set_width_chars(5)
        charge_title = label("charge", "title")
        charge_title.set_width_chars(12)
        charge = Gtk.Box(spacing=12, css_classes=["row"])
        for widget in (charge_title, self.level, self.percent):
            charge.append(widget)
        self.add(charge)

        self.values = {}
        for key in ("status", "time", "power draw"):
            self.values[key] = label("", "dim")
            self.add(row(key, self.values[key]))
        self.section("health")
        for key in ("capacity", "cycles", "charge limit"):
            self.values[key] = label("", "dim")
            self.add(row(key, self.values[key]))

    def refresh(self):
        if not self.path:
            return
        value = lambda name: read(f"{self.path}/{name}")
        number = lambda name: int(value(name) or 0)
        capacity, status = number("capacity"), value("status").lower()
        self.level.set_value(capacity)
        self.percent.set_label(f"{capacity}%")
        if status == "discharging" and number("time_to_empty_now"):
            time_text = f"{duration(number('time_to_empty_now'))} left"
        elif status == "charging" and number("time_to_full_now"):
            time_text = f"{duration(number('time_to_full_now'))} until full"
        else:
            time_text = "-"
        full, design = number("energy_full") or number("charge_full"), number("energy_full_design") or number("charge_full_design")
        self.values["status"].set_label(status)
        self.values["time"].set_label(time_text)
        self.values["power draw"].set_label(f"{abs(number('power_now')) / 1e6:.1f} w" if value("power_now") else "-")
        self.values["capacity"].set_label(f"{full * 100 // design}% of design" if design else "-")
        self.values["cycles"].set_label(value("cycle_count") or "-")
        limit = value("charge_control_end_threshold")
        self.values["charge limit"].set_label(f"{limit}%" if limit else "-")


PAGES = [WifiPage, BluetoothPage, SoundPage, DisplayPage, BatteryPage, WallpaperPage, NotificationsPage, AboutPage]

if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
