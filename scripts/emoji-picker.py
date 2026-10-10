#!/usr/bin/env python3
"""Emoji picker: a grid of emoji by category with a search bar, like macOS (Super+Ctrl+Space).

Keys: type to search by name or keyword ("thumbs", "lol", "party"), arrows move, enter picks,
      tab/shift+tab jump between categories, shift+enter (or right-click) picks a skin tone,
      esc closes. Drag it by any empty spot; it stays open until you pick or press esc (running it
      again brings it back to the front, or closes it if it's already there).

The pick is typed into the window you were in and also left on the clipboard. The ones you use most
show first, and emoji with skin tones show the tone you used last. Needs unicode-emoji (the emoji
and their categories) and cldr-emoji-annotation (search keywords).
"""
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from string import Template

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPTS)
from settings_pages.common import load_theme  # noqa: E402

APP_ID = "dev.dotfiles.EmojiPicker"
STATE = os.path.join(GLib.get_user_state_dir(), "emoji-picker")
RECENT = os.path.join(STATE, "recent.json")
CACHE = os.path.join(GLib.get_user_cache_dir(), "emoji-picker.json")
HIDDEN = os.path.join(GLib.get_user_cache_dir(), "emoji-picker-hidden.json")  # what the emoji font can't draw
EMOJI_TEST = "/usr/share/unicode/emoji/emoji-test.txt"
ANNOTATIONS = ["/usr/share/unicode/cldr/common/annotations/en.xml",
               "/usr/share/unicode/cldr/common/annotationsDerived/en.xml"]
COLUMNS = 9
FREQUENT = 2 * COLUMNS
MAX_RESULTS = 15 * COLUMNS
TONES = {chr(code) for code in range(0x1F3FB, 0x1F400)}
# Unicode's categories and a tab glyph for each (Font Awesome, from the Nerd Font); the Component
# category is just hair and skin swatches
GROUPS = {
    "Smileys & Emotion": "\uf118", "People & Body": "\uf256", "Animals & Nature": "\uf1b0",
    "Food & Drink": "\uf0f5", "Travel & Places": "\uf1b9", "Activities": "\uf1e3", "Objects": "\uf0eb",
    "Symbols": "\uf292", "Flags": "\uf024",
}
FREQUENT_GLYPH = "\uf017"

CSS = """
window.emoji { background: $bg; }
window.emoji > windowhandle > .frame { background: $bg; color: $fg; border: 1px solid $border; }
.frame, .frame * { font-family: "BlexMono Nerd Font", monospace; border-radius: 0; box-shadow: none; outline-style: none; }
entry.query { background: $bg; color: $fg; border: none; border-bottom: 1px solid $faint; font-size: 13pt;
              padding: 10px 14px; min-height: 0; caret-color: $accent; }
entry.query image { color: $dim; margin-right: 8px; }
.grid { padding: 0 8px 8px 8px; }
.section { color: $dim; font-size: 9pt; padding: 10px 4px 4px 4px; }
.empty { color: $dim; font-size: 10pt; padding: 24px; }
.frame .cell, popover .cell { font-family: emoji; font-size: 19pt; min-width: 42px; min-height: 42px; }
.cell:hover { background: $hover; }
.frame .cell.selected, popover .cell.selected { background: $sel; }
popover > contents { background: $bg; border: 1px solid $border; border-radius: 0; padding: 2px; box-shadow: none; }
popover > arrow { background: $bg; border: 1px solid $border; }
.name { color: $fg; font-size: 9.5pt; padding: 6px 14px; border-top: 1px solid $faint; }
.tabs { border-top: 1px solid $faint; padding: 2px 8px; }
button.tab { background: transparent; color: $dim; font-family: "BlexMono Nerd Font Propo"; font-size: 12pt;
             padding: 5px 0; min-height: 0; border: none; }
button.tab:hover { color: $fg; }
button.tab.current { color: $accent; }
"""

############
### DATA ###
############


class Emoji:
    def __init__(self, char, name, keywords, tones):
        self.char, self.name, self.tones = char, name, tones  # tones: [(char, name)], one per skin tone
        self.name_words = name.replace(":", " ").split()
        self.words = self.name_words + keywords.split()


