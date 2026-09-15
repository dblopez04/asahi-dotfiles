"""Widgets and helpers shared by the settings panel and its pages."""
import json
import math
import os
import re
import shlex
import subprocess
import sys
import threading

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gtk, Pango  # noqa: E402

SCRIPTS = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import dotconfig  # noqa: E402

V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL
HOME = os.path.expanduser("~")
WAL = os.path.join(HOME, ".cache/wal")

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
             "border": "#896822", "sel": "#896822", "sel_fg": "#1b1c19",
             "c1": "#896822", "c2": "#897130", "c3": "#8B784E", "c4": "#7A8270", "c5": "#998628", "c6": "#988B64"}
    try:
        with open(f"{WAL}/colors.json") as f:
            wal = json.load(f)
        special, colors = wal["special"], wal["colors"]
        theme.update(bg=special["background"], fg=special["foreground"], accent=colors["color2"],
                     dim=colors["color8"], border=colors["color1"], sel=colors["color1"],
                     sel_fg=special["background"], **{f"c{i}": colors[f"color{i}"] for i in range(1, 7)})
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


def rgba(color, alpha=1.0):
    value = Gdk.RGBA()
    value.parse(color)
    value.alpha = alpha
    return value


###############
### HELPERS ###
###############


def run(*cmd, timeout=10, input=None):
    """Run a command and return its stdout ('' if it failed or isn't installed)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def run_ok(*cmd, timeout=30, input=None):
    """Run a command and return (succeeded, its last line of output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    lines = (p.stderr.strip() or p.stdout.strip()).splitlines()
    return p.returncode == 0, lines[-1] if lines else ""


def run_json(*cmd, timeout=15, default=None):
    try:
        return json.loads(run(*cmd, timeout=timeout) or "null") or default
    except ValueError:
        return default


def spawn(*cmd):
    """Start a program that outlives the panel."""
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def in_terminal(title, command, keep_open=True):
    """Run a shell command in a terminal (for sudo prompts and long jobs with output)."""
    tail = "; echo; printf 'done, press enter to close'; read _" if keep_open else ""
    spawn("kitty", "--class", "settings-task", "--title", title, "sh", "-c", command + tail)


def in_background(work, done=None):
    """Run work() on a thread, then done(result) back on the GTK thread."""
    def target():
        try:
            result = work()
        except Exception as e:  # a page bug shouldn't kill the thread silently
            result = e
        if done:
            GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=target, daemon=True).start()


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def human_size(size):
    for unit in ("b", "kb", "mb", "gb", "tb"):
        if abs(size) < 1024 or unit == "tb":
            return f"{size:.0f} {unit}" if unit in ("b", "kb") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} tb"


