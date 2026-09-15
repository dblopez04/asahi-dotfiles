import time

from gi.repository import Gtk

from . import toolbar
from .common import ItemList, Page, Toggle, in_background, label, row, run, run_ok, value_row


class DateTimePage(Page):
    name = "date & time"
    interval = 1

    def __init__(self, panel):
        super().__init__(panel)
        self.clock = label("", "accent")
        self.add(row("now", self.clock))
        self.twelve = Toggle(lambda on: self.set_clock(on))
        self.add(row("12-hour clock", self.twelve, sub=label("in the top bar", "dim")))

        self.section("time zone")
        self.ntp = Toggle(self.set_ntp)
        line, self.zone = value_row("time zone")
        self.add(row("set automatically from the internet", self.ntp), line)
        self.search = Gtk.SearchEntry(placeholder_text="search time zones", hexpand=True)
        self.search.connect("search-changed", lambda _: self.fill_zones())
        self.zones = ItemList(self.set_zone, empty="no matching time zones")
        self.status = label("", "dim", "row")
        self.add(row("", self.search), self.zones, self.status)
        self.all_zones = []
        self.state = {}

    def shown(self):
        if not self.all_zones:
            in_background(lambda: run("timedatectl", "list-timezones").split(), self._zones_loaded)
        self.read_state()
        config = toolbar.load_config()
        if config:
            fmt = toolbar.clock_format(config)
            self.twelve.set_active("%I" in fmt or "%l" in fmt)
        super().shown()

    def read_state(self):
        self.state = dict(line.partition("=")[::2] for line in run("timedatectl", "show").splitlines())
        self.ntp.set_active(self.state.get("NTP") == "yes")
        self.zone.set_label(self.state.get("Timezone", ""))

    def refresh(self):
        twelve = self.twelve.active
        self.clock.set_label(time.strftime("%-I:%M:%S %p · %A, %B %-d %Y" if twelve else "%H:%M:%S · %A, %B %-d %Y").lower())

    def _zones_loaded(self, zones):
        self.all_zones = zones if isinstance(zones, list) else []
        self.fill_zones()

    def fill_zones(self):
        query = self.search.get_text().lower().replace(" ", "_")
        if not query:
            self.zones.set_items([])
            self.zones.empty = "type a city or region"
            return
        self.zones.empty = "no matching time zones"
        current = self.state.get("Timezone")
        matches = [z for z in self.all_zones if query in z.lower()][:15]
        self.zones.set_items((z, z.replace("_", " "), "", z == current) for z in matches)

    def set_zone(self, zone):
        self.status.set_label(f"setting {zone}...")
        # timedatectl asks polkit for permission (the password prompt)
        in_background(lambda: run_ok("timedatectl", "set-timezone", zone, timeout=120),
                      lambda r: (self.status.set_label(f"time zone is {zone}" if r[0] else f"failed: {r[1].lower()}"),
                                 self.read_state(), self.fill_zones()))

    def set_ntp(self, on):
        in_background(lambda: run_ok("timedatectl", "set-ntp", "true" if on else "false", timeout=120),
                      lambda r: (self.status.set_label("" if r[0] else f"failed: {r[1].lower()}"), self.read_state()))

    def set_clock(self, twelve):
        config = toolbar.load_config()
        if config:
            toolbar.set_clock(config, twelve=twelve)
            self.panel.update_pending()