def parse():
    """[(category, [[char, name, keywords, tones]])] from Unicode's emoji list and CLDR's keywords."""
    keywords = {}
    for path in ANNOTATIONS:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for node in root.iter("annotation"):
            if node.get("type") != "tts" and node.text:
                keywords[node.get("cp")] = node.text.lower().replace(" | ", " ")
    groups, bases, group = [], {}, None
    with open(EMOJI_TEST) as f:
        for line in f:
            if line.startswith("# group: "):
                group = line[9:].strip()
                if group in GROUPS:
                    groups.append((group, []))
                continue
            if group not in GROUPS or "; fully-qualified" not in line:
                continue
            codes, _, comment = line.partition(";")
            char = "".join(chr(int(code, 16)) for code in codes.split())
            name = comment.partition("#")[2].split(None, 2)[2].strip().lower()
            # skin tone variants go with their emoji instead of filling the grid; mixed tones are left out
            key = "".join(c for c in char if c not in TONES and c != "️")
            tones = set(char) & TONES
            if tones:
                if len(tones) == 1 and key in bases:
                    bases[key][3].append((char, name))
                continue
            entry = [char, name, keywords.get(char) or keywords.get(char.replace("️", ""), ""), []]
            bases.setdefault(key, entry)
            groups[-1][1].append(entry)
    return groups


def load_emoji():
    """[(category, [Emoji])], cached until the emoji list or the keywords change."""
    stamp = []
    for path in [EMOJI_TEST] + ANNOTATIONS:
        try:
            stamp.append(os.stat(path).st_mtime)
        except OSError:
            stamp.append(None)
    try:
        with open(CACHE) as f:
            cached = json.load(f)
        if cached["stamp"] == stamp:
            groups = cached["groups"]
        else:
            raise ValueError
    except (OSError, ValueError, KeyError):
        groups = parse()
        try:
            with open(CACHE, "w") as f:
                json.dump({"stamp": stamp, "groups": groups}, f, ensure_ascii=False)
        except OSError:
            pass
    return [(group, [Emoji(*entry) for entry in entries]) for group, entries in groups]


def emoji_font():
    """[file, mtime] of the font emoji are drawn with."""
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", "emoji"], capture_output=True, text=True).stdout
        return [path, os.stat(path).st_mtime]
    except OSError:
        return None


