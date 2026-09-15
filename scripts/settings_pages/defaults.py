import os
import shutil

from gi.repository import Gio

import dotconfig

from .common import HOME, Choice, Page, label, row

CATEGORIES = [
    ("web browser", ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"]),
    ("mail", ["x-scheme-handler/mailto"]),
    ("text editor", ["text/plain", "text/markdown"]),
    ("images", ["image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/svg+xml"]),
    ("videos", ["video/mp4", "video/x-matroska", "video/webm", "video/quicktime"]),
    ("music", ["audio/mpeg", "audio/flac", "audio/ogg", "audio/x-wav"]),
    ("pdfs", ["application/pdf"]),
    ("archives", ["application/zip", "application/x-tar", "application/x-7z-compressed"]),
]
TERMINALS = ["kitty", "foot", "alacritty", "wezterm", "ghostty", "gnome-terminal", "konsole", "xterm"]
FILE_MANAGERS = ["nautilus", "thunar", "dolphin", "nemo", "pcmanfm", "yazi"]
MIMEAPPS = os.path.join(HOME, ".config/mimeapps.list")


def apps_for(mimes):
    seen, apps = set(), []
    for mime in mimes:
        for app in Gio.AppInfo.get_all_for_type(mime):
            if app.get_id() not in seen and app.should_show():
                seen.add(app.get_id())
                apps.append(app)
    return sorted(apps, key=lambda a: a.get_display_name().lower())


class DefaultAppsPage(Page):
    name = "default apps"

    def __init__(self, panel):
        super().__init__(panel)
        self.choices = {}
        self.section("open with")
        for title, mimes in CATEGORIES:
            choice = Choice([], lambda app_id, mimes=mimes, title=title: self.set_default(title, mimes, app_id))
            self.choices[title] = (choice, mimes)
            self.add(row(title, choice))
        self.section("desktop")
        self.terminal = Choice([(t, t) for t in TERMINALS if shutil.which(t)], lambda v: self.set_program("terminal", v))
        self.files = Choice([(f, f) for f in FILE_MANAGERS if shutil.which(f)], lambda v: self.set_program("fileManager", v))
        self.add(row("terminal", self.terminal, sub=label("super+q", "dim")),
                 row("file manager", self.files, sub=label("super+e", "dim")))
        self.status = label("", "dim", "row")
        self.add(self.status)

    def refresh(self):
        for title, (choice, mimes) in self.choices.items():
            apps = apps_for(mimes)
            choice.set_options([(a.get_id(), a.get_display_name()) for a in apps] or [(None, "nothing installed")])
            default = Gio.AppInfo.get_default_for_type(mimes[0], False)
            choice.set_value(default.get_id() if default else None)
        self.terminal.set_value(self.sway("set $terminal", "kitty"))
        self.files.set_value(self.sway("set $fileManager", "nautilus"))

    def set_default(self, title, mimes, app_id):
        if not app_id:
            return
        app = Gio.DesktopAppInfo.new(app_id)
        if app is None:
            return
        dotconfig.backup(MIMEAPPS)  # not part of the dotfiles, but keep the old defaults anyway
        failed = []
        for mime in mimes:
            try:
                app.set_as_default_for_type(mime)
            except Exception:
                failed.append(mime)
        self.status.set_label(f"{title}: {app.get_display_name()}" + (f" (not for {', '.join(failed)})" if failed else ""))

    def set_program(self, variable, program):
        # sway expands $variables where they're used, so the keybindings are restaged too
        key = {"terminal": "$mod+q", "fileManager": "$mod+e"}[variable]
        self.stage(f"set ${variable} {program}", f"bindsym {key} exec {program}")
