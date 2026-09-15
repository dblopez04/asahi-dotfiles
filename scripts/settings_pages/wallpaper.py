import importlib.util
import os

from gi.repository import Gtk

from .common import SCRIPTS, Page


def load_picker():
    """wallpaper-picker.py as a module (its name has a dash, so it can't be imported normally)."""
    spec = importlib.util.spec_from_file_location("wallpaper_picker", os.path.join(SCRIPTS, "wallpaper-picker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WallpaperPage(Page):
    """The wallpaper picker's grid, local files and the online gallery."""
    name = "wallpaper"

    def __init__(self, panel):
        super().__init__(panel)
        self.remove_css_class("page")
        self.picker = load_picker()
        self.browser = self.picker.WallpaperBrowser(on_pending=panel.update_pending, show_prompt=True,
                                                    columns={"local": 4, "gallery": 3})
        self.append(self.browser)
        self.started = False
        # the browser scrolls its own grid; don't let the page scroller wrap it too
        self.set_vexpand(True)

    def shown(self):
        scroller = getattr(self, "scroller", None)
        if scroller:
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        if not self.started:
            self.started = True
            self.browser.show("local")
        else:
            self.browser.refresh_local()

    def refresh(self):
        self.browser.refresh_local()

    def handle_key(self, keyval, state):
        root = self.get_root()
        focus = root.get_focus() if root else None
        if focus is not None and not focus.is_ancestor(self.browser):
            return False
        return self.browser.handle_key(keyval, state)

    def escape(self, focus):
        if self.browser.filter:
            self.browser.set_filter("")
            return True
        return False
