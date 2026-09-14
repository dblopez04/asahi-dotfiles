#!/usr/bin/env python3
"""Wallpaper picker popup, styled like the fuzzel menus.

Usage: wallpaper-picker.py [gallery]    (running it again while it's open closes it)

Shows a grid of ~/wallpapers, or of github.com/dharmx/walls (tab switches). Picking one
from the gallery downloads it into ~/wallpapers. The pick is set as the sway wallpaper
and wal.sh themes everything from it.

Keys: type to filter, arrows move, enter picks, tab switches local/gallery,
      left/right move between the gallery's categories and its grid, esc closes.
"""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
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

APP_ID = "dev.dotfiles.WallpaperPicker"
WAL = os.path.expanduser("~/.cache/wal")
WAL_SH = os.path.expanduser("~/.local/bin/wal.sh")
SWAY_CONFIG = os.path.expanduser("~/.config/sway/config")
WALLPAPERS = os.path.expanduser("~/wallpapers")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "wallpaper-picker")
BG_LINE = re.compile(r'^(output \* bg )("[^"]*"|\S+)(.*)$', re.M)
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp")

GALLERY_TREE = "https://api.github.com/repos/dharmx/walls/git/trees/main?recursive=1"
GALLERY_RAW = "raw.githubusercontent.com/dharmx/walls/main/"
# github has no thumbnails, so previews come resized from the images.weserv.nl proxy
# (and from the full image if that fails)
THUMBNAIL_PROXY = "https://wsrv.nl/?url={}&w={}&h={}&fit=cover&output=jpg&q=80"

WIDTH, HEIGHT = 1000, 640
THUMB_W, THUMB_H = 168, 105
SCALE = 2  # sharp on the scaled laptop panel
COLUMNS = {"local": 5, "gallery": 4}
V = Gtk.Orientation.VERTICAL

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
window.wallpaper-picker { background: transparent; }

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

.prompt { padding: 8px 12px 6px 16px; }
.footer { padding: 6px 16px 8px 16px; }
.hints, .dim { color: $dim; }
.hsep { background: $faint; min-height: 1px; }
.vsep { background: $faint; min-width: 1px; }

/* local/gallery tabs */
button.tab { background: transparent; color: $dim; border: none; padding: 2px 8px; min-height: 0; min-width: 0; }
button.tab:hover { background: $hover; }
button.tab.on { color: $accent; font-weight: bold; }

/* categories: the fuzzel list. The selection is dimmed while the keyboard is in the grid. */
list.sidebar { background: transparent; color: $fg; padding: 8px; }
list.sidebar row { background: transparent; color: $fg; padding: 3px 8px; min-height: 0; }
list.sidebar row:hover { background: $hover; }
list.sidebar row:selected { background: $faint; color: $fg; }
list.sidebar:focus-within row:selected { background: $sel; color: $sel_fg; }
list.sidebar:focus-within row:selected .dim { color: $sel_fg; }

scrolledwindow, viewport { background: transparent; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: $faint; border: none; min-width: 4px; min-height: 4px; }

