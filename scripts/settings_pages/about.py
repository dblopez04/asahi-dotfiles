import os
import re

from .common import Page, human_size, read, run, value_row


class AboutPage(Page):
    name = "about"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        os_release = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read("/etc/os-release"), re.M))
        self.section("this mac")
        static = [
            ("model", read("/proc/device-tree/model").rstrip("\0")),
            ("chip", self.chip()),
            ("memory", human_size(self.meminfo().get("MemTotal", 0) * 1024)),
            ("os", os_release.get("PRETTY_NAME", "linux").lower()),
            ("kernel", os.uname().release),
            ("desktop", (run("sway", "--version").strip() or "sway").lower()),
            ("hostname", os.uname().nodename),
        ]
        for key, value in static:
            line, label_widget = value_row(key)
            label_widget.set_label(value)
            self.add(line)
        self.section("right now")
        self.values = {}
        for key in ("memory used", "disk used", "uptime", "load"):
            line, self.values[key] = value_row(key)
            self.add(line)

    @staticmethod
    def chip():
        compatible = read("/proc/device-tree/compatible").split("\0")
        chip = next((c.split(",")[1] for c in compatible if c.startswith("apple,t")), "")
        names = {"t8103": "apple m1", "t6000": "apple m1 pro", "t6001": "apple m1 max", "t8112": "apple m2",
                 "t6020": "apple m2 pro", "t6021": "apple m2 max"}
        return f"{names.get(chip, chip or 'arm64')} · {os.cpu_count()} cores"

    @staticmethod
    def meminfo():
        return {k: int(v) for k, v in re.findall(r"^(\w+):\s+(\d+)", read("/proc/meminfo"), re.M)}

    def refresh(self):
        mem = self.meminfo()
        total, available = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        self.values["memory used"].set_label(f"{human_size((total - available) * 1024)} of {human_size(total * 1024)}")
        disk = os.statvfs("/")
        size, free = disk.f_blocks * disk.f_frsize, disk.f_bavail * disk.f_frsize
        self.values["disk used"].set_label(f"{human_size(size - free)} of {human_size(size)}")
        minutes = int(float(read("/proc/uptime", "0").split()[0])) // 60
        self.values["uptime"].set_label(f"{minutes // 1440}d {minutes // 60 % 24}h {minutes % 60}m")
        self.values["load"].set_label(" ".join(read("/proc/loadavg").split()[:3]))
