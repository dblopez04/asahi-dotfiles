#!/usr/bin/env python3
"""Keyboard shortcut cheat sheet, grouped by what the shortcuts do (Super+/).

Reads the sway config (with unsaved Settings changes), so it always matches your real bindings,
gestures included. Any key or a click closes it.
"""
import os
import re
import sys
from string import Template

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPTS)
import dotconfig  # noqa: E402
from settings_pages.common import load_theme  # noqa: E402
from settings_pages.keyboard import bindings  # noqa: E402

APP_ID = "dev.dotfiles.Cheatsheet"
SECTIONS = ["apps & tools", "windows", "workspaces", "screenshots", "clipboard", "gestures", "media & hardware",
            "session"]

# (pattern on the command, section, description); the first match wins
RULES = [
    (r"spotlight\.py", "apps & tools", "spotlight"),
    (r"settings-panel\.py", "apps & tools", "settings"),
    (r"wallpaper-picker\.py", "apps & tools", "wallpaper picker"),
    (r"clipboard-history\.py", "clipboard", "clipboard history"),
    (r"emoji-picker\.py", "apps & tools", "emoji picker"),
    (r"color-picker\.sh", "apps & tools", "pick a color on screen"),
    (r"cheatsheet\.py", "apps & tools", "this cheat sheet"),
    (r"walwrite", "apps & tools", "walwrite"),
    (r"walcalc", "apps & tools", "calculator"),
    (r"\$menu|fuzzel", "apps & tools", "app launcher"),
    (r"\$terminal|kitty", "apps & tools", "terminal"),
    (r"\$fileManager|nautilus", "apps & tools", "file manager"),
    (r"firefox", "apps & tools", "firefox"),
    (r"swaync-client -t", "apps & tools", "notification center"),
    (r"mac-clipboard\.sh c", "clipboard", "copy"),
    (r"mac-clipboard\.sh x", "clipboard", "cut"),
    (r"mac-clipboard\.sh v", "clipboard", "paste"),
    (r"mac-clipboard\.sh a", "clipboard", "select all"),
    (r"screenshot.* area", "screenshots", "screenshot an area"),
    (r"screenshot.* (active|window)", "screenshots", "screenshot the window"),
    (r"screenshot.* output", "screenshots", "screenshot the screen"),
    (r"close-window|^kill", "windows", "close the window"),
    (r"^fullscreen", "windows", "fullscreen"),
    (r"^floating toggle", "windows", "float / tile"),
    (r"^layout toggle split", "windows", "change split direction"),
    (r'^mode "resize"', "windows", "resize mode (arrows, then esc)"),
    (r"^focus (left|right|up|down)", "windows", "focus a window"),
    (r"^move (left|right|up|down)", "windows", "move a window"),
    (r"^move scratchpad", "workspaces", "send to the scratchpad"),
    (r"^scratchpad show", "workspaces", "show the scratchpad"),
    (r"^move container to workspace", "workspaces", "move window to workspace"),
    (r"^workspace (next|prev)", "workspaces", "next / previous workspace"),
    (r"^workspace", "workspaces", "switch to workspace"),
    (r"^reload", "session", "reload sway"),
    (r"^exit", "session", "log out"),
    (r"swaylock", "session", "lock"),
    (r"Audio(Raise|Lower)Volume|output-volume (raise|lower)", "media & hardware", "volume"),
    (r"mute-toggle", "media & hardware", "mute"),
    (r"playerctl", "media & hardware", "play / skip"),
    (r"kbd_backlight", "media & hardware", "keyboard backlight"),
    (r"brightness", "media & hardware", "brightness"),
]
KEY_NAMES = {"$mod": "super", "mod4": "super", "mod1": "alt", "ctrl": "ctrl", "control": "ctrl", "shift": "shift",
             "comma": ",", "period": ".", "slash": "/", "space": "space", "return": "enter", "escape": "esc",
             "left": "←", "right": "→", "up": "↑", "down": "↓", "button4": "scroll ↑", "button5": "scroll ↓",
             "xf86audioraisevolume": "vol+", "xf86audiolowervolume": "vol−", "xf86audiomute": "mute key",
             "xf86audiomicmute": "mic mute key", "xf86monbrightnessup": "bright+", "xf86monbrightnessdown": "bright−",
             "xf86audioplay": "play key", "xf86audionext": "next key", "xf86audioprev": "prev key",
             "xf86launcha": "f3", "xf86search": "f4", "xf86calculator": "calculator key"}

CSS = """
window.cheatsheet { background: $bg; }
window.cheatsheet > .frame { background: $bg; color: $fg; border: 1px solid $border; padding: 18px 24px; }
.frame, .frame * { font-family: "BlexMono Nerd Font", monospace; border-radius: 0; box-shadow: none; }
.heading { color: $fg; font-size: 13pt; font-weight: bold; }
.subtitle { color: $dim; font-size: 9pt; }
.section { color: $accent; font-weight: bold; font-size: 10.5pt; margin-bottom: 4px; }
.keys { color: $fg; background: $hover; border: 1px solid $faint; padding: 0 6px; font-size: 9.5pt; }
.what { color: $dim; font-size: 9.5pt; }
flowboxchild { padding: 6px 14px 10px 0; outline: none; background: none; }
"""