def load_recent():
    """{char: [times picked, last picked]}"""
    try:
        with open(RECENT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def matches(emoji, terms, query):
    """How well an emoji matches (lower is better), or None."""
    if emoji.name == query:
        return 0
    if all(term in emoji.name_words for term in terms):  # "party" finds party popper first
        return 1
    if all(term in emoji.words for term in terms):  # whole words: "lol" finds 😂 before lollipop
        return 2
    if emoji.name.startswith(query):
        return 3
    if all(any(word.startswith(term) for word in emoji.name_words) for term in terms):
        return 4
    if all(any(word.startswith(term) for word in emoji.words) for term in terms):
        return 5
    return None


##############
### WINDOW ###
##############


class Picker(Gtk.ApplicationWindow):
    def __init__(self, app, groups):
        super().__init__(application=app, title="Emoji", css_classes=["emoji"], decorated=False, resizable=False)
        self.app = app
        self.recent = load_recent()
        self.rows = []  # the cells shown, row by row, for moving around with the keys
        self.selected = None  # (row, column)
        self.cell_emoji = {}  # cell -> (char, Emoji)
        self.sections = []  # (header, first row index, tab) of the category view
        self.tones = None  # (popover, [cells], selected index) while picking a skin tone

        groups = self.drop_unsupported(groups)
        self.all = [emoji for _group, emojis in groups for emoji in emojis]
        self.names = {emoji.char: emoji.name for emoji in self.all}
        self.names.update((char, name) for emoji in self.all for char, name in emoji.tones)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["frame"])
        self.entry = Gtk.Entry(css_classes=["query"], primary_icon_name="system-search-symbolic",
                               placeholder_text="search")
        self.entry.connect("changed", lambda _e: self.search())
        self.entry.connect("activate", lambda _e: self.pick_selected())
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)

        self.browse_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["grid"])
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["grid"])
        self.stack = Gtk.Stack()
        self.stack.add_named(self.browse_box, "browse")
        self.stack.add_named(self.results_box, "results")
        self.scroller = Gtk.ScrolledWindow(child=self.stack, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                           min_content_height=330)
        # "changed" comes once the sections have their sizes
        for signal in ("value-changed", "changed"):
            self.scroller.get_vadjustment().connect(signal, lambda _a: self.update_tabs())
        self.name = Gtk.Label(label=" ", xalign=0, css_classes=["name"], ellipsize=Pango.EllipsizeMode.END)
        self.tabs = Gtk.Box(css_classes=["tabs"], homogeneous=True)

        frequent = self.frequent()
        if frequent:
            self.add_section("frequently used", frequent, FREQUENT_GLYPH)
        for group, emojis in groups:
            self.add_section(group.lower(), [(self.shown(emoji), emoji) for emoji in emojis], GROUPS[group])
        self.browse_rows = self.rows

        frame.append(self.entry)
        frame.append(self.scroller)
        frame.append(self.name)
        frame.append(self.tabs)
        self.set_child(Gtk.WindowHandle(child=frame))  # drag the window by anything that isn't a control
        self.select(0, 0)
        self.update_tabs()

    # ----- building -----

    def drop_unsupported(self, groups):
        """Leave out emoji the emoji font can't draw as one picture (newer than the font, mostly).

        Checking takes half a second, so the answer is kept until the font changes."""
        font = emoji_font()
        try:
            with open(HIDDEN) as f:
                cached = json.load(f)
            hidden = set(cached["hidden"]) if cached["font"] == font else None
        except (OSError, ValueError, KeyError):
            hidden = None
        if hidden is None:
            layout = self.create_pango_layout("")
            layout.set_font_description(Pango.FontDescription("emoji 19"))

            def drawn(char):
                """(glyphs, font family) the char is drawn with; a family of None means a mix."""
                layout.set_text(char, -1)
                glyphs, families, it = layout.get_unknown_glyphs_count() * 2, set(), layout.get_iter()
                while True:
                    if run := it.get_run_readonly():
                        glyphs += run.glyphs.num_glyphs
                        families.add(run.item.analysis.font.describe().get_family())
                    if not it.next_run():
                        return glyphs, families.pop() if len(families) == 1 else None

            # one picture, from the same font as the rest (not a black-and-white fallback)
            family = drawn("\U0001F600")[1]

            def drawable(char):
                return drawn(char) == (1, family)

            hidden = {char for _group, emojis in groups for emoji in emojis
                      for char in [emoji.char] + [tone for tone, _name in emoji.tones[:1]] if not drawable(char)}
            try:
                with open(HIDDEN, "w") as f:
                    json.dump({"font": font, "hidden": sorted(hidden)}, f, ensure_ascii=False)
            except OSError:
                pass
        kept = []
        for group, emojis in groups:
            emojis = [emoji for emoji in emojis if emoji.char not in hidden]
            for emoji in emojis:
                if emoji.tones and emoji.tones[0][0] in hidden:
                    emoji.tones = []
            if emojis:
                kept.append((group, emojis))
        return kept

    def frequent(self):
        """[(char, Emoji)] most picked first, then most recently."""
        by_char = {emoji.char: emoji for emoji in self.all}
        by_char.update((char, emoji) for emoji in self.all for char, _name in emoji.tones)
        order = sorted(self.recent, key=lambda char: (-self.recent[char][0], -self.recent[char][1]))
        return [(char, by_char[char]) for char in order if char in by_char][:FREQUENT]

    def shown(self, emoji):
        """The emoji in the skin tone picked last, if one was."""
        if not emoji.tones:
            return emoji.char
        return max([emoji.char] + [char for char, _name in emoji.tones],
                   key=lambda char: self.recent.get(char, (0, 0))[1])

    def make_grid(self, cells):
        """A grid of (char, Emoji) cells; adds its rows to self.rows."""
        grid = Gtk.Grid(halign=Gtk.Align.START)
        for index, (char, emoji) in enumerate(cells):
            cell = Gtk.Label(label=char, css_classes=["cell"])
            self.cell_emoji[cell] = (char, emoji)
            grid.attach(cell, index % COLUMNS, index // COLUMNS, 1, 1)
            if index % COLUMNS == 0:
                self.rows.append([])
            self.rows[-1].append(cell)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", self.clicked, grid)
        grid.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.hovered, grid)
        motion.connect("leave", lambda _m: self.show_name())
        grid.add_controller(motion)
        return grid

    def add_section(self, title, cells, glyph):
        header = Gtk.Label(label=title, xalign=0, css_classes=["section"])
        first_row = len(self.rows)
        self.browse_box.append(header)
        self.browse_box.append(self.make_grid(cells))
        tab = Gtk.Button(label=glyph, css_classes=["tab"], focusable=False, tooltip_text=title)
        tab.connect("clicked", lambda _b, index=len(self.sections): self.jump_to(index))
        self.tabs.append(tab)
        self.sections.append((header, first_row, tab))

    # ----- moving around -----

    def cell(self, position):
        row, column = position
        return self.rows[row][column]

    def select(self, row, column):
        if self.selected:
            self.cell(self.selected).remove_css_class("selected")
        self.selected = None
        if not self.rows:
            self.show_name()
            return
        row = max(0, min(row, len(self.rows) - 1))
        column = max(0, min(column, len(self.rows[row]) - 1))
        self.selected = (row, column)
        cell = self.cell(self.selected)
        cell.add_css_class("selected")
        self.show_name()
        GLib.idle_add(lambda: self.scroll_to(cell) and False)  # once it has a size

    def move(self, step):
        """Left/right through every cell, wrapping from row to row."""
        row, column = self.selected or (0, 0)
        column += step
        if column < 0 and row > 0:
            row -= 1
            column = len(self.rows[row]) - 1
        elif column >= len(self.rows[row]) and row < len(self.rows) - 1:
            row, column = row + 1, 0
        self.select(row, column)

    def scroll_to(self, widget, top=False):
        ok, bounds = widget.compute_bounds(self.stack)
        if not ok:
            return
        adjustment = self.scroller.get_vadjustment()
        y, bottom = bounds.get_y(), bounds.get_y() + bounds.get_height()
        if top or y < adjustment.get_value():
            adjustment.set_value(y)
        elif bottom > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bottom - adjustment.get_page_size())

    def jump_to(self, index):
        """Show a category from its top and select its first emoji."""
        if self.entry.get_text():
            self.entry.set_text("")
        index = max(0, min(index, len(self.sections) - 1))
        header, first_row, _tab = self.sections[index]
        self.select(first_row, 0)
        GLib.idle_add(lambda: self.scroll_to(header, top=True) and False)

    def current_section(self):
        value = self.scroller.get_vadjustment().get_value()
        current = 0
        for index, (header, _row, _tab) in enumerate(self.sections):
            ok, bounds = header.compute_bounds(self.stack)
            if ok and bounds.get_y() <= value + 1:
                current = index
        return current

    def update_tabs(self):
        current = None if self.entry.get_text() else self.current_section()
        for index, (_header, _row, tab) in enumerate(self.sections):
            (tab.add_css_class if index == current else tab.remove_css_class)("current")

    def show_name(self, cell=None):
        cell = cell or (self.cell(self.selected) if self.selected else None)
        self.name.set_label(self.names.get(self.cell_emoji[cell][0], "") if cell else " ")

    # ----- searching -----

    def search(self):
        self.close_tones()
        query = " ".join(self.entry.get_text().lower().split())
        if self.selected:
            self.cell(self.selected).remove_css_class("selected")
            self.selected = None
        child = self.results_box.get_first_child()
        while child:
            self.results_box.remove(child)
            child = self.results_box.get_first_child()
        if not query:
            self.rows = self.browse_rows
            self.stack.set_visible_child_name("browse")
            self.select(0, 0)
            GLib.idle_add(lambda: self.scroller.get_vadjustment().set_value(0) and False)
            self.update_tabs()
            return
        terms = query.split()
        found = []
        for order, emoji in enumerate(self.all):
            rank = matches(emoji, terms, query)
            if rank is not None:
                uses = self.recent.get(self.shown(emoji), (0, 0))[0]
                found.append((rank, -uses, order, emoji))
        found.sort(key=lambda item: item[:3])
        self.rows = []
        if found:
            self.results_box.append(self.make_grid([(self.shown(e), e) for *_k, e in found[:MAX_RESULTS]]))
        else:
            self.results_box.append(Gtk.Label(label="no emoji found", css_classes=["empty"]))
        self.stack.set_visible_child_name("results")
        self.scroller.get_vadjustment().set_value(0)
        self.select(0, 0)
        self.update_tabs()

    # ----- skin tones -----

    def open_tones(self, cell):
        """A row of the emoji in each skin tone under the cell; arrows and enter pick one."""
        self.close_tones()
        _char, emoji = self.cell_emoji[cell]
        if not emoji.tones:
            return False
        box = Gtk.Box()
        cells = []
        for char, _name in [(emoji.char, emoji.name)] + emoji.tones:
            tone = Gtk.Label(label=char, css_classes=["cell"])
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, c=char: self.pick(c))
            tone.add_controller(click)
            box.append(tone)
            cells.append(tone)
        # not autohide: the keys stay with the window, which drives the popover itself
        popover = Gtk.Popover(child=box, autohide=False, can_focus=False, position=Gtk.PositionType.BOTTOM)
        popover.set_parent(cell)
        current = [char for char, _name in [(emoji.char, "")] + emoji.tones].index(self.cell_emoji[cell][0])
        self.tones = (popover, cells, current)
        cells[current].add_css_class("selected")
        popover.popup()
        return True

    def move_tone(self, step):
        popover, cells, current = self.tones
        cells[current].remove_css_class("selected")
        current = max(0, min(current + step, len(cells) - 1))
        cells[current].add_css_class("selected")
        self.tones = (popover, cells, current)
        self.name.set_label(self.names.get(cells[current].get_label(), ""))

    def close_tones(self):
        if self.tones:
            popover = self.tones[0]
            self.tones = None
            popover.popdown()
            popover.unparent()
            self.show_name()

    # ----- events -----

    def cell_at(self, grid, x, y):
        widget = grid.pick(x, y, Gtk.PickFlags.DEFAULT)
        return widget if widget in self.cell_emoji else None

    def clicked(self, gesture, _presses, x, y, grid):
        cell = self.cell_at(grid, x, y)
        if not cell:
            self.close_tones()
            return  # left unclaimed, so a drag from here moves the window
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if gesture.get_current_button() == Gdk.BUTTON_SECONDARY:
            self.select(*self.position_of(cell))
            self.open_tones(cell)
        else:
            self.pick(self.cell_emoji[cell][0])

    def hovered(self, _motion, x, y, grid):
        if not self.tones:
            self.show_name(self.cell_at(grid, x, y))

    def position_of(self, cell):
        for row, cells in enumerate(self.rows):
            if cell in cells:
                return row, cells.index(cell)
        return 0, 0

    def key_pressed(self, _controller, keyval, _keycode, state):
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        enter = keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
        if self.tones:
            if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
                self.move_tone(1 if keyval == Gdk.KEY_Right else -1)
                return True
            if enter:
                _popover, cells, current = self.tones
                self.pick(cells[current].get_label())
                return True
            self.close_tones()
            if keyval == Gdk.KEY_Escape:
                return True
        if keyval == Gdk.KEY_Escape:
            self.app.quit()
            return True
        if not self.selected and keyval != Gdk.KEY_Tab:
            return False
        row, column = self.selected or (0, 0)
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            self.move(1 if keyval == Gdk.KEY_Right else -1)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            self.select(row + (1 if keyval == Gdk.KEY_Down else -1), column)
            return True
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            back = shift or keyval == Gdk.KEY_ISO_Left_Tab
            if self.entry.get_text():
                self.jump_to(0)
            else:
                current = max(i for i, (_h, first, _t) in enumerate(self.sections) if first <= row)
                self.jump_to(current + (-1 if back else 1))
            return True
        if enter and shift:
            self.open_tones(self.cell(self.selected))
            return True
        return False

    def pick_selected(self):
        if self.selected:
            self.pick(self.cell_emoji[self.cell(self.selected)][0])

    def pick(self, char):
        count, _when = self.recent.get(char, (0, 0))
        self.recent[char] = (count + 1, time.time())
        try:
            os.makedirs(STATE, exist_ok=True)
            with open(RECENT, "w") as f:
                json.dump(self.recent, f, ensure_ascii=False)
        except OSError:
            pass
        self.app.picked = char
        self.close_tones()
        self.destroy()  # gone before typing, so the keys go to the window that was in front
        self.app.quit()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.picked = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(Template(CSS).substitute(load_theme()))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args[:1] in (["-h"], ["--help"]):
            command_line.print_literal(__doc__)
        elif self.window is not None and self.window.is_active():
            self.quit()
        elif self.window is not None:
            self.window.present()
        elif not os.path.exists(EMOJI_TEST):
            subprocess.run(["notify-send", "-a", "Emoji", "Emoji picker needs the emoji list",
                            "sudo dnf install unicode-emoji cldr-emoji-annotation google-noto-color-emoji-fonts"])
        else:
            self.window = Picker(self, load_emoji())
            self.window.present()
            self.window.entry.grab_focus()
        return 0


def main():
    app = App()
    status = app.run(sys.argv)
    if app.picked:
        subprocess.run(["wl-copy", app.picked])
        time.sleep(0.15)  # let focus go back to the window that was active before
        subprocess.run(["wtype", app.picked], stderr=subprocess.DEVNULL)
    return status


if __name__ == "__main__":
    sys.exit(main())