def duration(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds // 60 % 60:02d}m"
    return f"{seconds // 60}m"


def quote(value):
    return shlex.quote(value)


###############
### WIDGETS ###
###############


def label(text="", *classes, xalign=0.0, hexpand=False, ellipsize=False, wrap=False, selectable=False):
    widget = Gtk.Label(label=text, xalign=xalign, hexpand=hexpand, css_classes=list(classes))
    if ellipsize:
        widget.set_ellipsize(Pango.EllipsizeMode.END)
    if wrap:
        widget.set_wrap(True)
        widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if selectable:
        widget.set_selectable(True)
    return widget


def button(text, on_click, *classes, tooltip=None):
    widget = Gtk.Button(label=f"[ {text} ]", css_classes=["flat", *classes], valign=Gtk.Align.CENTER)
    widget.connect("clicked", lambda _: on_click())
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


def row(title, *end, sub=None):
    """A settings line: title (and an optional subtitle widget) on the left, controls on the right."""
    box = Gtk.Box(spacing=12, css_classes=["row"])
    text = Gtk.Box(orientation=V, hexpand=True, valign=Gtk.Align.CENTER)
    text.append(label(title, "title"))
    if sub is not None:
        text.append(sub)
    box.append(text)
    for widget in end:
        box.append(widget)
    return box


def value_row(title):
    """A row showing a value; returns (row, value label)."""
    value = label("", "dim", selectable=True, ellipsize=True)
    value.set_xalign(1.0)
    return row(title, value), value


class Toggle(Gtk.Button):
    """A text switch, [on ] / [off]."""

    def __init__(self, on_change):
        super().__init__(css_classes=["toggle"], valign=Gtk.Align.CENTER)
        self.on_change = on_change
        self.active = False
        self.set_active(False)
        self.connect("clicked", self._clicked)

    def _clicked(self, _):
        self.set_active(not self.active)
        self.on_change(self.active)

    def set_active(self, active):
        self.active = bool(active)
        self.set_label("[on ]" if self.active else "[off]")
        (self.add_css_class if self.active else self.remove_css_class)("on")


class Slider(Gtk.Box):
    """A scale with a title and value. on_change runs at most every `throttle` ms while dragging,
    or only on release when throttle is None (for changes that reload sway)."""

    def __init__(self, title, on_change, lower=0, upper=100, step=1, fmt="{:.0f}%", throttle=50, width_chars=12):
        super().__init__(spacing=12, css_classes=["row"])
        self.on_change = on_change
        self.fmt = fmt
        self.pending = None
        self.updating = False
        self.throttle = throttle
        title_label = label(title, "title")
        title_label.set_width_chars(width_chars)
        self.scale = Gtk.Scale.new_with_range(H, lower, upper, step)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.get_adjustment().set_step_increment(step)
        self.scale.get_adjustment().set_page_increment(step * 5)
        self.scale.connect("value-changed", self._changed)
        if throttle is None:
            release = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
            release.connect("released", lambda *_: self._flush_later())
            self.scale.add_controller(release)
            keys = Gtk.EventControllerKey()
            keys.connect("key-released", lambda *_: self._flush_later())
            self.scale.add_controller(keys)
        self.value = label("", "dim", xalign=1.0)
        self.value.set_width_chars(7)
        for widget in (title_label, self.scale, self.value):
            self.append(widget)

    def _changed(self, scale):
        value = scale.get_value()
        self.value.set_label(self.fmt.format(value))
        if self.updating:
            return
        if self.throttle is not None and self.pending is None:
            GLib.timeout_add(self.throttle, self._flush)
        self.pending = value

    def _flush_later(self):
        if self.pending is not None:
            GLib.timeout_add(300, self._flush)

    def _flush(self):
        value, self.pending = self.pending, None
        if value is not None:
            self.on_change(value)
        return False

    def set_value(self, value):
        # don't yank the slider out from under a drag
        if self.pending is not None or self.scale.get_state_flags() & Gtk.StateFlags.ACTIVE:
            return
        self.updating = True
        self.scale.set_value(value)
        self.updating = False
        self.value.set_label(self.fmt.format(value))


class Choice(Gtk.MenuButton):
    """A dropdown: [ current ▾ ] with a list of (value, text) options."""

    def __init__(self, options, on_change, width_chars=None):
        super().__init__(css_classes=["choice"], valign=Gtk.Align.CENTER)
        self.on_change = on_change
        self.value = None
        self.text = label("", xalign=0)
        if width_chars:
            self.text.set_width_chars(width_chars)
        box = Gtk.Box(spacing=6)
        box.append(label("["))
        box.append(self.text)
        box.append(label("▾ ]"))
        self.set_child(box)
        self.popover = Gtk.Popover(css_classes=["choices"], has_arrow=False)
        self.list = Gtk.Box(orientation=V)
        scroller = Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True, max_content_height=320)
        self.popover.set_child(scroller)
        self.set_popover(self.popover)
        self.set_options(options)

    def set_options(self, options):
        self.options = list(options)
        while child := self.list.get_first_child():
            self.list.remove(child)
        for value, text in self.options:
            item = Gtk.Button(label=text, css_classes=["item"])
            item.get_child().set_xalign(0)
            item.connect("clicked", lambda _, v=value: self._pick(v))
            self.list.append(item)
        if self.value is not None:
            self.set_value(self.value)

    def _pick(self, value):
        self.popover.popdown()
        if value != self.value:
            self.set_value(value)
            self.on_change(value)

    def set_value(self, value):
        self.value = value
        text = next((t for v, t in self.options if v == value), str(value) if value is not None else "-")
        self.text.set_label(text)