def pretty(combo):
    parts = [KEY_NAMES.get(part.lower(), part.lower()) for part in combo.split("+")]
    return " ".join(parts)


def describe(command, comment):
    for pattern, section, text in RULES:
        if re.search(pattern, command, re.I):
            return section, text
    text = comment or command
    return "apps & tools" if command.startswith("exec") else "windows", text[:40]


def gather():
    sections = {name: [] for name in SECTIONS}
    seen = {}
    for combo, command, comment, _flags in bindings():
        if command.startswith("exec") and combo.lower().startswith("xf86"):
            command = combo + " " + command  # media keys are recognised by their key name
        section, text = describe(command, comment)
        keys = pretty(combo)
        # collapse repeats: workspace 1-10, arrow directions, volume up/down...
        group_key = (section, text)
        if group_key in seen:
            entry = seen[group_key]
            entry["keys"].append(keys)
            continue
        entry = {"keys": [keys], "text": text}
        seen[group_key] = entry
        sections[section].append(entry)

    config = dotconfig.read(dotconfig.SWAY_CONFIG) + "\n" + dotconfig.read(dotconfig.SWAY_PENDING)
    for fingers, direction, command in re.findall(r"^\s*bindgesture\s+(?:--\S+\s+)*swipe:(\d):(\w+)\s+(.+)$", config, re.M):
        _section, text = describe(command, "")
        arrow = {"left": "←", "right": "→", "up": "↑", "down": "↓"}.get(direction, direction)
        entry = next((e for e in sections["gestures"] if e["text"] == text), None)
        label = f"{fingers} fingers {arrow}"
        if entry:
            if label not in entry["keys"]:
                entry["keys"].append(label)
        else:
            sections["gestures"].append({"keys": [label], "text": text})
    return sections


def compact(keys):
    """'super 1', 'super 2', ... -> 'super 1…0'; arrows -> 'super ←→↑↓'."""
    if len(keys) <= 1:
        return keys[0] if keys else ""
    prefixes = {k.rsplit(" ", 1)[0] if " " in k else "" for k in keys}
    lasts = [k.rsplit(" ", 1)[-1] for k in keys]
    if len(prefixes) == 1:
        prefix = prefixes.pop()
        if all(l.isdigit() for l in lasts):
            return f"{prefix} {lasts[0]}…{lasts[-1]}".strip()
        if all(len(l) == 1 for l in lasts):
            return f"{prefix} {''.join(lasts)}".strip()
    return " / ".join(keys)


class Cheatsheet(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Keyboard shortcuts", css_classes=["cheatsheet"], decorated=False,
                         default_width=1180)
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["frame"])
        header = Gtk.Box(spacing=12)
        header.append(Gtk.Label(label="keyboard shortcuts", xalign=0, css_classes=["heading"]))
        header.append(Gtk.Label(label="from your sway config · change them in settings > keyboard · any key closes",
                                xalign=0, hexpand=True, css_classes=["subtitle"]))
        frame.append(header)
        # nothing in the sheet takes focus, so arrow keys don't move a focus box around it
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=3, max_children_per_line=4,
                           homogeneous=False, valign=Gtk.Align.START, focusable=False, can_focus=False)
        for name, entries in gather().items():
            if not entries:
                continue
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.append(Gtk.Label(label=name, xalign=0, css_classes=["section"]))
            for entry in entries:
                line = Gtk.Box(spacing=8)
                keys = Gtk.Label(label=compact(entry["keys"]), css_classes=["keys"], ellipsize=Pango.EllipsizeMode.END,
                                 max_width_chars=26)
                line.append(keys)
                line.append(Gtk.Label(label=entry["text"], xalign=0, css_classes=["what"], hexpand=True))
                box.append(line)
            grid.append(box)
            child = grid.get_last_child()
            child.set_focusable(False)
            child.set_can_focus(False)
        frame.append(grid)
        self.set_child(frame)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: self.close())
        self.add_controller(click)
        self.connect("notify::is-active", lambda *_: (not self.is_active() and getattr(self, "shown", False)
                                                        and self.close()) or setattr(self, "shown", True))

    def key_pressed(self, _controller, keyval, _keycode, _state):
        name = Gdk.keyval_name(keyval) or ""
        if name.startswith(("Super", "Shift", "Control", "Alt", "Meta")):
            return True  # holding modifiers doesn't close it
        if name in ("Up", "Down", "Left", "Right", "Tab", "ISO_Left_Tab", "Page_Up", "Page_Down", "Home", "End"):
            return True  # the sheet is static: navigation keys do nothing
        self.close()
        return True


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(Template(CSS).substitute(load_theme()))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

    def do_command_line(self, command_line):
        if self.window is None:
            self.window = Cheatsheet(self)
            self.window.present()
        else:
            self.quit()
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
