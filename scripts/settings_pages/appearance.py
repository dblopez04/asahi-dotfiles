import os
import re

import dotconfig

from .common import HOME, Choice, Page, Slider, Toggle, button, in_background, label, row, run_ok

BACKEND_FILE = os.path.join(HOME, ".config/wal/backend")
BACKENDS = [("colorz", "colorz · lively"), ("wal", "wal · the default, muted"), ("haishoku", "haishoku · earthy"),
            ("modern_colorthief", "colorthief · dark, rich")]


def cursor_themes():
    themes = set()
    for base in (os.path.join(HOME, ".local/share/icons"), os.path.join(HOME, ".icons"), "/usr/share/icons"):
        try:
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name, "cursors")):
                    themes.add(name)
        except OSError:
            pass
    return sorted(themes, key=str.lower)


class AppearancePage(Page):
    name = "appearance"

    def __init__(self, panel):
        super().__init__(panel)
        self.section("windows")
        self.inner = Slider("gaps between", lambda v: self.stage(f"gaps inner {v:.0f}"),
                            lower=0, upper=40, step=1, fmt="{:.0f} px", throttle=None)
        self.outer = Slider("screen edges", lambda v: self.stage(f"gaps outer {v - self.inner.scale.get_value():.0f}"),
                            lower=0, upper=40, step=1, fmt="{:.0f} px", throttle=None)
        self.border = Choice([(n, f"{n} px") for n in range(0, 7)], self.set_border)
        self.edges = Choice([("none", "always"), ("smart", "not with one window"), ("both", "never at screen edges")],
                            lambda v: self.stage(f"hide_edge_borders {v}"))
        self.smart_gaps = Toggle(lambda on: self.stage(f"smart_gaps {'on' if on else 'off'}"))
        self.follow = Toggle(lambda on: self.stage(f"focus_follows_mouse {'yes' if on else 'no'}"))
        self.add(self.inner, self.outer, row("border width", self.border), row("borders", self.edges),
                 row("no gaps with one window", self.smart_gaps),
                 row("focus follows mouse", self.follow, sub=label("hovering a window focuses it", "dim")))

        self.section("cursor")
        self.cursor_theme = Choice([(t, t) for t in cursor_themes()], lambda v: self.set_cursor(theme=v))
        self.cursor_size = Choice([(n, str(n)) for n in (16, 20, 24, 28, 32, 40, 48)], lambda v: self.set_cursor(size=v))
        self.add(row("theme", self.cursor_theme), row("size", self.cursor_size))

        self.section("colors")
        self.backend = Choice(BACKENDS, self.set_backend)
        self.wal_status = label("", "dim", ellipsize=True)
        self.add(row("palette style", self.backend),
                 row("theme", button("regenerate from wallpaper", self.rerun_wal), sub=self.wal_status))

    def refresh(self):
        inner = int(self.sway("gaps inner", "10"))
        outer = int(self.sway("gaps outer", "0"))
        self.inner.set_value(inner)
        self.outer.set_value(inner + outer)  # sway adds inner at the edges
        border = re.search(r"(\d+)", self.sway("default_border", "pixel 1") or "")
        self.border.set_value(int(border.group(1)) if border else 1)
        self.edges.set_value(self.sway("hide_edge_borders", "none"))
        self.smart_gaps.set_active(self.sway("smart_gaps", "off") in ("on", "yes", "true"))
        self.follow.set_active(self.sway("focus_follows_mouse", "yes") != "no")
        seat = (self.sway("seat seat0 xcursor_theme") or "Adwaita 24").split()
        self.cursor_theme.set_value(seat[0])
        self.cursor_size.set_value(int(seat[1]) if len(seat) > 1 else 24)
        pending = dotconfig.file_pending_content(BACKEND_FILE)
        self.backend.set_value((pending if pending is not None else dotconfig.read(BACKEND_FILE)).strip() or "colorz")

    def set_border(self, width):
        self.stage(f"default_border pixel {width}", f"default_floating_border pixel {width}")

    def set_cursor(self, theme=None, size=None):
        theme = theme or self.cursor_theme.value
        size = size or self.cursor_size.value
        self.stage(f"seat seat0 xcursor_theme {theme} {size}")
        # gtk apps read the cursor from gsettings
        run_ok("gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", theme)
        run_ok("gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(size))

    def set_backend(self, backend):
        dotconfig.stage_file(BACKEND_FILE, backend + "\n", "palette style")
        self.panel.update_pending()
        self.wal_status.set_label("used from the next theme change")

    def rerun_wal(self):
        match = re.search(r'^("[^"]*"|\S+)', self.sway("output * bg", "") or "")
        path = os.path.expanduser(match.group(1).strip('"')) if match else ""
        if not os.path.exists(path):
            self.wal_status.set_label("no wallpaper set")
            return
        self.wal_status.set_label("regenerating...")
        backend = self.backend.value or "colorz"
        env_cmd = ["env", f"WAL_BACKEND={backend}", os.path.join(HOME, ".local/bin/wal.sh"), path]
        in_background(lambda: run_ok(*env_cmd, timeout=300),
                      lambda r: self.wal_status.set_label("done" if r is not None and r[0] else "wal.sh failed"))