class ItemList(Gtk.Box):
    """Clickable '* name   detail' lines. Only rebuilt when the items change, and keeps keyboard focus.
    extra(key) may return widgets (buttons) to put at the end of a line."""

    def __init__(self, on_activate, empty="nothing here", extra=None):
        super().__init__(orientation=V)
        self.on_activate = on_activate
        self.empty = empty
        self.extra = extra
        self.items = None
        self.buttons = {}

    def set_items(self, items, force=False):
        """items: (key, name, detail, active) tuples."""
        items = list(items)
        if items == self.items and not force:
            return
        focused = next((key for key, b in self.buttons.items() if b.has_focus()), None)
        self.items = items
        self.buttons = {}
        while child := self.get_first_child():
            self.remove(child)
        if not items:
            self.append(label(self.empty, "dim", "row"))
        for key, name, detail, active in items:
            line = Gtk.Box()
            box = Gtk.Box(spacing=12)
            box.append(label(("* " if active else "  ") + name, hexpand=True, ellipsize=True))
            box.append(label(detail, "detail"))
            item = Gtk.Button(child=box, css_classes=["item"], hexpand=True)
            item.connect("clicked", lambda _, key=key: self.on_activate(key))
            line.append(item)
            for widget in (self.extra(key) if self.extra else []) or []:
                line.append(widget)
            self.append(line)
            self.buttons[key] = item
        if focused is not None and self.buttons:
            self.buttons.get(focused, next(iter(self.buttons.values()))).grab_focus()


# Drawn with GtkSnapshot rather than cairo: PyGObject's cairo support (python3-gobject, not just
# -base) isn't guaranteed to be installed.

def _rect(x, y, w, h):
    rect = Graphene.Rect()
    return rect.init(x, y, w, h)


class SegmentBar(Gtk.Widget):
    """A horizontal bar split into colored segments: [(fraction, color)]."""

    def __init__(self, height=14):
        super().__init__(hexpand=True, height_request=height)
        self.segments = []
        self.background = "#333333"

    def set_segments(self, segments, background):
        self.segments = segments
        self.background = background
        self.queue_draw()

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        snapshot.append_color(rgba(self.background), _rect(0, 0, width, height))
        x = 0.0
        for fraction, color in self.segments:
            w = max(0.0, fraction) * width
            if w >= 0.5:
                snapshot.append_color(rgba(color), _rect(x, 0, w, height))
                x += w


class Chart(Gtk.Box):
    """A small time chart: bars (0-1) with an optional line of dots (0-1), and x labels underneath."""

    class Plot(Gtk.Widget):
        def __init__(self, chart, height):
            super().__init__(hexpand=True, height_request=height)
            self.chart = chart

        def do_snapshot(self, snapshot):
            chart = self.chart
            width, height = self.get_width(), self.get_height()
            usable = height - 4
            for fraction in (0, 0.5, 1):
                y = round(height - 1 - fraction * usable)
                snapshot.append_color(rgba(chart.colors["grid"]), _rect(0, y, width, 1))
            if chart.bars:
                slot = width / len(chart.bars)
                for i, (value, color) in enumerate(chart.bars):
                    if value > 0:
                        h = max(1.0, value * usable)
                        snapshot.append_color(rgba(color), _rect(i * slot + slot * 0.15, height - h, max(1, slot * 0.7), h))
            if chart.line:
                step = width / max(1, len(chart.line) - 1)
                for i, value in enumerate(chart.line):
                    if value is not None:
                        y = height - 1 - value * usable
                        snapshot.append_color(rgba(chart.colors["line"]), _rect(i * step - 1.5, y - 1.5, 3, 3))

    def __init__(self, height=110):
        super().__init__(orientation=V, hexpand=True, css_classes=["row"])
        self.bars = []  # [(value 0-1, color)]
        self.line = []  # [value 0-1 or None]
        self.colors = {"grid": "#444444", "line": "#cccccc", "text": "#888888"}
        self.plot = Chart.Plot(self, height)
        self.axis = Gtk.Box(homogeneous=True)
        self.append(self.plot)
        self.append(self.axis)

    def set_data(self, bars=None, line=None, labels=None, colors=None):
        self.bars = bars or []
        self.line = line or []
        self.colors.update(colors or {})
        while child := self.axis.get_first_child():
            self.axis.remove(child)
        for _fraction, text in labels or []:
            self.axis.append(label(text, "dim", xalign=0.0))
        self.plot.queue_draw()


