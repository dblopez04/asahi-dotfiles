#!/usr/bin/env python3
"""Spotlight: find apps, settings, files and commands, do quick math, or search the web.

Usage: spotlight.py [--query TEXT] [--select PATH]    (Super+Space; running it again while it's open closes it)

--query starts with TEXT typed, and --select picks the result for PATH (Quick Look uses these to come back).

Also: conversions (5 km in miles, 72f to c, 20 usd to eur, 3pm in tokyo) and timers (timer 25m tea,
remind me at 5pm to call mom).

Keys: type to search, up/down pick, enter opens, ctrl+y quick looks a file, ctrl+t sends it with Taildrop,
      ctrl+enter shows it in its folder,
      esc closes (so does clicking away).

Browsing: start with ~ or / (or pick "browse files") to look through folders. Tab or enter goes into a
folder, shift+tab goes up, and typing after the last / filters the folder (a leading . shows hidden files).
Tab on any file or folder result jumps into browsing there.
"""
import ast
import importlib
import importlib.util
import json
import math
import operator
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from string import Template

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPTS)
from settings_pages.common import human_size, load_theme  # noqa: E402
import conversions  # noqa: E402
import timer as timers  # noqa: E402

APP_ID = "dev.dotfiles.Spotlight"
HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, ".local/bin")
STATE = os.path.join(GLib.get_user_state_dir(), "spotlight", "usage.json")
RECENT = os.path.join(GLib.get_user_data_dir(), "recently-used.xbel")
WAL = os.path.join(HOME, ".cache/wal")
WIDTH = 680
MAX_ROWS = 9
BROWSE_LIMIT = 300
HINT = "enter open   ctrl+y quick look   ctrl+t send   ctrl+enter show in folder   esc close"
BROWSE_HINT = "tab/enter open folder   shift+tab up   ctrl+y quick look   ctrl+t send   ctrl+enter show in folder"
SKIP_DIRS = ("/.cache/", "/.local/share/Trash/", "/node_modules/", "/.git/", "/__pycache__/", "/.claude/",
             "/.local/share/containers/", "/.npm/", "/.cargo/registry/", "/.var/app/", "/.mozilla/")

CSS = """
window.spotlight { background: $bg; }
window.spotlight > .frame { background: $bg; color: $fg; border: 1px solid $border; }
.frame, .frame * { font-family: "BlexMono Nerd Font", monospace; border-radius: 0; box-shadow: none; outline-style: none; }
entry.query { background: $bg; color: $fg; border: none; border-bottom: 1px solid $faint; font-size: 16pt;
              padding: 12px 16px; min-height: 0; caret-color: $accent; }
entry.query image { color: $dim; margin-right: 8px; }
list.results { background: transparent; padding: 4px; }
list.results row { background: transparent; color: $fg; padding: 5px 12px; min-height: 0; }
list.results row:hover { background: $hover; }
list.results row:selected { background: $sel; color: $sel_fg; }
list.results row:selected .detail, list.results row:selected .glyph { color: $sel_fg; }
.title { font-size: 11pt; }
.detail { color: $dim; font-size: 9pt; }
.glyph { color: $accent; font-family: "BlexMono Nerd Font Propo"; font-size: 14pt; min-width: 26px; }
.kind { color: $dim; font-size: 8.5pt; }
.hint { color: $dim; font-size: 9pt; padding: 6px 16px 8px 16px; border-top: 1px solid $faint; }
"""

