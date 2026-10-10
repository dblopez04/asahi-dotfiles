import json
import os
import stat
import subprocess
import threading
import time

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

import dotconfig

from .common import (HOME, ItemList, Page, SegmentBar, V, button, human_size, in_background, label, load_theme)

CACHE = os.path.join(HOME, ".cache/settings-panel/storage.json")
MAX_AGE = 3600
TRASH = os.path.join(HOME, ".local/share/Trash")
CATEGORIES = [
    # (name, paths, color key)
    ("apps", ["/usr", "/opt", "/var/lib/flatpak", os.path.join(HOME, ".local/share/flatpak")], "c1"),
    ("documents", [os.path.join(HOME, d) for d in ("Documents", "Desktop", "Downloads")], "c2"),
    ("media", [os.path.join(HOME, d) for d in ("Pictures", "Videos", "Music", "Screenshots", "wallpapers")], "c3"),
    ("developer", [os.path.join(HOME, d) for d in (".local/share/containers", ".npm", ".cache/pnpm",
                                                   ".local/share/pnpm", ".cargo", ".rustup", ".bun", "go",
                                                   ".vscode", ".config/Code")] + [dotconfig.DOTFILES], "c4"),
    ("caches", [os.path.join(HOME, ".cache"), "/var/cache"], "c5"),
    ("system", ["/var/log", "/var/lib", "/boot"], "c6"),
    ("trash", [TRASH], "dim"),
]
# where the browser can start besides the categories' own folders: (title, target)
ROOTS = {"home": ("home", ("dir", HOME)), "other": ("whole disk", ("dir", "/"))}
SHOWN = 50  # the biggest entries listed in a folder


