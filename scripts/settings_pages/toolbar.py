import json
import os
import re

from gi.repository import Gtk

import dotconfig

from .common import HOME, Choice, Page, Slider, Toggle, button, label, row, run

TEMPLATE = os.path.join(HOME, ".config/wal/templates/waybar-config.jsonc")
LOCATION_FILE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local/state"), "weather-location")
RENDERED = os.path.join(HOME, ".cache/wal/waybar-config.jsonc")
RENDER = f"sed 's/{{{{/{{/g; s/}}}}/}}/g' {TEMPLATE} > {RENDERED} && pkill -SIGUSR2 -x waybar"
MODULES = [
    ("sway/workspaces", "workspaces"), ("custom/now-playing", "now playing"), ("custom/clock", "clock"),
    ("custom/timer", "timers"), ("custom/stay-awake", "stay awake icon"),
    ("custom/notification", "notifications"), ("group/tray-expander", "tray"), ("custom/agents", "coding agents"),
    ("custom/weather", "weather"), ("custom/network-speed", "network speed"), ("custom/system", "cpu & memory"),
    ("bluetooth", "bluetooth"), ("network", "wi-fi"), ("custom/tailscale", "tailscale"),
    ("custom/audio", "volume"), ("custom/battery", "battery"),
]
# where a module goes back to when it's turned on again
HOMES = {name: section for section, names in (
    ("modules-left", ["sway/workspaces", "sway/mode", "custom/now-playing"]),
    ("modules-center", ["custom/clock", "custom/timer", "custom/stay-awake", "custom/notification"]),
    ("modules-right", ["group/tray-expander", "custom/agents", "custom/weather", "custom/network-speed",
                       "custom/system", "bluetooth", "network", "custom/tailscale",
                       "custom/audio", "custom/battery"])) for name in names}
ORDER = [name for name, _ in MODULES]


def load_config():
    """The waybar config from the template (with unsaved changes), as a dict."""
    text = dotconfig.file_pending_content(TEMPLATE)
    if text is None:
        text = dotconfig.read(TEMPLATE)
    try:
        return json.loads(text.replace("{{", "{").replace("}}", "}"))
    except ValueError:
        return None


def stage_config(config):
    text = json.dumps(config, indent="\t", ensure_ascii=False).replace("{", "{{").replace("}", "}}") + "\n"
    dotconfig.stage_file(TEMPLATE, text, "toolbar", apply=RENDER)
    # preview it right away: waybar reads the rendered copy
    try:
        dotconfig.write_atomic(RENDERED, text.replace("{{", "{").replace("}}", "}"))
    except OSError:
        return
    run("pkill", "-SIGUSR2", "-x", "waybar")


def clock_format(config):
    command = config.get("custom/clock", {}).get("exec", "")
    match = re.search(r"date \+'([^']*)'", command)
    return match.group(1) if match else "%I:%M %p %A, %b %d"


def set_clock(config, twelve=None, date=None):
    fmt = clock_format(config)
    time_part = "%I:%M %p" if "%I" in fmt or "%l" in fmt else "%H:%M"
    date_part = fmt.replace("%I:%M %p", "").replace("%H:%M", "").strip()
    if twelve is not None:
        time_part = "%I:%M %p" if twelve else "%H:%M"
    if date is not None:
        date_part = "%A, %b %d" if date else ""
    new = f"{time_part} {date_part}".strip()
    config.setdefault("custom/clock", {})["exec"] = f"date +'{new}' | tr '[:upper:]' '[:lower:]'"
    stage_config(config)


class ToolbarPage(Page):
    name = "toolbar"

    def __init__(self, panel):
        super().__init__(panel)
        self.section("bar")
        self.position = Choice([("top", "top"), ("bottom", "bottom")], lambda v: self.change(position=v))
        self.height = Slider("height", lambda v: self.change(height=int(v)), lower=22, upper=44, step=1,
                             fmt="{:.0f} px", throttle=None)
        self.add(row("position", self.position), self.height)

        self.section("clock")
        self.twelve = Toggle(lambda on: self.with_config(lambda c: set_clock(c, twelve=on)))
        self.date = Toggle(lambda on: self.with_config(lambda c: set_clock(c, date=on)))
        self.add(row("12-hour time", self.twelve), row("show the date", self.date))

        self.section("show")
        self.modules = {}
        for name, title in MODULES:
            toggle = Toggle(lambda on, name=name: self.set_module(name, on))
            self.modules[name] = toggle
            self.add(row(title, toggle))
        self.section("weather")
        self.location = Gtk.Entry(placeholder_text="detected automatically", hexpand=True)
        self.location.connect("activate", lambda _e: self.save_location())
        self.add(row("location", self.location, button("set", self.save_location),
                     sub=label("a city or zip code", "dim")))
        self.note = label("", "dim", "row")
        self.add(self.note)

    def save_location(self):
        os.makedirs(os.path.dirname(LOCATION_FILE), exist_ok=True)
        with open(LOCATION_FILE, "w") as f:
            f.write(self.location.get_text().strip() + "\n")
        # the weather module restarts on its own and fetches the new place
        run("pkill", "-f", "sysinfo.py weather")
        self.note.set_label("weather location saved")

    def with_config(self, action):
        config = load_config()
        if config is None:
            self.note.set_label("couldn't read the waybar template")
            return
        action(config)
        self.panel.update_pending()

    def refresh(self):
        config = load_config()
        if config is None:
            self.note.set_label("couldn't read the waybar template")
            return
        self.position.set_value(config.get("position", "top"))
        self.height.set_value(config.get("height", 30))
        fmt = clock_format(config)
        self.twelve.set_active("%I" in fmt or "%l" in fmt)
        self.date.set_active("%b" in fmt or "%d" in fmt or "%A" in fmt)
        if not self.location.has_focus():
            try:
                with open(LOCATION_FILE) as f:
                    self.location.set_text(f.read().strip())
            except OSError:
                pass
        shown = set(config.get("modules-left", []) + config.get("modules-center", []) + config.get("modules-right", []))
        for name, toggle in self.modules.items():
            toggle.set_active(name in shown)

    def change(self, **values):
        def apply(config):
            config.update(values)
            stage_config(config)
        self.with_config(apply)

    def set_module(self, name, on):
        def apply(config):
            section = HOMES[name]
            modules = [m for m in config.get(section, []) if m != name]
            if on:
                modules.append(name)
                modules.sort(key=lambda m: ORDER.index(m) if m in ORDER else -1)
            config[section] = modules
            stage_config(config)
        self.with_config(apply)
