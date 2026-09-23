import json
import os
import subprocess
import time

from gi.repository import Gtk

import dotconfig

from .common import (HOME, ItemList, Page, SegmentBar, button, human_size, in_background, label, load_theme,
                      spawn)

CACHE = os.path.join(HOME, ".cache/settings-panel/storage.json")
MAX_AGE = 3600
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
    ("trash", [os.path.join(HOME, ".local/share/Trash")], "dim"),
]


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
    result = {"time": time.time(), "categories": {}, "home": {}}
    for name, paths, _color in CATEGORIES:
        result["categories"][name] = du(paths)
    try:
        for entry in os.scandir(HOME):
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                result["home"][entry.name] = du([entry.path])
    except OSError:
        pass
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(result, f)
    return result


class StoragePage(Page):
    name = "storage"

    def __init__(self, panel):
        super().__init__(panel)
        self.measuring = False
        self.disk = label("", "accent", "row")
        self.bar = SegmentBar(18)
        self.bar.set_margin_start(8)
        self.bar.set_margin_end(8)
        self.legend = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                  min_children_per_line=2, column_spacing=12)
        self.status = label("", "dim", "row")
        self.add(self.disk, self.bar, self.legend, self.status)
        self.section("home folder", button("measure again", lambda: self.start(force=True)))
        self.home = ItemList(lambda name: spawn("nautilus", os.path.join(HOME, name)), empty="measuring...")
        self.add(self.home)

    def shown(self):
        self.start()

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

    def show(self, data):
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
        age = int((time.time() - data.get("time", 0)) / 60)
        if not self.measuring:
            self.status.set_label(f"measured {age} min ago" if age else "measured just now")
        home = sorted(data.get("home", {}).items(), key=lambda kv: -kv[1])
        self.home.set_items((name, name, human_size(amount), False) for name, amount in home if amount > 0)
