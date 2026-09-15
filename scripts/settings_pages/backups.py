import os
import time

from gi.repository import Gtk

import dotconfig

from .common import HOME, ItemList, Page, dialog, human_size, label, load_theme


class BackupsPage(Page):
    """Older versions of config files the panel saved over, the newest 10 of each."""
    name = "backups"

    def __init__(self, panel):
        super().__init__(panel)
        self.add(label(f"saved in {dotconfig.BACKUPS.replace(HOME, '~')}", "dim", "row"))
        self.files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.files)
        self.status = label("", "dim", "row")
        self.add(self.status)

    def refresh(self):
        while child := self.files.get_first_child():
            self.files.remove(child)
        paths = dotconfig.backed_up_files()
        if not paths:
            self.files.append(label("nothing backed up yet", "dim", "row"))
        for path in paths:
            name = os.path.relpath(path, HOME)
            header = Gtk.Box(spacing=12, css_classes=["section-row"])
            header.append(label(name + ":", "section", hexpand=True))
            self.files.append(header)
            backups = dotconfig.list_backups(path)
            items = ItemList(lambda backup, path=path: self.show_diff(path, backup))
            items.set_items((b["backup"], time.strftime("%b %-d, %-I:%M %p", time.localtime(b["time"])).lower(),
                             human_size(b["size"]), False) for b in backups)
            self.files.append(items)

    def show_diff(self, path, backup):
        current = dotconfig.read(path)
        old = dotconfig.read(backup)
        view = Gtk.TextView(editable=False, monospace=True, css_classes=["diff"], left_margin=12, right_margin=12,
                            top_margin=8, bottom_margin=8)
        buffer = view.get_buffer()
        theme = load_theme()
        tags = {"+": buffer.create_tag(foreground=theme["accent"]), "-": buffer.create_tag(foreground=theme["c1"])}
        text = dotconfig.diff(current, old, os.path.basename(path)) or "identical to the current file\n"
        for line in text.splitlines(True):
            tag = tags.get(line[:1]) if not line.startswith(("+++", "---")) else None
            if tag:
                buffer.insert_with_tags(buffer.get_end_iter(), line, tag)
            else:
                buffer.insert(buffer.get_end_iter(), line)
        scroller = Gtk.ScrolledWindow(child=view, min_content_height=380)
        when = time.strftime("%b %-d %-I:%M %p", time.localtime(os.path.getmtime(backup))).lower()
        dialog(self.panel, f"{os.path.basename(path)} · changes to go back to {when}", scroller,
               [("close", None), ("restore this version", "restore")],
               lambda r: r == "restore" and self.restore(path, backup), width=760, height=520)

    def restore(self, path, backup):
        dotconfig.restore(path, backup)
        if path == dotconfig.SWAY_CONFIG:
            dotconfig.reload_sway()
        self.status.set_label(f"restored {os.path.relpath(path, HOME)} (the version it replaced is backed up too)")
        self.refresh()
