#!/usr/bin/env python3
"""Quick Look: a fast preview of a file, like pressing Space in Finder.

Usage: quicklook.py [--back QUERY] FILE    (Ctrl+Y in Spotlight; previewing the same file again closes it)

--back: closing the preview reopens Spotlight with QUERY (or, when browsing, the folder of the file
being previewed) and that file selected, so you pick up where you were.

Previews images, text and code, PDFs (with poppler-utils), video and audio, and folders; anything
else shows its details. Keys: esc or space close, enter opens it in its app, left/right show the
previous/next file in the same folder.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from string import Template

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPTS)
from settings_pages.common import human_size, load_theme  # noqa: E402

APP_ID = "dev.dotfiles.QuickLook"
HOME = os.path.expanduser("~")
TEXT_LIMIT = 256 * 1024
TEXT_TYPES = ("application/json", "application/xml", "application/x-shellscript", "application/javascript",
              "application/toml", "application/x-yaml", "application/sql", "application/x-desktop")

CSS = """
window.quicklook { background: $bg; }
window.quicklook > .frame { background: $bg; color: $fg; border: 1px solid $border; }
.frame, .frame * { font-family: "BlexMono Nerd Font", monospace; border-radius: 0; box-shadow: none; outline-style: none; }
.header { padding: 8px 10px 8px 16px; border-bottom: 1px solid $faint; }
.name { font-size: 11pt; font-weight: bold; }
.meta { color: $dim; font-size: 9pt; }
button.flat { background: transparent; color: $fg; border: none; padding: 2px 8px; min-height: 0; min-width: 0; }
button.flat:hover { background: $hover; }
textview.preview, textview.preview text { background: $bg; color: $fg; font-size: 10pt; }
.body { padding: 12px; }
.big-icon { color: $dim; }
.note { color: $dim; padding: 16px; }
.listing { padding: 8px 16px; }
.listing label { font-size: 10pt; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: $faint; min-width: 4px; min-height: 4px; }
"""


def modified(path):
    stamp = os.stat(path).st_mtime
    age = time.time() - stamp
    if age < 86400:
        return time.strftime("today %-I:%M %p", time.localtime(stamp)).lower()
    return time.strftime("%b %-d %Y", time.localtime(stamp)).lower()


def folder_size(path):
    try:
        return len([e for e in os.scandir(path) if not e.name.startswith(".")])
    except OSError:
        return 0


class Preview(Gtk.ApplicationWindow):
    def __init__(self, app, path, back=None):
        super().__init__(application=app, title="Quick Look", css_classes=["quicklook"], decorated=False,
                         default_width=920, default_height=660)
        self.app = app
        self.back = back  # the Spotlight query to go back to, or None
        self.path = None
        self.media = None
        self.tmp = None

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["frame"])
        header = Gtk.Box(spacing=8, css_classes=["header"])
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.name = Gtk.Label(xalign=0, css_classes=["name"], ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.meta = Gtk.Label(xalign=0, css_classes=["meta"], ellipsize=Pango.EllipsizeMode.END)
        titles.append(self.name)
        titles.append(self.meta)
        header.append(titles)
        for text, tip, action in (("[ open ]", "Open with its app (Enter)", self.open_file),
                                  ("[ folder ]", "Show in its folder", self.reveal),
                                  ("[ send ]", "Send to another device with Taildrop (t)", self.send),
                                  ("×", "Close (Esc)", self.go_back)):
            button = Gtk.Button(label=text, css_classes=["flat"], tooltip_text=tip, valign=Gtk.Align.CENTER,
                                focusable=False)
            button.connect("clicked", lambda _b, a=action: a())
            header.append(button)
        frame.append(Gtk.WindowHandle(child=header))
        self.body = Gtk.Box(vexpand=True, hexpand=True)
        frame.append(self.body)
        self.set_child(frame)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)
        self.connect("close-request", lambda *_: self.cleanup() or False)
        self.show_path(path)

    # ----- showing -----

    def show_path(self, path):
        self.cleanup()
        self.path = os.path.abspath(path)
        while child := self.body.get_first_child():
            self.body.remove(child)
        self.name.set_label(os.path.basename(self.path) or self.path)
        if not os.path.exists(self.path):
            self.meta.set_label("doesn't exist")
            self.body.append(self.note("this file doesn't exist"))
            return

        is_dir = os.path.isdir(self.path)
        content_type = "inode/directory" if is_dir else (Gio.content_type_guess(self.path, None)[0] or "")
        description = Gio.content_type_get_description(content_type) if content_type else "file"
        size = f"{folder_size(self.path)} items" if is_dir else human_size(os.path.getsize(self.path))
        self.meta.set_label(f"{description.lower()}  ·  {size}  ·  modified {modified(self.path)}  ·  "
                            f"{os.path.dirname(self.path).replace(HOME, '~', 1)}")

        try:
            if is_dir:
                widget = self.folder()
            elif content_type.startswith("image/"):
                widget = self.image()
            elif content_type == "application/pdf":
                widget = self.pdf()
            elif content_type.startswith(("video/", "audio/")):
                widget = self.video()
            elif content_type.startswith("text/") or content_type in TEXT_TYPES or self.looks_like_text():
                widget = self.text()
            else:
                widget = self.details(content_type)
        except (GLib.Error, OSError) as e:
            widget = self.note(f"couldn't preview this: {getattr(e, 'message', None) or e}")
        widget.set_hexpand(True)
        widget.set_vexpand(True)
        self.body.append(widget)

    def note(self, text):
        return Gtk.Label(label=text, css_classes=["note"], wrap=True, valign=Gtk.Align.CENTER)

    def image(self):
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, css_classes=["body"])
        picture.set_file(Gio.File.new_for_path(self.path))
        return picture

    def looks_like_text(self):
        try:
            with open(self.path, "rb") as f:
                sample = f.read(4096)
        except OSError:
            return False
        if b"\0" in sample:
            return False
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def text(self):
        with open(self.path, "rb") as f:
            data = f.read(TEXT_LIMIT + 1)
        text = data[:TEXT_LIMIT].decode("utf-8", errors="replace")
        if len(data) > TEXT_LIMIT:
            text += "\n\n… (the rest isn't shown; enter opens the whole file)"
        view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            css_classes=["preview"], left_margin=16, right_margin=16, top_margin=12, bottom_margin=12)
        view.get_buffer().set_text(text)
        return Gtk.ScrolledWindow(child=view)

    def pdf(self):
        if not shutil.which("pdftoppm"):
            return self.details("application/pdf", extra="install poppler-utils to see pdf pages here")
        self.tmp = tempfile.mkdtemp(prefix="quicklook-")
        subprocess.run(["pdftoppm", "-png", "-r", "90", "-f", "1", "-l", "4", self.path, os.path.join(self.tmp, "page")],
                       capture_output=True, timeout=30)
        pages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["body"])
        for name in sorted(os.listdir(self.tmp)):
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=False)
            picture.set_file(Gio.File.new_for_path(os.path.join(self.tmp, name)))
            pages.append(picture)
        if not pages.get_first_child():
            return self.details("application/pdf", extra="couldn't render this pdf")
        pages.append(self.note("the first pages · enter opens the whole document"))
        return Gtk.ScrolledWindow(child=pages)

    def video(self):
        self.media = Gtk.MediaFile.new_for_filename(self.path)
        video = Gtk.Video(media_stream=self.media, autoplay=True, css_classes=["body"])
        return video

    def folder(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["listing"])
        try:
            entries = sorted((e for e in os.scandir(self.path) if not e.name.startswith(".")),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as e:
            return self.note(f"can't read this folder: {e.strerror}")
        for entry in entries[:300]:
            line = Gtk.Box(spacing=12)
            is_dir = entry.is_dir()
            line.append(Gtk.Label(label=("  " if is_dir else "  ") + entry.name, xalign=0, hexpand=True,
                                  ellipsize=Pango.EllipsizeMode.END))
            try:
                detail = f"{folder_size(entry.path)} items" if is_dir else human_size(entry.stat().st_size)
            except OSError:
                detail = ""
            line.append(Gtk.Label(label=detail, css_classes=["meta"]))
            box.append(line)
        if len(entries) > 300:
            box.append(Gtk.Label(label=f"and {len(entries) - 300} more", xalign=0, css_classes=["meta"]))
        if not entries:
            box.append(self.note("empty folder"))
        return Gtk.ScrolledWindow(child=box)

    def details(self, content_type, extra=""):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        icon = Gtk.Image(gicon=Gio.content_type_get_icon(content_type or "application/octet-stream"), pixel_size=128,
                         css_classes=["big-icon"])
        box.append(icon)
        box.append(Gtk.Label(label=content_type or "unknown type", css_classes=["meta"]))
        if extra:
            box.append(Gtk.Label(label=extra, css_classes=["meta"]))
        return box

    # ----- acting -----

    def siblings(self):
        folder = os.path.dirname(self.path)
        try:
            names = sorted((n for n in os.listdir(folder) if not n.startswith(".")), key=str.lower)
        except OSError:
            return []
        return [os.path.join(folder, n) for n in names]

    def step(self, direction):
        items = self.siblings()
        if self.path in items and len(items) > 1:
            self.show_path(items[(items.index(self.path) + direction) % len(items)])

    def open_file(self):
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(self.path).get_uri(),
                                               Gdk.Display.get_default().get_app_launch_context())
        except GLib.Error:
            subprocess.Popen(["xdg-open", self.path], start_new_session=True)
        self.close()

    def send(self):
        if os.path.isfile(self.path):
            subprocess.Popen([os.path.join(SCRIPTS, "taildrop.py"), "send", self.path], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reveal(self):
        subprocess.Popen(["nautilus", "--select", self.path], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    def key_pressed(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_space, Gdk.KEY_q):
            self.go_back()
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.open_file()
        elif keyval == Gdk.KEY_t:
            self.send()
        # left/right always step through the folder; up/down scroll text previews instead
        elif keyval == Gdk.KEY_Right or (keyval == Gdk.KEY_Down and not isinstance(self.get_focus(), Gtk.TextView)):
            self.step(1)
        elif keyval == Gdk.KEY_Left or (keyval == Gdk.KEY_Up and not isinstance(self.get_focus(), Gtk.TextView)):
            self.step(-1)
        else:
            return False
        return True

    def go_back(self):
        """Close, and return to Spotlight where the preview was opened from."""
        if self.back is not None and self.path:
            query = self.back
            if query.startswith(("~", "/")):
                # browsing: the folder of the file shown now (left/right may have moved on)
                folder = os.path.dirname(self.path.rstrip("/")) or "/"
                query = ("~" + folder[len(HOME):] if folder == HOME or folder.startswith(HOME + "/") else folder)
                query = query.rstrip("/") + "/"
            subprocess.Popen([os.path.join(SCRIPTS, "spotlight.py"), "--query", query, "--select", self.path],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    def cleanup(self):
        if self.media:
            self.media.pause()
            self.media = None
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.tmp = None


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
        back = None
        if len(args) >= 2 and args[0] == "--back":
            back, args = args[1], args[2:]
        if not args or args[0] in ("-h", "--help"):
            command_line.print_literal(__doc__)
            return 0 if args else 1
        path = os.path.join(command_line.get_cwd() or os.getcwd(), os.path.expanduser(args[0]))
        if self.window is None:
            self.window = Preview(self, path, back)
            self.window.connect("close-request", lambda *_: GLib.idle_add(self.quit) and False)
            self.window.present()
        elif os.path.abspath(path) == self.window.path:
            self.window.close()
        else:
            self.window.back = back
            self.window.show_path(path)
            self.window.present()
        return 0


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
