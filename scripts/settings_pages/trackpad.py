import json

from .common import Choice, Page, Slider, Toggle, label, row, run

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

        self.section("speed")
        self.speed = Slider("pointer", lambda v: self.set("pointer_accel", f"{v:.2f}"),
                            lower=-1, upper=1, step=0.05, fmt="{:+.2f}", throttle=None)
        self.profile = Choice([("adaptive", "adaptive"), ("flat", "flat")], lambda v: self.set("accel_profile", v))
        self.scroll = Slider("scrolling", lambda v: self.set("scroll_factor", f"{v:.2f}"),
                             lower=0.2, upper=3, step=0.1, fmt="{:.1f}x", throttle=None)
        self.add(self.speed, row("acceleration", self.profile), self.scroll)

    def set(self, key, value):
        self.stage(f"input {DEVICE} {key} {value}")

    def refresh(self):
        state = libinput_state()
        for key, toggle in self.switches.items():
            value = self.sway(f"input {DEVICE} {key}") or state.get(key, "disabled")
            toggle.set_active(value == "enabled")
        self.click.set_value(self.sway(f"input {DEVICE} click_method") or state.get("click_method", "clickfinger"))
        self.profile.set_value(self.sway(f"input {DEVICE} accel_profile") or state.get("accel_profile", "adaptive"))
        self.speed.set_value(float(self.sway(f"input {DEVICE} pointer_accel") or state.get("accel_speed", 0)))
        self.scroll.set_value(float(self.sway(f"input {DEVICE} scroll_factor") or 1))

    def shown(self):
        self.refresh()