COMMANDS = [
    # (title, keywords, glyph, command, confirm); a None command starts browsing files
    ("browse files", "files folders finder browse home directory", "\uf07c", None, False),
    ("lock screen", "lock", "", ["swaylock", "-f"], False),
    ("sleep", "suspend sleep", "", ["systemctl", "suspend"], False),
    ("log out", "logout exit sway quit", "", ["swaymsg", "exit"], True),
    ("restart", "reboot restart", "", ["systemctl", "reboot"], True),
    ("shut down", "shutdown poweroff power off", "", ["systemctl", "poweroff"], True),
    ("wallpaper picker", "wallpaper background theme colors", "", [f"{BIN}/wallpaper-picker.py"], False),
    ("clipboard history", "clipboard paste copied history", "", [f"{BIN}/clipboard-history.py", "pick"], False),
    ("stay awake", "caffeine awake keep sleep idle", "", [f"{BIN}/stay-awake.sh", "toggle"], False),
    ("notification center", "notifications", "", ["swaync-client", "-t", "-sw"], False),
    ("do not disturb", "dnd notifications quiet focus", "", ["swaync-client", "-d", "-sw"], False),
    ("color picker", "color picker eyedropper hex pixel", "\uf1fb", [f"{BIN}/color-picker.sh"], False),
    ("keyboard shortcuts", "keyboard shortcuts cheat sheet keys bindings", "\uf11c", [f"{BIN}/cheatsheet.py"], False),
    ("timers", "timers reminders cancel countdown", "\uf2f2", [f"{BIN}/timer.py", "menu"], False),
    ("reload sway", "reload refresh config", "", ["swaymsg", "reload"], False),
    ("screenshot area", "screenshot capture region", "",
     ["env", f"XDG_SCREENSHOTS_DIR={HOME}/Screenshots", "grimshot", "--notify", "savecopy", "area"], False),
]

#############
### MATCH ###
#############


def score(query, *fields):
    """How well query matches the best of fields (0 = not at all)."""
    best = 0
    for field in fields:
        if not field:
            continue
        text = field.lower()
        if text == query:
            best = max(best, 100)
        elif text.startswith(query):
            best = max(best, 85)
        elif re.search(r"(^|[\s\-_./])" + re.escape(query), text):
            best = max(best, 65)
        elif query in text:
            best = max(best, 45)
        elif all(word in text for word in query.split()):
            best = max(best, 35)
        else:
            it = iter(text)
            if len(query) >= 3 and all(c in it for c in query.replace(" ", "")):
                best = max(best, 15)
    return best


############
### MATH ###
############

OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
             ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
             ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCTIONS = {name: getattr(math, name) for name in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp",
                                                     "floor", "ceil", "factorial", "radians", "degrees")}