.grid { padding: 8px 12px 12px 12px; }
flowbox, flowboxchild { background: transparent; }
flowboxchild { padding: 2px; border: 1px solid transparent; }
flowboxchild:hover { border-color: $faint; }
flowboxchild:selected { border-color: $accent; }
flowbox:focus-within flowboxchild:selected { background: $sel; border-color: $sel; }
"""

###############
### HELPERS ###
###############


def label(text="", *classes, xalign=0.0, hexpand=False, ellipsize=False):
    widget = Gtk.Label(label=text, xalign=xalign, hexpand=hexpand, css_classes=list(classes))
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    return widget


def in_background(work, done=None):
    """Run work() on a thread, then done(result) back on the GTK thread."""
    def target():
        result = work()
        if done:
            GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=target, daemon=True).start()


def on_main_thread(func, *args):
    GLib.idle_add(lambda: func(*args) and False)


def texture(pixbuf):
    fmt = Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pixbuf.get_width(), pixbuf.get_height(), fmt,
                                 pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def megabytes(size):
    return f"{size / 2**20:.1f} mb"


def download(url, dest, progress=None, timeout=30):
    """Save url to dest (only once it's complete). progress(bytes so far, total or 0) runs as it goes."""
    part = f"{dest}.{threading.get_ident()}.part"
    request = urllib.request.Request(url, headers={"User-Agent": "dotfiles-wallpaper-picker"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(part, "wb") as f:
            total, done = int(response.headers.get("Content-Length") or 0), 0
            while chunk := response.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        os.replace(part, dest)
    except BaseException:
        remove(part)
        raise


##################
### WALLPAPERS ###
##################

# Items are dicts: name, size, key (the thumbnail's cache name), and
# path for local files, or category and url for gallery ones.


def local_items():
    try:
        names = sorted(os.listdir(WALLPAPERS), key=str.lower)
    except OSError:
        return []
    items = []
    for name in names:
        path = os.path.join(WALLPAPERS, name)
        if not name.lower().endswith(IMAGE_TYPES) or not os.path.isfile(path):
            continue
        stat = os.stat(path)
        key = hashlib.sha1(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
        items.append({"name": name, "path": path, "size": stat.st_size, "key": f"local-{key}"})
    return items


def gallery_items():
    """{category: [items]} from the walls repo's file list (cached for a day), or None if it can't be had."""
    path = os.path.join(CACHE, "walls-tree.json")
    try:
        stale = time.time() - os.path.getmtime(path) > 86400
    except OSError:
        stale = True
    if stale:
        try:
            os.makedirs(CACHE, exist_ok=True)
            download(GALLERY_TREE, path)
        except OSError:
            pass  # keep using the old list, if there is one
    try:
        with open(path) as f:
            tree = json.load(f)["tree"]
    except (OSError, ValueError, KeyError):
        return None

    categories = {}
    for entry in tree:
        category, _, name = entry.get("path", "").partition("/")
        if entry.get("type") != "blob" or category.startswith(".") or "/" in name \
                or not name.lower().endswith(IMAGE_TYPES):
            continue
        categories.setdefault(category, []).append({
            "name": name, "category": category, "size": entry.get("size", 0), "key": f"walls-{entry['sha']}",
            "url": "https://" + GALLERY_RAW + urllib.parse.quote(entry["path"]),
        })
    return {category: sorted(items, key=lambda item: item["name"].lower())
            for category, items in sorted(categories.items())}


def local_copy(item):
    """Where a gallery item is (or will be) saved: its own name, or category_name if that's taken by another file."""
    for name in (item["name"], f"{item['category']}_{item['name']}"):
        path = os.path.join(WALLPAPERS, name)
        if not os.path.exists(path) or os.path.getsize(path) == item["size"]:
            return path
    return path


def make_thumbnail(src, dest):
    """Scale an image down to cover the thumbnail size."""
    fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(src)
    if fmt is None or not width or not height:
        raise OSError(f"not an image: {src}")
    ratio = max(THUMB_W * SCALE / width, THUMB_H * SCALE / height)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(src, max(1, round(width * ratio)),
                                                     max(1, round(height * ratio)), False)
    part = f"{dest}.{threading.get_ident()}.part"
    try:
        pixbuf.savev(part, "png", [], [])
        os.replace(part, dest)
    except BaseException:
        remove(part)
        raise


def thumbnail(item):
    """The item's preview as a pixbuf, made and cached first if needed. None if it can't be made."""
    path = os.path.join(CACHE, "thumbnails", item["key"])
    try:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if "path" in item:
                make_thumbnail(item["path"], path)
            else:
                source = GALLERY_RAW + item["url"].removeprefix("https://" + GALLERY_RAW)
                try:
                    download(THUMBNAIL_PROXY.format(urllib.parse.quote(source, safe=""), THUMB_W * SCALE,
                                                    THUMB_H * SCALE), path)
                except OSError:
                    full = f"{path}.full"
                    try:
                        download(item["url"], full, timeout=120)
                        make_thumbnail(full, path)
                    finally:
                        remove(full)
        return GdkPixbuf.Pixbuf.new_from_file(path)
    except (OSError, GLib.Error):
        remove(path)  # try again next time
        return None


def current_wallpaper():
    """The image in the sway config's `output * bg` line, or None."""
    try:
        with open(SWAY_CONFIG) as f:
            match = BG_LINE.search(f.read())
    except OSError:
        return None
    return os.path.expanduser(match.group(2).strip('"')) if match else None


def set_wallpaper(path):
    """Point the sway config's `output * bg` line at path. Returns an error message, or None."""
    home = os.path.expanduser("~")
    short = "~" + path[len(home):] if path.startswith(home + "/") else path
    if " " in short:
        short = f'"{short}"'
    try:
        with open(SWAY_CONFIG) as f:
            config = f.read()
        config, found = BG_LINE.subn(lambda m: m.group(1) + short + m.group(3), config, count=1)
        if not found:
            return "no `output * bg` line in the sway config"
        with open(SWAY_CONFIG, "w") as f:
            f.write(config)
    except OSError as e:
        return f"couldn't update the sway config: {e.strerror.lower()}"
    return None


##############
### PICKER ###
##############


class Picker(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="wallpaper", css_classes=["wallpaper-picker"])
        self.app = app
        self.mode = None
        self.items = []  # what the grid shows
        self.visible = []  # indexes of the items that match the filter
        self.filter = ""
        self.gallery = None  # {category: [items]} once loaded
        self.gallery_loading = False
        self.busy = False  # downloading a pick
        self.generation = 0  # bumped when the grid is rebuilt, so late thumbnails are dropped
        self.jobs = queue.Queue()
        for _ in range(6):
            threading.Thread(target=self._thumbnail_worker, daemon=True).start()

        # a transparent overlay over the whole screen, so clicking outside the picker closes it
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "wallpaper-picker")
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self, edge, True)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

        frame = Gtk.Box(orientation=V, css_classes=["frame"])
        header = Gtk.Box(spacing=4, css_classes=["prompt"])
        self.prompt = label("", hexpand=True, ellipsize=True)
        header.append(self.prompt)
        self.tabs = {}
        for mode in COLUMNS:
            tab = Gtk.Button(label=mode, css_classes=["tab"], focusable=False)
            tab.connect("clicked", lambda _, mode=mode: self.show(mode))
            header.append(tab)
            self.tabs[mode] = tab
        frame.append(header)
        frame.append(Gtk.Box(css_classes=["hsep"]))

        body = Gtk.Box(vexpand=True)
        self.sidebar = Gtk.ListBox(css_classes=["sidebar"], selection_mode=Gtk.SelectionMode.BROWSE)
        self.sidebar.connect("row-selected", lambda _, row: row and self.show_category(row.get_index()))
        self.sidebar_box = Gtk.Box(visible=False)
        self.sidebar_box.append(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=190,
                                                   child=self.sidebar))
        self.sidebar_box.append(Gtk.Box(css_classes=["vsep"]))
        body.append(self.sidebar_box)

        self.grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, homogeneous=True, row_spacing=4,
                                column_spacing=4, activate_on_single_click=True, valign=Gtk.Align.START)
        self.grid.set_filter_func(lambda child: self.matches(self.items[child.get_index()]))
        self.grid.connect("child-activated", lambda _, child: self.pick(child.get_index()))
        self.grid.connect("selected-children-changed", lambda _: self.describe_selection())
        grid_box = Gtk.Box(orientation=V, css_classes=["grid"])
        grid_box.append(self.grid)
        body.append(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True, child=grid_box))
        frame.append(body)

        frame.append(Gtk.Box(css_classes=["hsep"]))
        footer = Gtk.Box(spacing=16, css_classes=["footer"])
        self.status = label("", hexpand=True, ellipsize=True)
        self.hints = label("", "hints")
        footer.append(self.status)
        footer.append(self.hints)
        frame.append(footer)
        # Keep the popup at the local view's size even when gallery content has
        # a larger natural size. The inner scrollers still handle navigation.
        self.set_child(Gtk.ScrolledWindow(
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            width_request=WIDTH, height_request=HEIGHT,
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.EXTERNAL, child=frame))

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("pressed", self._clicked)
        self.add_controller(click)

    ### views ###

    def show(self, mode):
        if self.busy or mode == self.mode:
            return
        self.mode = mode
        for name, tab in self.tabs.items():
            (tab.add_css_class if name == mode else tab.remove_css_class)("on")
        self.sidebar_box.set_visible(mode == "gallery")
        self.grid.set_min_children_per_line(COLUMNS[mode])
        self.grid.set_max_children_per_line(COLUMNS[mode])

        if mode == "local":
            self.hints.set_label("tab gallery  enter pick  esc close")
            self.set_items(local_items())
            current = current_wallpaper()
            self.focus_item(next((i for i, item in enumerate(self.items) if item["path"] == current), 0))
            if not self.items:
                self.status.set_label(f"no images in {WALLPAPERS}, press tab for the gallery")
            return

        self.hints.set_label("←→ categories  tab local  enter download  esc close")
        if self.gallery:
            row = self.sidebar.get_selected_row() or self.sidebar.get_row_at_index(0)
            self.sidebar.select_row(row)
            self.show_category(row.get_index())
            row.grab_focus()
            return
        self.set_items([])
        self.status.set_label("loading the gallery...")
        if not self.gallery_loading:
            self.gallery_loading = True
            in_background(gallery_items, self._gallery_loaded)

    def _gallery_loaded(self, gallery):
        self.gallery_loading = False
        if not gallery:
            if self.mode == "gallery":
                self.status.set_label("couldn't get the gallery from github")
            return
        self.gallery = gallery
        for category, items in gallery.items():
            row = Gtk.Box(spacing=12)
            row.append(label(category, hexpand=True, ellipsize=True))
            row.append(label(str(len(items)), "dim"))
            self.sidebar.append(Gtk.ListBoxRow(child=row))
        if self.mode == "gallery":
            self.mode = None
            self.show("gallery")

    def show_category(self, index):
        if self.mode != "gallery" or not self.gallery:
            return
        items = list(self.gallery.values())[index]
        if items is not self.items:
            self.set_items(items)
            self.select_visible(0)

    def set_items(self, items):
        self.items = items
        self.filter = ""
        self.generation += 1
        while child := self.grid.get_first_child():
            self.grid.remove(child)
        for item in items:
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
            picture.set_size_request(THUMB_W, THUMB_H)
            picture.set_tooltip_text(item["name"])
            self.grid.append(picture)
            self.jobs.put((self.generation, item, picture))
        self.refilter()

    def _thumbnail_worker(self):
        while True:
            generation, item, picture = self.jobs.get()
            if generation == self.generation and (pixbuf := thumbnail(item)) is not None:
                on_main_thread(self._set_thumbnail, generation, picture, pixbuf)

    def _set_thumbnail(self, generation, picture, pixbuf):
        if generation == self.generation:
            picture.set_paintable(texture(pixbuf))

    ### filter and selection ###

    def matches(self, item):
        name = item["name"].lower()
        return all(term in name for term in self.filter.lower().split())

    def set_filter(self, text):
        if text != self.filter:
            self.filter = text
            self.refilter()

    def refilter(self):
        self.visible = [i for i, item in enumerate(self.items) if self.matches(item)]
        self.grid.invalidate_filter()
        self.prompt.set_label(f"wallpaper > {self.filter}▏")
        selected = self.selected_index()
        if selected is None or selected not in self.visible:
            self.select_visible(0)
        if self.items and not self.visible:
            self.status.set_label("no matches")

    def selected_index(self):
        children = self.grid.get_selected_children()
        return children[0].get_index() if children else None

    def select_visible(self, position):
        """Select the position-th matching item, keeping the keyboard in the grid if it was there."""
        if not self.visible:
            self.grid.unselect_all()
            return
        child = self.grid.get_child_at_index(self.visible[position])
        focus = self.get_focus()
        self.grid.select_child(child)
        if focus is None or focus.is_ancestor(self.grid):
            child.grab_focus()

    def focus_item(self, index):
        if child := self.grid.get_child_at_index(index):
            self.grid.select_child(child)
            child.grab_focus()

    def focus_grid(self):
        selected = self.selected_index()
        if selected is not None:
            self.focus_item(selected)
        elif self.visible:
            self.focus_item(self.visible[0])

    def select_category(self, index):
        if row := self.sidebar.get_row_at_index(max(0, min(index, len(self.gallery) - 1))):
            self.sidebar.select_row(row)
            row.grab_focus()

    def describe_selection(self):
        index = self.selected_index()
        if self.busy or index is None:
            return
        item = self.items[index]
        if "path" in item:
            note = " · current" if item["path"] == current_wallpaper() else ""
            self.status.set_label(f"{item['name']} · {megabytes(item['size'])}{note}")
        else:
            note = " · downloaded" if os.path.exists(local_copy(item)) else ""
            self.status.set_label(f"{item['category']}/{item['name']} · {megabytes(item['size'])}{note}")

    ### picking ###

    def pick(self, index):
        if self.busy or index is None or index not in self.visible:
            return
        item = self.items[index]
        if "path" in item:
            self.apply(item["path"])
            return
        dest = local_copy(item)
        if os.path.exists(dest):
            self.apply(dest)
            return

        self.busy = True
        name = os.path.basename(dest)
        self.status.set_label(f"downloading {name}...")
        last_update = [0.0]

        def progress(done, total):
            if time.monotonic() - last_update[0] > 0.1:
                last_update[0] = time.monotonic()
                amount = f"{done * 100 // total}%" if total else megabytes(done)
                on_main_thread(self.status.set_label, f"downloading {name}... {amount}")

        def work():
            part = os.path.join(CACHE, "downloads", item["key"])
            try:
                os.makedirs(os.path.dirname(part), exist_ok=True)
                download(item["url"], part, progress, timeout=60)
                shutil.move(part, dest)
            except OSError as e:
                remove(part)
                return f"download failed: {str(getattr(e, 'reason', None) or e).lower()}"
            return None

        def done(error):
            self.busy = False
            if error:
                self.status.set_label(error)
            else:
                self.apply(dest)

        in_background(work, done)

    def apply(self, path):
        if error := set_wallpaper(path):
            self.status.set_label(error)
            return
        # wal.sh reloads sway (which puts up the new wallpaper) and re-themes everything, after the picker is gone
        subprocess.Popen(["sh", "-c", '"$0" "$1" >/dev/null 2>&1 || notify-send -a wallpaper "theming failed" "wal.sh $1"',
                          WAL_SH, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        self.app.quit()

    ### input ###

    def _key_pressed(self, _, keyval, _keycode, state):
        name = Gdk.keyval_name(keyval) or ""
        mods = state & Gtk.accelerator_get_default_mod_mask()
        focus = self.get_focus()
        in_sidebar = focus is not None and focus.is_ancestor(self.sidebar)
        # GTK only turns on focus rings for keys it handles itself, and these get caught first
        self.set_focus_visible(True)

        if name == "Escape":
            self.app.quit()
        elif name in ("Tab", "ISO_Left_Tab"):
            self.show("gallery" if self.mode == "local" else "local")
        elif name == "BackSpace":
            self.set_filter("" if mods & Gdk.ModifierType.CONTROL_MASK else self.filter[:-1])
        elif name == "u" and mods == Gdk.ModifierType.CONTROL_MASK:
            self.set_filter("")
        elif name in ("Return", "KP_Enter"):
            if in_sidebar:
                self.focus_grid()
            else:
                self.pick(self.selected_index())
        elif in_sidebar and name in ("Up", "Down", "Home", "End"):
            index = self.sidebar.get_selected_row().get_index()
            self.select_category({"Up": index - 1, "Down": index + 1, "Home": 0, "End": len(self.gallery)}[name])
        elif in_sidebar and name == "Right":
            self.focus_grid()
        elif self.mode == "gallery" and self.gallery and name == "Left" and self.at_left_edge(focus):
            self.sidebar.get_selected_row().grab_focus()
        elif not mods & ~Gdk.ModifierType.SHIFT_MASK and (char := Gdk.keyval_to_unicode(keyval)) >= 32 and char != 127:
            self.set_filter(self.filter + chr(char))
        else:
            return False
        return True

    def at_left_edge(self, focus):
        child = focus if isinstance(focus, Gtk.FlowBoxChild) else focus and focus.get_ancestor(Gtk.FlowBoxChild)
        if child is None or child.get_index() not in self.visible:
            return True
        return self.visible.index(child.get_index()) % COLUMNS[self.mode] == 0

    def _clicked(self, gesture, _n, x, y):
        if self.pick(x, y, Gtk.PickFlags.DEFAULT) in (None, self):
            self.app.quit()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        css = Gtk.CssProvider()
        css.load_from_string(Template(CSS).substitute(load_theme()))
        # above ~/.config/gtk-4.0/gtk.css, which is also generated by pywal
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args[:1] in (["-h"], ["--help"]):
            command_line.print_literal(__doc__)
        elif self.window is None:
            self.window = Picker(self)
            self.window.present()
            self.window.show("gallery" if args[:1] == ["gallery"] else "local")
        else:
            self.quit()
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
