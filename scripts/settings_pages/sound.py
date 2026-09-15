import json
import re

from .common import ItemList, Page, Slider, Toggle, button, row, run, spawn


def wpctl_volume(node):
    """(percent, muted) for a wpctl node such as @DEFAULT_AUDIO_SINK@."""
    output = run("wpctl", "get-volume", node, timeout=3)
    match = re.search(r"Volume: ([\d.]+)", output)
    return (round(float(match.group(1)) * 100) if match else 0), "MUTED" in output


class SoundPage(Page):
    name = "sound"
    interval = 2

    def __init__(self, panel):
        super().__init__(panel)
        self.controls = {}
        for kind, node in (("sink", "@DEFAULT_AUDIO_SINK@"), ("source", "@DEFAULT_AUDIO_SOURCE@")):
            title = "output" if kind == "sink" else "input"
            end = [button("mixer", self.open_mixer)] if kind == "sink" else []
            self.section(title, *end)
            volume = Slider("volume", lambda v, node=node: run("wpctl", "set-volume", "-l", "1.0", node, f"{v / 100:.2f}"))
            mute = Toggle(lambda on, node=node: run("wpctl", "set-mute", node, "1" if on else "0"))
            devices = ItemList(lambda name, kind=kind: self.set_default(kind, name), empty=f"no {title} devices")
            self.add(volume, row("mute", mute), devices)
            self.controls[kind] = (node, volume, mute, devices)

    def refresh(self):
        for kind, (node, volume, mute, devices) in self.controls.items():
            percent, muted = wpctl_volume(node)
            volume.set_value(percent)
            mute.set_active(muted)
            default = run("pactl", f"get-default-{kind}", timeout=3).strip()
            try:
                nodes = json.loads(run("pactl", "-f", "json", "list", f"{kind}s", timeout=3) or "[]")
            except ValueError:
                nodes = []
            devices.set_items((n["name"], n.get("description") or n["name"], "", n["name"] == default)
                              for n in nodes if not n["name"].endswith(".monitor"))

    def set_default(self, kind, name):
        run("pactl", f"set-default-{kind}", name)
        self.refresh()

    def open_mixer(self):
        spawn("pavucontrol")
