import json
import os

from .common import Choice, Page, Slider, Toggle, label, row, run

GESTURES = [("swipe:3:left", "3 fingers left"), ("swipe:3:right", "3 fingers right"), ("swipe:3:up", "3 fingers up"),
            ("swipe:3:down", "3 fingers down"), ("swipe:4:left", "4 fingers left"), ("swipe:4:right", "4 fingers right"),
            ("swipe:4:up", "4 fingers up"), ("swipe:4:down", "4 fingers down")]
ACTIONS = [
    ("nothing", None),
    ("next workspace", "workspace next_on_output"),
    ("previous workspace", "workspace prev_on_output"),
    ("move window to next workspace", "move container to workspace next_on_output, workspace next_on_output"),
    ("move window to previous workspace", "move container to workspace prev_on_output, workspace prev_on_output"),
    ("spotlight", "exec ~/.local/bin/spotlight.py"),
    ("notification center", "exec swaync-client -t -sw"),
    ("keyboard shortcuts", "exec ~/.local/bin/cheatsheet.py"),
    ("fullscreen", "fullscreen"),
    ("float / tile", "floating toggle"),
    ("show the scratchpad", "scratchpad show"),
    ("clipboard history", "exec ~/.local/bin/clipboard-history.py pick"),
    ("screenshot an area", "exec ~/.local/bin/screenshot.sh area"),
]

DEVICE = "type:touchpad"


def libinput_state():
    """The touchpad's current libinput settings from sway."""
    try:
        inputs = json.loads(run("swaymsg", "-r", "-t", "get_inputs", timeout=3) or "[]")
    except ValueError:
        return {}
    return next((i.get("libinput", {}) for i in inputs if i.get("type") == "touchpad"), {})


class TrackpadPage(Page):
    name = "trackpad"

    def __init__(self, panel):
        super().__init__(panel)
        self.switches = {}
        self.section("point and click")
        for key, title, sub in (("tap", "tap to click", None),
                                ("tap_drag", "tap and drag", None),
                                ("natural_scroll", "natural scrolling", "content follows your fingers"),
                                ("dwt", "disable while typing", None),
                                ("middle_emulation", "middle click", "click left and right together")):
            toggle = Toggle(lambda on, key=key: self.set(key, "enabled" if on else "disabled"))
            self.switches[key] = toggle
            self.add(row(title, toggle, sub=label(sub, "dim") if sub else None))

        self.click = Choice([("clickfinger", "fingers (two = right click)"), ("button_areas", "areas (bottom right = right click)")],
                            lambda v: self.set("click_method", v))
        self.add(row("click method", self.click))

        self.section("gestures")
        self.gestures = {}
        for gesture, title in GESTURES:
            choice = Choice([(name, name) for name, _command in ACTIONS], lambda v, g=gesture: self.set_gesture(g, v))
            self.gestures[gesture] = choice
            self.add(row(title, choice))

        self.section("speed")
        self.speed = Slider("pointer", lambda v: self.set("pointer_accel", f"{v:.2f}"),
                            lower=-1, upper=1, step=0.05, fmt="{:+.2f}", throttle=None)
        self.profile = Choice([("adaptive", "adaptive"), ("flat", "flat")], lambda v: self.set("accel_profile", v))
        self.scroll = Slider("scrolling", lambda v: self.set("scroll_factor", f"{v:.2f}"),
                             lower=0.2, upper=3, step=0.1, fmt="{:.1f}x", throttle=None)
        self.add(self.speed, row("acceleration", self.profile), self.scroll)

    def set(self, key, value):
        self.stage(f"input {DEVICE} {key} {value}")

    def set_gesture(self, gesture, action):
        command = dict(ACTIONS)[action]
        self.stage(f"bindgesture {gesture} {command}" if command else f"unbindgesture {gesture}")

    def refresh(self):
        state = libinput_state()
        commands = {command: name for name, command in ACTIONS if command}
        for gesture, choice in self.gestures.items():
            line = self.sway(f"bindgesture {gesture}")
            if line and line.split(maxsplit=1)[-1:] and line.startswith(gesture):
                command = line[len(gesture):].strip()
            else:
                command = line or ""
            name = commands.get(command.replace(os.path.expanduser("~"), "~"), "nothing" if not command else command)
            if name not in dict(ACTIONS):
                choice.set_options([(n, n) for n, _c in ACTIONS] + [(name, f"custom: {name[:30]}")])
            choice.set_value(name)
        for key, toggle in self.switches.items():
            value = self.sway(f"input {DEVICE} {key}") or state.get(key, "disabled")
            toggle.set_active(value == "enabled")
        self.click.set_value(self.sway(f"input {DEVICE} click_method") or state.get("click_method", "clickfinger"))
        self.profile.set_value(self.sway(f"input {DEVICE} accel_profile") or state.get("accel_profile", "adaptive"))
        self.speed.set_value(float(self.sway(f"input {DEVICE} pointer_accel") or state.get("accel_speed", 0)))
        self.scroll.set_value(float(self.sway(f"input {DEVICE} scroll_factor") or 1))

    def shown(self):
        self.refresh()