FUNCTIONS.update(abs=abs, round=round)
CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def calculate(text):
    """The value of a math expression, or None if text isn't one."""
    expression = text.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    expression = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expression)
    if not re.search(r"\d", expression) or not re.search(r"[-+*/()]|\*\*|sqrt|sin|cos|tan|log|exp|pi", expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None

    def value(node):
        if isinstance(node, ast.Expression):
            return value(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("too big")
            return OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](value(node.operand))
        if isinstance(node, ast.Name) and node.id in CONSTANTS:
            return CONSTANTS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            return FUNCTIONS[node.func.id](*[value(a) for a in node.args])
        raise ValueError("not math")

    try:
        result = value(tree)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    if isinstance(result, float):
        if result.is_integer() and abs(result) < 1e15:
            return str(int(result))
        return f"{result:.10g}"
    return str(result)


#############
### FILES ###
#############


def recent_files():
    """Recently opened files, newest first, from GTK's recently-used list."""
    try:
        root = ET.parse(RECENT).getroot()
    except (OSError, ET.ParseError):
        return []
    items = []
    for bookmark in root.iter("bookmark"):
        href = bookmark.get("href", "")
        if href.startswith("file://"):
            path = urllib.parse.unquote(href[7:])
            if os.path.exists(path):
                items.append((bookmark.get("visited") or bookmark.get("modified") or "", path))
    return [path for _when, path in sorted(items, reverse=True)]


def find_files(query):
    """Files and folders under ~ whose names match, from the plocate index (refreshed daily)."""
    words = query.split()
    try:
        out = subprocess.run(["plocate", "-i", "-b", "-l", "400", *words], capture_output=True, text=True,
                             timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    results = []
    for path in out.splitlines():
        if not path.startswith(HOME + "/") or any(skip in path + "/" for skip in SKIP_DIRS):
            continue
        relative = path[len(HOME) + 1:]
        if any(part.startswith(".") for part in relative.split("/")[:-1]):
            continue  # inside hidden folders (except the dotfiles repo's own name matches)
        if os.path.exists(path):
            results.append(path)
    name_score = lambda p: (score(query.lower(), os.path.basename(p)), -p.count("/"))
    return sorted(results, key=name_score, reverse=True)[:8]


def browse(text):
    """For a path query like ~/Doc or /etc/sy: (folder, filter text, [(path, is folder)]), where the list is
    None if the folder can't be read."""
    expanded = HOME + "/" if text == "~" else os.path.expanduser(text)
    folder, _, name = expanded.rpartition("/")
    folder = folder or "/"
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return folder, name, None
    items = []
    for entry in entries:
        if entry.name.startswith(".") and not name.startswith("."):
            continue
        rank = score(name.lower(), entry.name) if name else 1
        if not rank:
            continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            is_dir = False
        items.append((rank, is_dir, entry.path))
    items.sort(key=lambda i: (-i[0], not i[1], os.path.basename(i[2]).lower()))
    return folder, name, [(path, is_dir) for _rank, is_dir, path in items[:BROWSE_LIMIT]]


###########
### APP ###
###########


class Result:
    def __init__(self, kind, title, detail, glyph=None, gicon=None, action=None, reveal=None, rank=0, confirm=False,
                 path=None):
        self.kind, self.title, self.detail, self.path = kind, title, detail, path
        self.glyph, self.gicon = glyph, gicon
        self.action, self.reveal = action, reveal
        self.rank, self.confirm = rank, confirm


class Spotlight(Gtk.ApplicationWindow):
    def __init__(self, app, query="", select=None):
        super().__init__(application=app, title="Spotlight", css_classes=["spotlight"], decorated=False,
                         resizable=False, default_width=WIDTH)
        self.app = app
        self.results = []
        self.file_results = []
        self.search_id = 0
        self.armed = None  # a command waiting for a second enter
        self.pending_select = select  # a path to select once its result shows up
        self.was_active = False
        self.usage = self.load_usage()
        self.apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
        self.pages = self.settings_pages()
        self.recent = []
        threading.Thread(target=lambda: setattr(self, "recent", recent_files()), daemon=True).start()

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["frame"])
        self.entry = Gtk.Entry(css_classes=["query"], primary_icon_name="system-search-symbolic")
        self.entry.connect("changed", lambda _e: self.search())
        self.entry.connect("activate", lambda _e: self.activate_selected())
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)
        self.list = Gtk.ListBox(css_classes=["results"], selection_mode=Gtk.SelectionMode.BROWSE,
                                activate_on_single_click=True)
        self.list.connect("row-activated", lambda _l, row: self.activate(row.get_index()))
        self.hint = Gtk.Label(label=HINT, xalign=0, css_classes=["hint"])
        # grows with the results, then scrolls (folders can be long)
        self.scroller = Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                           propagate_natural_height=True, max_content_height=470)
        self.browsing = None  # the folder being browsed, or None
        frame.append(self.entry)
        frame.append(self.scroller)
        frame.append(self.hint)
        self.set_child(frame)
        self.connect("notify::is-active", self.focus_changed)
        if query:
            self.set_query(query)
        else:
            self.search()

    # ----- sources -----

    @staticmethod
    def load_usage():
        try:
            with open(STATE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def remember(self, key):
        self.usage[key] = self.usage.get(key, 0) + 1
        try:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            with open(STATE, "w") as f:
                json.dump(self.usage, f)
        except OSError:
            pass

    @staticmethod
    def settings_pages():
        pages = []
        try:
            panel = importlib.util.spec_from_file_location("settings_panel", os.path.join(SCRIPTS, "settings-panel.py"))
            module = importlib.util.module_from_spec(panel)
            panel.loader.exec_module(module)
            for module_name, class_name, *_group in module.PAGES:
                cls = getattr(importlib.import_module(f"settings_pages.{module_name}"), class_name)
                pages.append((module_name, cls.name, (cls.__doc__ or "").strip().split("\n")[0]))
        except Exception:
            pass
        return pages

    def search(self):
        raw = self.entry.get_text()
        self.armed = None
        if raw.startswith(("~", "/")):
            self.search_id += 1  # drop any file search still running
            self.show_folder(raw)
            return
        if self.browsing is not None:
            self.browsing = None
            self.hint.set_label(HINT)
        query = raw.strip().lower()
        results = []
        if not query:
            ranked = sorted(self.apps, key=lambda a: -self.usage.get(a.get_id() or "", 0))[:MAX_ROWS - 1]
            results = [self.app_result(a, 0) for a in ranked]
            self.show(results)
            return

        raw_query = raw.strip()
        timer = timers.parse(raw_query)
        if timer:
            kind, end, label = timer
            if kind == "timer":
                seconds = round(end - time.time())
                title = f"start a {timers.left(seconds)} timer" + (f" · {label}" if label else "")
                command = [f"{BIN}/timer.py", "add", str(seconds), *label.split()]
            else:
                when = time.strftime("%-I:%M %p", time.localtime(end)).lower()
                title = f"remind me at {when}" + (f" · {label}" if label else "")
                command = [f"{BIN}/timer.py", "at", str(int(end)), *label.split()]
            results.append(Result("timer", title, "enter starts it · shows in the bar", glyph="\uf2f2", rank=1000,
                                  action=lambda c=command: self.run(c)))
        converted = conversions.convert(raw_query)
        if converted:
            for answer, detail in converted:
                results.append(Result("math", answer, detail, glyph="\uf0ec", rank=1000,
                                      action=lambda a=answer: self.copy(a)))
        elif base := conversions.currency_request(raw_query):
            # rates aren't cached yet: fetch them, then search again if the query hasn't changed
            def fetch(base=base, text=raw):
                if conversions.fetch_rates(base):
                    GLib.idle_add(lambda: self.entry.get_text() == text and self.search() and False)
            threading.Thread(target=fetch, daemon=True).start()
            results.append(Result("math", "getting today's exchange rates…", "", glyph="\uf0ec", rank=1000))
        value = calculate(query)
        if value is not None:
            results.append(Result("math", f"= {value}", "enter copies the result", glyph="", rank=1000,
                                  action=lambda v=value: self.copy(v)))

        for app in self.apps:
            s = score(query, app.get_display_name(), app.get_name(), app.get_executable(),
                      " ".join(app.get_keywords() or []) if hasattr(app, "get_keywords") else "",
                      app.get_description() or "")
            if s:
                results.append(self.app_result(app, s + min(15, self.usage.get(app.get_id() or "", 0))))
        for module_name, name, doc in self.pages:
            s = score(query, name, f"settings {name}", doc)
            if s:
                results.append(Result("settings", name, "settings", glyph="", rank=s - 5,
                                      action=lambda m=module_name: self.run([f"{BIN}/settings-panel.py", m])))
        for title, keywords, glyph, command, needs_confirm in COMMANDS:
            s = score(query, title, keywords)
            if s and command is None:
                results.append(Result("browse", title, "look through your folders (or type ~/)", glyph=glyph,
                                      rank=s - 8, action=lambda: self.set_query("~/")))
                continue
            if s:
                detail = "turn off" if title == "stay awake" and self.staying_awake() else "command"
                results.append(Result("command", title, detail, glyph=glyph, rank=s - 8, confirm=needs_confirm,
                                      action=lambda c=command, t=title: (self.remember(f"cmd:{t}"), self.run(c))))
        for path in self.recent:
            s = score(query, os.path.basename(path))
            if s >= 45:
                results.append(self.file_result(path, s - 10, recent=True))

        results.sort(key=lambda r: -r.rank)
        results = results[:MAX_ROWS - 1]
        results.append(Result("web", f"search the web for “{self.entry.get_text().strip()}”", "duckduckgo",
                              glyph="", rank=-1,
                              action=lambda q=self.entry.get_text().strip(): self.open_uri(
                                  "https://duckduckgo.com/?q=" + urllib.parse.quote(q))))
        self.base_results = results
        self.show(results)

        # files come from plocate on a thread; they're added below the other matches
        self.search_id += 1
        search_id = self.search_id
        if len(query) >= 2:
            def work():
                files = find_files(query)
                GLib.idle_add(lambda: self.add_files(search_id, files) and False)
            GLib.timeout_add(120, lambda: search_id == self.search_id and threading.Thread(target=work, daemon=True).start() and False)

    def show_folder(self, text):
        folder, name, items = browse(text)
        self.browsing = folder
        self.hint.set_label(BROWSE_HINT)
        results = []
        if items is None:
            results.append(Result("browse", "can't open this folder", self.short(folder), glyph="\uf071"))
        else:
            if folder != "/" and not name:
                parent = os.path.dirname(folder.rstrip("/")) or "/"
                results.append(Result("folder", "..", f"up to {self.short(parent)}", glyph="\uf062", path=parent,
                                      action=lambda p=parent: self.set_query(self.as_query(p) + "/")))
            for path, is_dir in items:
                results.append(self.browse_result(path, is_dir))
            if not items:
                results.append(Result("browse", "nothing here" if not name else f"nothing matching “{name}”",
                                      self.short(folder), glyph="\uf05a"))
        self.show(results)
        # start on the first entry, not the .. row, so enter opens something
        if results and results[0].title == ".." and len(results) > 1 and results[1].path and not self.pending_select:
            self.list.select_row(self.list.get_row_at_index(1))

    def browse_result(self, path, is_dir):
        try:
            stat = os.stat(path)
            when = time.strftime("%b %-d %Y", time.localtime(stat.st_mtime)).lower()
            detail = f"folder  ·  {when}" if is_dir else f"{human_size(stat.st_size)}  ·  {when}"
        except OSError:
            detail = "folder" if is_dir else ""
        if is_dir:
            return Result("folder", os.path.basename(path) + "/", detail, glyph="\uf07b", path=path,
                          action=lambda p=path: self.set_query(self.as_query(p) + "/"),
                          reveal=lambda p=path: self.run(["nautilus", p]))
        return Result("file", os.path.basename(path), detail, glyph="\uf15b", path=path,
                      action=lambda p=path: self.open_uri(Gio.File.new_for_path(p).get_uri()),
                      reveal=lambda p=path: self.run(["nautilus", "--select", p]))

    @staticmethod
    def as_query(path):
        path = path.rstrip("/") or "/"
        return "~" + path[len(HOME):] if path == HOME or path.startswith(HOME + "/") else path

    def set_query(self, text):
        self.entry.set_text(text)
        self.entry.set_position(-1)

    def add_files(self, search_id, files):
        if search_id != self.search_id:
            return
        shown = {r.detail for r in self.base_results if r.kind == "file"}
        extra = [self.file_result(path, 30) for path in files if self.short(os.path.dirname(path)) not in shown
                 or os.path.basename(path) not in {r.title for r in self.base_results}]
        others = [r for r in self.base_results if r.kind != "web"]
        web = [r for r in self.base_results if r.kind == "web"]
        room = max(2, MAX_ROWS + 3 - len(others) - 1)
        self.show(others + extra[:room] + web, keep_selection=True)

    def app_result(self, app, rank):
        detail = app.get_description() or app.get_generic_name() if hasattr(app, "get_generic_name") else ""
        return Result("app", app.get_display_name(), (detail or "application")[:70], gicon=app.get_icon(), rank=rank,
                      action=lambda a=app: (self.remember(a.get_id() or ""), self.launch(a)))

    def file_result(self, path, rank, recent=False):
        is_dir = os.path.isdir(path)
        return Result("file", os.path.basename(path), self.short(os.path.dirname(path)) + ("  · recent" if recent else ""),
                      glyph="" if is_dir else "", rank=rank, path=path,
                      action=lambda p=path: self.open_uri(Gio.File.new_for_path(p).get_uri()),
                      reveal=lambda p=path: self.run(["nautilus", "--select", p]))

    @staticmethod
    def short(path):
        return "~" + path[len(HOME):] if path.startswith(HOME) else path

    @staticmethod
    def staying_awake():
        return os.path.exists(os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "stay-awake"))

    # ----- showing -----

    def show(self, results, keep_selection=False):
        selected = self.list.get_selected_row()
        index = selected.get_index() if (selected and keep_selection) else 0
        self.results = results
        while child := self.list.get_first_child():
            self.list.remove(child)
        for result in results:
            box = Gtk.Box(spacing=10)
            if result.gicon is not None:
                icon = Gtk.Image(gicon=result.gicon, pixel_size=24)
                icon.set_size_request(26, -1)
            else:
                icon = Gtk.Label(label=result.glyph or "", css_classes=["glyph"])
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
            title = Gtk.Label(label=result.title, xalign=0, css_classes=["title"], ellipsize=Pango.EllipsizeMode.END)
            texts.append(title)
            if result.detail:
                texts.append(Gtk.Label(label=result.detail, xalign=0, css_classes=["detail"],
                                       ellipsize=Pango.EllipsizeMode.MIDDLE))
            box.append(icon)
            box.append(texts)
            box.append(Gtk.Label(label=result.kind if result.kind != "web" else "", css_classes=["kind"]))
            self.list.append(Gtk.ListBoxRow(child=box))
        if not keep_selection:
            self.scroller.get_vadjustment().set_value(0)
        if row := self.list.get_row_at_index(min(index, len(results) - 1)):
            self.list.select_row(row)
        self.select_pending()

    def select_pending(self):
        if not self.pending_select:
            return
        for index, result in enumerate(self.results):
            if result.path == self.pending_select:
                row = self.list.get_row_at_index(index)
                self.list.select_row(row)
                GLib.idle_add(lambda: self.scroll_to(row) and False)  # once the rows have sizes
                return

    def scroll_to(self, row):
        ok, bounds = row.compute_bounds(self.list)
        if not ok:
            return
        adjustment = self.scroller.get_vadjustment()
        top, bottom = bounds.get_y(), bounds.get_y() + bounds.get_height()
        if top < adjustment.get_value():
            adjustment.set_value(top)
        elif bottom > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bottom - adjustment.get_page_size())

    # ----- acting -----

    def key_pressed(self, _controller, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == Gdk.KEY_Escape:
            self.app.quit()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up) or (ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_p, Gdk.KEY_j, Gdk.KEY_k)):
            step = 1 if keyval in (Gdk.KEY_Down, Gdk.KEY_n, Gdk.KEY_j) else -1
            row = self.list.get_selected_row()
            index = (row.get_index() if row else -1) + step
            if target := self.list.get_row_at_index(max(0, min(index, len(self.results) - 1))):
                self.list.select_row(target)
                self.scroll_to(target)
                self.pending_select = None
                self.armed = None
                self.hint.set_label(BROWSE_HINT if self.browsing is not None else HINT)
            return True
        if keyval == Gdk.KEY_ISO_Left_Tab or (keyval == Gdk.KEY_Tab and state & Gdk.ModifierType.SHIFT_MASK):
            if self.browsing is not None and self.browsing != "/":
                self.set_query(self.as_query(os.path.dirname(self.browsing.rstrip("/")) or "/") + "/")
            return True
        if keyval == Gdk.KEY_Tab:
            # into the selected folder, or start browsing where the selected file is
            row = self.list.get_selected_row()
            result = self.results[row.get_index()] if row else None
            if result and result.path:
                if os.path.isdir(result.path):
                    self.set_query(self.as_query(result.path) + "/")
                elif self.browsing is not None:
                    self.set_query(self.as_query(result.path))
                else:
                    self.set_query(self.as_query(os.path.dirname(result.path)) + "/")
            elif self.browsing is None and not self.entry.get_text():
                self.set_query("~/")
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and ctrl:
            row = self.list.get_selected_row()
            if row and self.results[row.get_index()].reveal:
                self.results[row.get_index()].reveal()
                self.app.quit()
            return True
        if ctrl and keyval in (Gdk.KEY_t, Gdk.KEY_T):
            # send the selected file to another device with Taildrop
            row = self.list.get_selected_row()
            result = self.results[row.get_index()] if row else None
            if result and result.path and os.path.isfile(result.path):
                self.run([f"{BIN}/taildrop.py", "send", result.path])
                self.app.quit()
            return True
        if ctrl and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            # Quick Look, like Cmd+Y on macOS; Spotlight closes so the preview gets the keyboard
            row = self.list.get_selected_row()
            result = self.results[row.get_index()] if row else None
            if result and result.path:
                self.run([f"{BIN}/quicklook.py", "--back", self.entry.get_text(), result.path])
                self.app.quit()
            return True
        return False

    def activate_selected(self):
        row = self.list.get_selected_row()
        if row:
            self.activate(row.get_index())

    def activate(self, index):
        result = self.results[index]
        if result.confirm and self.armed is not result:
            self.armed = result
            self.hint.set_label(f"press enter again to {result.title}")
            return
        if result.action:
            result.action()
        if result.kind not in ("math", "folder", "browse"):
            self.app.quit()

    def launch(self, app):
        context = Gdk.Display.get_default().get_app_launch_context()
        # sway starts us without ~/.local/bin on the PATH; apps shouldn't inherit that
        context.setenv("PATH", f"{BIN}:{os.environ.get('PATH', '/usr/bin')}")
        try:
            app.launch([], context)
        except GLib.Error:
            pass

    def run(self, command):
        env = dict(os.environ, PATH=f"{BIN}:{os.environ.get('PATH', '/usr/bin')}")
        try:
            subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass

    def open_uri(self, uri):
        try:
            Gio.AppInfo.launch_default_for_uri(uri, Gdk.Display.get_default().get_app_launch_context())
        except GLib.Error:
            self.run(["xdg-open", uri])

    def copy(self, text):
        Gdk.Display.get_default().get_clipboard().set(text)
        self.hint.set_label(f"copied {text}")
        # the clipboard only lives as long as this window; hand it to wl-copy before closing
        self.run(["wl-copy", text])
        GLib.timeout_add(400, lambda: self.app.quit() or False)

    def focus_changed(self, *_):
        if self.is_active():
            self.was_active = True
        elif self.was_active:
            self.app.quit()  # clicked away, like Spotlight


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
        args = command_line.get_arguments()[1:]
        query = args[args.index("--query") + 1] if "--query" in args[:-1] else ""
        select = args[args.index("--select") + 1] if "--select" in args[:-1] else None
        if args[:1] in (["-h"], ["--help"]):
            command_line.print_literal(__doc__)
        elif self.window is None:
            self.window = Spotlight(self, query, select)
            self.window.present()
            self.window.entry.grab_focus()
            self.window.entry.set_position(-1)  # grabbing focus selects everything; keep a returning query editable
        else:
            self.quit()
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
