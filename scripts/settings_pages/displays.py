import json

from gi.repository import Gtk

from .common import V, Choice, Page, Slider, label, row, run

# scales that divide the 2560x1600 panel into whole logical pixels (others leave a glitchy row)
SCALES = [(1.0, "1 · 2560x1600"), (1.25, "1.25 · 2048x1280"), (1.333333, "1.33 · 1920x1200"),
          (1.6, "1.6 · 1600x1000"), (1.666667, "1.67 · 1536x960"), (2.0, "2 · 1280x800")]


def brightness(*device):
    """Percent brightness of a brightnessctl device, or None if there isn't one."""
    fields = run("brightnessctl", "-m", *device, timeout=3).partition("\n")[0].split(",")
    try:
        return round(int(fields[2]) * 100 / int(fields[4]))
    except (IndexError, ValueError, ZeroDivisionError):
        return None


class DisplayPage(Page):
    name = "displays"
    interval = 2

    def __init__(self, panel):
        super().__init__(panel)
        self.section("brightness")
        # never all the way to 0%, that turns the panel off
        self.screen = Slider("display", lambda v: run("brightnessctl", "-q", "-c", "backlight", "set", f"{max(v, 1):.0f}%"))
        self.keyboard = Slider("keyboard", lambda v: run("brightnessctl", "-q", "-d", "kbd_backlight", "set", f"{v:.0f}%"))
        self.keyboard.set_visible(brightness("-d", "kbd_backlight") is not None)
        self.add(self.screen, self.keyboard)
        self.section("outputs")
        self.outputs = Gtk.Box(orientation=V)
        self.add(self.outputs)

    def shown(self):
        while child := self.outputs.get_first_child():
            self.outputs.remove(child)
        try:
            outputs = json.loads(run("swaymsg", "-r", "-t", "get_outputs", timeout=3) or "[]")
        except ValueError:
            outputs = []
        for output in outputs:
            mode = output.get("current_mode") or {}
            size = f"{mode.get('width', '?')}x{mode.get('height', '?')} @ {mode.get('refresh', 0) / 1000:.0f}hz"
            model = f"{output.get('make', '')} {output.get('model', '')}".strip()
            name = output["name"]
            self.outputs.append(row(name, label(size, "dim"), sub=label(model.lower(), "dim")))
            scale = Choice(SCALES, lambda value, name=name: self.stage(f"output {name} scale {value:g}"))
            current = float(self.sway(f"output {name} scale") or output.get("scale", 1))
            scale.set_value(min((s for s, _t in SCALES), key=lambda s: abs(s - current)))
            self.outputs.append(row("scale", scale, sub=label("looks like", "dim")))
        super().shown()

    def refresh(self):
        if (value := brightness("-c", "backlight")) is not None:
            self.screen.set_value(value)
        if self.keyboard.get_visible() and (value := brightness("-d", "kbd_backlight")) is not None:
            self.keyboard.set_value(value)