def dialog(parent, title, body_widget, buttons, on_response=None, width=640, height=-1):
    """A square modal in the panel's style. buttons: [(text, response)]."""
    window = Gtk.Window(transient_for=parent, modal=True, decorated=False, title=title,
                        css_classes=["settings-dialog"], default_width=width, default_height=height)
    frame = Gtk.Box(orientation=V, css_classes=["frame"])
    frame.append(Gtk.WindowHandle(child=label(title, "prompt")))
    frame.append(Gtk.Box(css_classes=["hsep"]))
    body_widget.set_vexpand(True)
    frame.append(body_widget)
    frame.append(Gtk.Box(css_classes=["hsep"]))
    actions = Gtk.Box(spacing=4, halign=Gtk.Align.END, css_classes=["footer"])
    done = []

    def respond(response):
        if done:
            return
        done.append(response)
        window.destroy()
        if on_response:
            on_response(response)

    for text, response in buttons:
        actions.append(button(text, lambda r=response: respond(r)))
    frame.append(actions)
    window.set_child(frame)
    keys = Gtk.EventControllerKey()
    keys.connect("key-pressed", lambda _c, keyval, *_: keyval == Gdk.KEY_Escape and (respond(None) or True))
    window.add_controller(keys)
    window.connect("close-request", lambda _w: respond(None) or False)
    window.present()
    return window


def confirm(parent, title, text, action_text, on_yes):
    body = label(text, "row", wrap=True)
    body.set_margin_top(8)
    body.set_margin_bottom(8)
    dialog(parent, title, body, [("cancel", None), (action_text, "yes")],
           lambda r: r == "yes" and on_yes(), width=460)


############
### PAGE ###
############


class Page(Gtk.Box):
    name = ""
    interval = 0  # seconds between refresh() calls while the page is visible

    def __init__(self, panel):
        super().__init__(orientation=V, css_classes=["page"])
        self.panel = panel
        self.timer = 0

    def section(self, text, *end):
        box = Gtk.Box(spacing=12, css_classes=["section-row"])
        box.append(label(text + ":", "section", hexpand=True))
        for widget in end:
            box.append(widget)
        self.append(box)
        return box

    def add(self, *widgets):
        for widget in widgets:
            self.append(widget)

    def shown(self):
        self.refresh()
        if self.interval:
            self.timer = GLib.timeout_add_seconds(self.interval, lambda: self.refresh() or True)

    def hidden(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def refresh(self):
        pass

    def escape(self, focus):
        """Handle esc inside the page; return True to keep the keyboard here."""
        return False

    # ----- staged settings -----

    def stage(self, *lines, reload=True):
        """Stage sway lines as unsaved changes (applied live) and update the save bar."""
        try:
            ok, message = dotconfig.stage_sway(*lines, reload=reload)
        except OSError as e:
            ok, message = False, str(e)
        self.panel.update_pending()
        if not ok and message:
            self.panel.flash(f"sway: {message.lower()}")
        return ok

    @staticmethod
    def sway(key, default=None):
        """The effective (staged or saved) sway directive for key, without the key words."""
        line = dotconfig.sway_value(key)
        if not line:
            return default
        tokens = re.findall(r'"[^"]*"|\S+', line)
        skip = len(key.split())
        return " ".join(tokens[skip:]) or default


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def nice_number(value):
    return f"{value:g}" if isinstance(value, float) and not math.isnan(value) else str(value)