def du(paths):
    """Bytes used by paths on the root filesystem, counting hard links once."""
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return 0
    try:
        out = subprocess.run(["nice", "-n", "19", "ionice", "-c", "3", "du", "-sxbc", *existing],
                             capture_output=True, text=True, timeout=600).stdout
        return int(out.strip().splitlines()[-1].split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


def measure():
    result = {"time": time.time(), "categories": {}}
    for name, paths, _color in CATEGORIES:
        result["categories"][name] = du(paths)
    save(result)
    return result


def save(result):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(result, f)


def tilde(path):
    return "~" + path[len(HOME):] if path == HOME or path.startswith(HOME + "/") else path


def inside(path, folder):
    return path == folder or path.startswith(folder.rstrip("/") + "/")


###############
### FOLDERS ###
###############

# Folder sizes for this session (path -> bytes on disk), filled in by every listing: the folders in a
# listing and two levels below them, so going into a folder is usually instant.
SIZES = {}
KEEP = 2
LISTINGS = {}  # target -> finished entries


class Cancelled(Exception):
    pass


def mounts():
    """(disk mounts, virtual mounts like /proc and /run): only disk mounts are followed into."""
    disks, virtual = set(), set()
    try:
        with open("/proc/self/mounts") as f:
            for line in f:
                source, point = line.split()[:2]
                point = point.replace("\\040", " ")
                (disks if source.startswith("/dev/") else virtual).add(point)
    except (OSError, ValueError):
        pass
    return disks, virtual - disks


class Scan:
    """One listing's walk: hard links counted once, cancelled when the page moves on."""

    def __init__(self):
        self.cancel = threading.Event()
        self.seen = set()
        self.disks, self.virtual = mounts()

    def usage(self, st):
        if st.st_nlink > 1 and not stat.S_ISDIR(st.st_mode):
            if (st.st_dev, st.st_ino) in self.seen:
                return 0
            self.seen.add((st.st_dev, st.st_ino))
        return st.st_blocks * 512

    def folder(self, path, st):
        """Bytes used by a folder and everything in it, without following symlinks."""
        if path in SIZES:
            return SIZES[path]
        size = self.usage(st) + self.contents(path, st.st_dev, 0)
        SIZES[path] = size
        return size

    def contents(self, path, dev, depth):
        total = 0
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if self.cancel.is_set():
                        raise Cancelled
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if not stat.S_ISDIR(st.st_mode):
                        total += self.usage(st)
                    elif entry.path in SIZES:
                        total += SIZES[entry.path]
                    elif depth < 200 and (st.st_dev == dev or entry.path in self.disks):
                        size = self.usage(st) + self.contents(entry.path, st.st_dev, depth + 1)
                        if depth < KEEP:
                            SIZES[entry.path] = size
                        total += size
        except OSError:
            pass
        return total


def scan(target, job, progress):
    """Entries [name, path, is_dir, size] for a target: ("dir", path) lists a folder, ("paths", paths)
    lists those paths. Files are sized right away and folders one by one, with progress(entries) between."""
    kind, value = target
    if kind == "dir":
        try:
            with os.scandir(value) as it:
                found = [(entry.name, entry.path) for entry in it]
        except OSError as e:
            raise OSError(e.strerror.lower() if e.strerror else str(e)) from None
    else:
        found = [(tilde(path), path) for path in value]
    entries, folders = [], []
    for name, path in found:
        if path in job.virtual:
            continue
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            entry = [name, path, True, SIZES.get(path)]
            if entry[3] is None:
                folders.append((entry, st))
        else:
            entry = [name, path, False, job.usage(st)]
        entries.append(entry)
    progress(entries)
    last = time.monotonic()
    for entry, st in folders:
        entry[3] = job.folder(entry[1], st)
        if time.monotonic() - last > 0.25:
            progress(entries)
            last = time.monotonic()
    return entries


def forget(path):
    """Drop cached sizes that change when path goes away: its own, what's in it, and its parents'."""
    for key in list(SIZES):
        if inside(key, path) or inside(path, key):
            SIZES.pop(key, None)
    LISTINGS.clear()


def reveal(path, is_dir):
    """Open a folder, or show a file in its folder, in the file manager."""
    uri = Gio.File.new_for_path(path).get_uri()
    parent = Gio.File.new_for_path(os.path.dirname(path)).get_uri()

    def fallback():
        try:
            Gio.AppInfo.launch_default_for_uri(uri if is_dir else parent, None)
        except GLib.Error:
            pass

    def called(bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error:
            fallback()

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        fallback()
        return
    bus.call("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1",
             "ShowFolders" if is_dir else "ShowItems", GLib.Variant("(ass)", ([uri], "")), None,
             Gio.DBusCallFlags.NONE, 10000, None, called)


############
### PAGE ###
############


class StoragePage(Page):
    name = "storage"

    def __init__(self, panel):
        super().__init__(panel)
        self.measuring = False
        self.data = None
        self.disk = label("", "accent", "row")
        self.bar = SegmentBar(18)
        self.bar.set_margin_start(8)
        self.bar.set_margin_end(8)
        self.legend = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                  min_children_per_line=2, column_spacing=12)
        self.legend.connect("child-activated", lambda _f, child: self.browse(self.legend_names[child.get_index()]))
        self.legend_names = []
        self.status = label("", "dim", "row")
        self.add(self.disk, self.bar, self.legend, self.status)

        # the folder browser: the biggest things in a category or folder
        self.up_button = button("up", self.up, tooltip="Back up a folder (Backspace)")
        self.section("contents", self.up_button, button("home", lambda: self.browse("home")),
                     button("measure again", self.measure_again))
        self.crumbs = Gtk.Box(css_classes=["row"])
        self.add(self.crumbs)
        self.browser = Gtk.Box(orientation=V)
        self.list = ItemList(self.activate, empty="measuring...")
        self.browser.append(self.list)
        self.add(self.browser)
        self.summary = label("", "dim", "row")
        self.add(self.summary)
        self.add(label("click a category above or a folder to look inside · right-click (or the menu key) to open "
                       "it in the file browser or move it to the trash", "dim", "row", wrap=True))

        # right-click menu, in the dropdowns' style
        self.menu = Gtk.Popover(css_classes=["choices"], has_arrow=False, position=Gtk.PositionType.BOTTOM,
                                halign=Gtk.Align.START)
        self.menu_items = Gtk.Box(orientation=V)
        self.menu.set_child(self.menu_items)
        self.menu.set_parent(self.browser)
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self._right_click)
        self.browser.add_controller(click)

        self.root = "home"  # the category (or ROOTS key) being browsed
        self.trail = [ROOTS["home"]]  # [(title, target)]; the last one is shown
        self.entries = {}  # path -> [name, path, is_dir, size]
        self.job = None
        self.focus_key = None  # the entry to focus once it's listed (True: the first one)
        self.menu_path = None

    def shown(self):
        self.start()
        self.load()

    def hidden(self):
        super().hidden()
        self.menu.popdown()
        if self.job:
            self.job.cancel.set()

    # ----- usage totals -----

    def start(self, force=False):
        cached = None
        try:
            with open(CACHE) as f:
                cached = json.load(f)
        except (OSError, ValueError):
            pass
        if cached:
            self.show(cached)
        if self.measuring or (cached and not force and time.time() - cached.get("time", 0) < MAX_AGE):
            return
        self.measuring = True
        self.status.set_label("measuring (this takes a minute)..." if not cached else "updating...")
        in_background(measure, self._measured)

    def _measured(self, result):
        self.measuring = False
        if isinstance(result, Exception):
            self.status.set_label(f"couldn't measure: {result}")
            return
        self.show(result)

    def measure_again(self):
        SIZES.clear()
        LISTINGS.clear()
        self.start(force=True)
        self.load()

    def show(self, data):
        self.data = data
        theme = load_theme()
        disk = os.statvfs("/")
        size, free = disk.f_blocks * disk.f_frsize, disk.f_bavail * disk.f_frsize
        used = size - free
        self.disk.set_label(f"{human_size(used)} of {human_size(size)} used  ·  {human_size(free)} available")
        segments, legend = [], []
        counted = 0
        for name, _paths, color in CATEGORIES:
            amount = min(data["categories"].get(name, 0), max(0, used - counted))
            counted += amount
            segments.append((amount / size, theme[color]))
            legend.append((name, amount, theme[color]))
        other = max(0, used - counted)
        segments.append((other / size, theme["faint"] if theme["faint"] != theme["hover"] else theme["fg"]))
        legend.append(("other", other, theme["fg"]))
        self.bar.set_segments(segments, theme["hover"])
        while child := self.legend.get_first_child():
            self.legend.remove(child)
        for name, amount, color in legend:
            box = Gtk.Box(spacing=6)
            swatch = label("■")
            swatch.set_markup(f'<span foreground="{color}">■</span>')
            box.append(swatch)
            box.append(label(f"{name} {human_size(amount)}", "dim"))
            self.legend.append(box)
        self.legend_names = [name for name, _amount, _color in legend]
        self._mark_legend()
        age = int((time.time() - data.get("time", 0)) / 60)
        if not self.measuring:
            self.status.set_label(f"measured {age} min ago" if age else "measured just now")

    def _mark_legend(self):
        for i, name in enumerate(self.legend_names):
            child = self.legend.get_child_at_index(i)
            (child.add_css_class if name == self.root else child.remove_css_class)("current")

    def _account_trashed(self, path, size, to_home_trash):
        """Move a trashed item's size from its categories to the trash, without measuring again."""
        if not self.data or not size:
            return
        categories = self.data["categories"]
        for name, paths, _color in CATEGORIES:
            if name != "trash" and any(inside(path, p) for p in paths):
                categories[name] = max(0, categories.get(name, 0) - size)
        if to_home_trash:
            categories["trash"] = categories.get("trash", 0) + size
        try:
            save(self.data)
        except OSError:
            pass
        self.show(self.data)

    # ----- the folder browser -----

    def browse(self, name):
        self.root = name
        if name in ROOTS:
            self.trail = [ROOTS[name]]
        else:
            self.trail = [(name, ("paths", tuple(next(paths for n, paths, _c in CATEGORIES if n == name))))]
        self.load(focus=True)

    def go(self, depth):
        if depth < len(self.trail) - 1:
            self.focus_key = self.trail[depth + 1][1][1]  # back on the folder we came out of
            self.trail = self.trail[:depth + 1]
            self.load()

    def up(self):
        self.go(len(self.trail) - 2)

    def activate(self, path):
        entry = self.entries.get(path)
        if not entry:
            return
        if entry[2]:
            title = entry[0] if self.trail[-1][1][0] == "dir" else tilde(path)
            self.trail.append((title, ("dir", path)))
            self.load(focus=True)
        else:
            self.open_menu(path, self.list.buttons.get(path))

    def load(self, focus=False):
        """List the folder at the end of the trail: cached, or measured in the background."""
        if self.job:
            self.job.cancel.set()
        self.menu.popdown()
        if focus:
            self.focus_key = True  # the first entry
        self._update_crumbs()
        self._mark_legend()
        target = self.trail[-1][1]
        self.entries = {}
        if target in LISTINGS:
            self.job = None
            self._show_entries(LISTINGS[target], True)
            return
        self.list.empty = "measuring..."
        self.list.set_items([], force=True)
        self.summary.set_label("")
        job = self.job = Scan()

        def progress(entries):
            snapshot = [list(e) for e in entries]
            GLib.idle_add(lambda: job is self.job and self._show_entries(snapshot, False) and False)

        def done(result):
            if job is not self.job:
                return
            self.job = None
            if isinstance(result, Cancelled):
                return
            if isinstance(result, Exception):
                self.list.empty = f"can't open this folder: {result}"
                self.list.set_items([], force=True)
                self.summary.set_label("")
                return
            LISTINGS[target] = result
            self._show_entries(result, True)

        in_background(lambda: scan(target, job, progress), done)

    def _show_entries(self, entries, finished):
        self.entries = {e[1]: e for e in entries}
        ordered = sorted(entries, key=lambda e: (e[3] is None, -(e[3] or 0), e[0].lower()))
        shown = ordered[:SHOWN]
        self.list.empty = "empty folder" if finished else "measuring..."
        self.list.set_items((e[1], e[0] + ("/" if e[2] else ""), "..." if e[3] is None else human_size(e[3]), False)
                            for e in shown)
        total = sum(e[3] or 0 for e in entries)
        text = f"{len(entries)} item{'s' if len(entries) != 1 else ''} · {human_size(total)}"
        if len(ordered) > SHOWN:
            rest = sum(e[3] or 0 for e in ordered[SHOWN:])
            text += f"  ·  {len(ordered) - SHOWN} smaller ones not shown ({human_size(rest)})"
        if not finished:
            left = sum(1 for e in entries if e[3] is None)
            text = f"measuring, {left} folder{'s' if left != 1 else ''} to go...  ·  " + text
        self.summary.set_label(text if entries else "")
        if self.focus_key is not None and self.list.buttons:
            key = self.focus_key
            item = self.list.buttons.get(key) or (next(iter(self.list.buttons.values())) if key is True else None)
            if item:
                item.grab_focus()
            if finished or item:
                self.focus_key = None

    def _update_crumbs(self):
        while child := self.crumbs.get_first_child():
            self.crumbs.remove(child)
        last = len(self.trail) - 1
        # the first crumb, then the last four; the ones between fold into ...
        visible = [i for i in range(len(self.trail)) if i == 0 or i >= last - 3]
        for n, i in enumerate(visible):
            if n:
                self.crumbs.append(label(" / " if visible[n - 1] == i - 1 else " / ... / ", "dim"))
            crumb = Gtk.Button(label=self.trail[i][0], css_classes=["tab"] + (["on"] if i == last else []),
                               valign=Gtk.Align.CENTER)
            crumb.get_child().set_max_width_chars(28)
            crumb.get_child().set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            crumb.connect("clicked", lambda _, i=i: self.go(i))
            self.crumbs.append(crumb)
        self.up_button.set_sensitive(last > 0)

    # ----- the right-click menu -----

    def _right_click(self, gesture, _n, x, y):
        widget = self.browser.pick(x, y, Gtk.PickFlags.DEFAULT)
        path = next((key for key, item in self.list.buttons.items()
                     if widget is not None and (widget is item or widget.is_ancestor(item))), None)
        if path:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.open_menu(path, None, x, y)

    def open_menu(self, path, item, x=None, y=None):
        entry = self.entries.get(path)
        if not entry:
            return
        _name, path, is_dir, _size = entry
        self.menu_path = path
        while child := self.menu_items.get_first_child():
            self.menu_items.remove(child)
        actions = [("open in file browser" if is_dir else "show in file browser", lambda: reveal(path, is_dir), True)]
        if not inside(path, TRASH):
            writable = os.access(os.path.dirname(path), os.W_OK)
            actions.append(("move to trash", lambda: self.trash(path), writable))
        for text, action, sensitive in actions:
            choice = Gtk.Button(label=text, css_classes=["item"], sensitive=sensitive)
            choice.get_child().set_xalign(0)
            choice.connect("clicked", lambda _, action=action: (self.menu.popdown(), action()))
            if not sensitive:
                choice.set_tooltip_text("needs root")
            self.menu_items.append(choice)
        rect = Gdk.Rectangle()
        if x is None:
            ok, bounds = item.compute_bounds(self.browser) if item else (False, None)
            x, y = (bounds.get_x() + 24, bounds.get_y() + bounds.get_height()) if ok else (24, 0)
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.menu.set_pointing_to(rect)
        self.menu.popup()
        self.menu_items.get_first_child().grab_focus()

    def trash(self, path):
        entry = self.entries.get(path)
        size = entry[3] if entry else None
        ordered = [b for b in self.list.buttons]
        index = ordered.index(path) if path in ordered else 0

        def work():
            try:
                to_home_trash = os.lstat(path).st_dev == os.stat(HOME).st_dev
            except OSError:
                to_home_trash = False
            Gio.File.new_for_path(path).trash(None)
            return to_home_trash

        def done(result):
            name = tilde(path) if self.trail[-1][1][0] != "dir" else os.path.basename(path)
            if isinstance(result, Exception):
                message = result.message if isinstance(result, GLib.Error) else str(result)
                self.panel.flash(f"couldn't move {name} to the trash: {message.lower()}")
                return
            self.panel.flash(f"moved {name} to the trash")
            forget(path)
            self._account_trashed(path, size, result)
            rest = [key for key in ordered if key != path]
            self.focus_key = rest[min(index, len(rest) - 1)] if rest else None
            self.load()

        in_background(work, done)

    # ----- keys -----

    def handle_key(self, keyval, state):
        root = self.get_root()
        focus = root.get_focus() if root else None
        if focus is None or not (focus.is_ancestor(self.browser) or focus.is_ancestor(self.crumbs)):
            return False
        mods = state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_BackSpace and not mods and len(self.trail) > 1:
            self.up()
            return True
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and mods == Gdk.ModifierType.SHIFT_MASK):
            path = next((key for key, item in self.list.buttons.items() if focus is item or focus.is_ancestor(item)),
                        None)
            if path:
                self.open_menu(path, self.list.buttons[path])
                return True
        return False

    def escape(self, focus):
        if self.menu.get_visible():
            self.menu.popdown()
            if item := self.list.buttons.get(self.menu_path):
                item.grab_focus()
            return True
        if len(self.trail) > 1 and focus is not None and (focus.is_ancestor(self.browser)
                                                          or focus.is_ancestor(self.crumbs)):
            self.up()
            return True
        return False
