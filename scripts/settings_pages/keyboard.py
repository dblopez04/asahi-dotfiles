import re

from gi.repository import Gdk, Gtk

import dotconfig

from .common import V, ItemList, Page, Slider, button, label, row

MODIFIERS = [(Gdk.ModifierType.SUPER_MASK, "$mod"), (Gdk.ModifierType.CONTROL_MASK, "Ctrl"),
             (Gdk.ModifierType.ALT_MASK, "Mod1"), (Gdk.ModifierType.SHIFT_MASK, "Shift")]
PRETTY = {"$mod": "Super", "mod4": "Super", "mod1": "Alt", "ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift"}


def pretty_combo(combo):
    parts = []
    for part in combo.split("+"):
        name = PRETTY.get(part.lower(), part)
        parts.append(name.upper() if len(name) == 1 else name.replace("XF86", "").replace("button", "scroll "))
    return "+".join(parts)


def bindings():
    """[(combo, command, description, flags)] from the saved config with staged changes on top."""
    config = dotconfig.read(dotconfig.SWAY_CONFIG).splitlines()
    found, comment, depth = {}, "", 0
    for line in config:
        stripped = line.strip()
        if stripped.endswith("{"):
            depth += 1
        elif stripped == "}":
            depth = max(0, depth - 1)
        if stripped.startswith("#"):
            comment = stripped.lstrip("# ").strip()
            continue
        if not stripped:
            comment = ""
            continue
        match = re.match(r"^bindsym\s+((?:--\S+\s+)*)(\S+)\s+(.*)$", stripped)
        if match and depth == 0:
            found[match.group(2).lower()] = (match.group(2), match.group(3), comment, match.group(1).strip())
    for key, line in dotconfig.sway_pending().items():
        if not key.startswith("bindsym "):
            continue
        match = re.match(r"^(un)?bindsym\s+((?:--\S+\s+)*)(\S+)\s*(.*)$", line)
        if not match:
            continue
        combo = match.group(3)
        if match.group(1):
            found.pop(combo.lower(), None)
        else:
            old = found.get(combo.lower())
            found[combo.lower()] = (combo, match.group(4), old[2] if old else "", match.group(2).strip())
    return list(found.values())


class KeyboardPage(Page):
    name = "keyboard"

    def __init__(self, panel):
        super().__init__(panel)
        self.recording = False
        self.editing = None  # the combo being edited, or "" for a new one

        self.section("typing")
        self.delay = Slider("repeat delay", lambda v: self.stage(f"input type:keyboard repeat_delay {v:.0f}"),
                            lower=150, upper=1000, step=25, fmt="{:.0f} ms", throttle=None)
        self.rate = Slider("repeat rate", lambda v: self.stage(f"input type:keyboard repeat_rate {v:.0f}"),
                           lower=10, upper=80, step=1, fmt="{:.0f}/s", throttle=None)
        test = Gtk.Entry(placeholder_text="try it here", hexpand=True)
        self.add(self.delay, self.rate, row("test", test))

        self.search = Gtk.SearchEntry(placeholder_text="search shortcuts", hexpand=True)
        self.search.connect("search-changed", lambda _: self.fill())
        self.section("shortcuts", button("add", lambda: self.edit("")))

        self.editor = Gtk.Box(orientation=V, css_classes=["row"], visible=False)
        keys_row = Gtk.Box(spacing=8)
        self.keys = label("", "accent", hexpand=True)
        self.record_button = button("record keys", self.start_recording)
        keys_row.append(label("keys", "title"))
        keys_row.append(self.keys)
        keys_row.append(self.record_button)
        command_row = Gtk.Box(spacing=8)
        self.command = Gtk.Entry(hexpand=True, placeholder_text="sway command, e.g. exec firefox")
        self.command.connect("activate", lambda _: self.save_binding())
        command_row.append(label("does", "title"))
        command_row.append(self.command)
        actions = Gtk.Box(spacing=4, halign=Gtk.Align.END)
        self.remove_button = button("remove", self.remove_binding, "danger")
        for widget in (self.remove_button, button("cancel", self.close_editor), button("apply", self.save_binding)):
            actions.append(widget)
        self.editor_status = label("", "dim", ellipsize=True)
        for widget in (keys_row, command_row, self.editor_status, actions):
            self.editor.append(widget)
        self.add(row("", self.search), self.editor)

        self.list = ItemList(self.edit, empty="no shortcuts match")
        self.add(self.list)

    def refresh(self):
        state = {k: self.sway(f"input type:keyboard {k}") for k in ("repeat_delay", "repeat_rate")}
        self.delay.set_value(float(state["repeat_delay"] or 600))
        self.rate.set_value(float(state["repeat_rate"] or 25))
        self.fill()

    def fill(self):
        query = self.search.get_text().lower()
        self.bindings = {combo.lower(): (combo, command, desc, flags) for combo, command, desc, flags in bindings()}
        items = []
        for key, (combo, command, desc, _flags) in self.bindings.items():
            text = f"{pretty_combo(combo)} {command} {desc}".lower()
            if query and query not in text:
                continue
            items.append((key, pretty_combo(combo), command if len(command) < 48 else command[:46] + "…", False))
        self.list.set_items(sorted(items, key=lambda i: i[1].lower()))

    # ----- editing -----

    def edit(self, key):
        self.editing = key
        combo, command, desc, _flags = self.bindings.get(key, ("", "", "", ""))
        self.new_combo = combo
        self.keys.set_label(pretty_combo(combo) if combo else "press record, then the keys")
        self.command.set_text(command)
        self.editor_status.set_label(desc)
        self.remove_button.set_visible(bool(key))
        self.editor.set_visible(True)
        if key:
            self.command.grab_focus()
        else:
            self.start_recording()

    def start_recording(self):
        self.recording = True
        self.keys.set_label("press the new shortcut…")
        self.record_button.grab_focus()

    def handle_key(self, keyval, state):
        if not self.recording:
            return False
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Meta_L"):
            return True  # wait for the real key
        if name == "Escape" and not state & Gtk.accelerator_get_default_mod_mask():
            self.recording = False
            self.keys.set_label(pretty_combo(self.new_combo) if self.new_combo else "")
            return True
        mods = [text for mask, text in MODIFIERS if state & mask]
        key = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or name
        self.new_combo = "+".join(mods + [key])
        self.recording = False
        self.keys.set_label(pretty_combo(self.new_combo))
        existing = self.bindings.get(self.new_combo.lower())
        if existing and self.new_combo.lower() != (self.editing or ""):
            self.editor_status.set_label(f"already used for: {existing[1]} (applying replaces it)")
        self.command.grab_focus()
        return True

    def save_binding(self):
        command = self.command.get_text().strip()
        if not self.new_combo or not command:
            self.editor_status.set_label("needs keys and a command")
            return
        flags = self.bindings.get(self.editing or "", ("", "", "", ""))[3]
        lines = []
        if self.editing and self.editing != self.new_combo.lower():
            lines.append(f"unbindsym {self.bindings[self.editing][0]}")
        lines.append(" ".join(part for part in ("bindsym", flags, self.new_combo, command) if part))
        self.stage(*lines)
        self.close_editor()
        self.fill()

    def remove_binding(self):
        if self.editing:
            self.stage(f"unbindsym {self.bindings[self.editing][0]}")
        self.close_editor()
        self.fill()

    def close_editor(self):
        self.recording = False
        self.editing = None
        self.editor.set_visible(False)

    def escape(self, focus):
        if self.editor.get_visible():
            self.close_editor()
            return True
        return False
