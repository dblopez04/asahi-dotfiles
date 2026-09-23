import glob
import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .common import (Chart, Choice, ItemList, Page, button, duration, in_background, label, load_theme, read, row,
                      run_ok, value_row)

STATE = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
USAGE = os.path.join(STATE, "usage")
# restored at login by the sway config, since the limit resets on boot
SAVED_LIMIT = os.path.join(STATE, "battery-limit")
LIMITS = [(100, "off (charge to 100%)"), (90, "90%"), (80, "80%"), (70, "70%"), (60, "60%"), (50, "50%")]
LIMIT_NOTE = "stops charging here to slow battery wear"
UPOWER_DEVICE = "/org/freedesktop/UPower/devices/battery_macsmc_battery"


def upower_history(kind, seconds, points):
    """[(time, value, state)] from upower (charge in %, rate in W), oldest first."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        reply = bus.call_sync("org.freedesktop.UPower", UPOWER_DEVICE, "org.freedesktop.UPower.Device", "GetHistory",
                              GLib.Variant("(suu)", (kind, seconds, points)), None, 0, 3000, None)
        return sorted((t, v, s) for t, v, s in reply.unpack()[0] if t and s != 0)
    except GLib.Error:
        return []


def samples(since):
    items = []
    for path in sorted(glob.glob(os.path.join(USAGE, "*.jsonl"))):
        if os.path.getmtime(path) < since:
            continue
        with open(path) as f:
            for line in f:
                try:
                    sample = json.loads(line)
                except ValueError:
                    continue
                if sample.get("t", 0) >= since:
                    items.append(sample)
    return items


class BatteryPage(Page):
    name = "battery"
    interval = 10

    def __init__(self, panel):
        super().__init__(panel)
        supplies = "/sys/class/power_supply"
        names = sorted(os.listdir(supplies)) if os.path.isdir(supplies) else []
        self.path = next((f"{supplies}/{n}" for n in names if read(f"{supplies}/{n}/type") == "Battery"), None)
        self.days = 1
        if not self.path:
            self.add(label("no battery", "dim", "row"))
            return

        self.level = Gtk.LevelBar(hexpand=True, valign=Gtk.Align.CENTER, min_value=0, max_value=100)
        for offset in (Gtk.LEVEL_BAR_OFFSET_LOW, Gtk.LEVEL_BAR_OFFSET_HIGH, Gtk.LEVEL_BAR_OFFSET_FULL):
            self.level.remove_offset_value(offset)
        self.percent = label("", "accent", xalign=1.0)
        self.percent.set_width_chars(5)
        charge = Gtk.Box(spacing=12, css_classes=["row"])
        charge.append(label("charge", "title"))
        charge.append(self.level)
        charge.append(self.percent)
        self.add(charge)
        self.values = {}
        for key in ("status", "time", "power draw"):
            line, self.values[key] = value_row(key)
            self.add(line)

        self.range_buttons = {}
        header = self.section("history")
        for days, text in ((1, "24 hours"), (10, "10 days")):
            tab = Gtk.Button(label=text, css_classes=["tab"])
            tab.connect("clicked", lambda _b, d=days: self.set_range(d))
            header.append(tab)
            self.range_buttons[days] = tab
        self.level_chart = Chart(100)
        self.use_chart = Chart(80)
        self.summary = label("", "dim", "row", wrap=True)
        self.add(label("battery level", "dim", "row"), self.level_chart,
                 label("screen on (bars) and power draw (line)", "dim", "row"), self.use_chart, self.summary)

        self.section("apps using the most energy")
        self.apps = ItemList(lambda _k: None, empty="collecting... (history starts once the usage sampler has run a while)")
        self.add(self.apps)
        self.sampler_row = row("usage history", button("start recording", self.start_sampler),
                               sub=label("a tiny background service samples once a minute", "dim"))
        self.add(self.sampler_row)

        self.section("health")
        for key in ("capacity", "cycles"):
            line, self.values[key] = value_row(key)
            self.add(line)
        self.limit = Choice(LIMITS, self.set_limit)
        self.limit_note = label(LIMIT_NOTE, "dim", wrap=True)
        self.add(row("charge limit", self.limit, sub=self.limit_note))

    def shown(self):
        if self.path:
            self.set_range(self.days)
        super().shown()

    def refresh(self):
        if not self.path:
            return
        value = lambda name: read(f"{self.path}/{name}")
        number = lambda name: int(value(name) or 0)
        capacity, status = number("capacity"), value("status").lower()
        self.level.set_value(capacity)
        self.percent.set_label(f"{capacity}%")
        if status == "discharging" and number("time_to_empty_now"):
            time_text = f"{duration(number('time_to_empty_now'))} left"
        elif status == "charging" and number("time_to_full_now"):
            time_text = f"{duration(number('time_to_full_now'))} until full"
        else:
            time_text = "-"
        full = number("energy_full") or number("charge_full")
        design = number("energy_full_design") or number("charge_full_design")
        self.values["status"].set_label(status)
        self.values["time"].set_label(time_text)
        self.values["power draw"].set_label(f"{abs(number('power_now')) / 1e6:.1f} w" if value("power_now") else "-")
        self.values["capacity"].set_label(f"{full * 100 // design}% of new" if design else "-")
        self.values["cycles"].set_label(value("cycle_count") or "-")
        limit = value("charge_control_end_threshold")
        self.limit.set_sensitive(bool(limit))
        self.limit.set_value(int(limit) if limit else None)
        active = os.system("systemctl --user --quiet is-active usage-sampler.service") == 0
        self.sampler_row.set_visible(not active)

    def set_range(self, days):
        self.days = days
        for d, tab in self.range_buttons.items():
            (tab.add_css_class if d == days else tab.remove_css_class)("on")
        in_background(lambda: self._load(days), self._show_history)

    def _load(self, days):
        seconds = days * 86400
        return days, upower_history("charge", seconds, 300), upower_history("rate", seconds, 300), \
            samples(time.time() - seconds)

    def _show_history(self, result):
        if isinstance(result, Exception):
            self.summary.set_label(f"couldn't read the history: {result}")
            return
        days, charge, rate, usage = result
        theme = load_theme()
        now = time.time()
        span = days * 86400
        slots = 48 if days == 1 else days * 12  # 30 minute or 2 hour buckets
        width = span / slots
        start = now - span

        def bucket(t):
            return min(slots - 1, max(0, int((t - start) // width)))

        levels = [None] * slots
        for t, v, _state in charge:
            if t >= start:
                levels[bucket(t)] = v / 100
        watts = [[] for _ in range(slots)]
        for t, v, _state in rate:
            if t >= start:
                watts[bucket(t)].append(v)
        screen = [[0, 0] for _ in range(slots)]  # [on samples, samples]
        app_energy, screen_minutes, battery_minutes = {}, 0, 0
        for sample in usage:
            b = bucket(sample["t"])
            screen[b][1] += 1
            if sample.get("screen"):
                screen[b][0] += 1
                screen_minutes += 1
            if not sample.get("charging"):
                battery_minutes += 1
                draw = abs(sample.get("watts", 0))  # the battery reports discharging as negative
                for app, share in sample.get("apps", {}).items():
                    app_energy[app] = app_energy.get(app, 0) + draw * share / 60  # watt-hours
            if sample.get("watts") is not None and not rate:
                watts[b].append(abs(sample["watts"]))

        peak = max([max(w) for w in watts if w] + [10])
        labels = ([(i / 4, time.strftime("%-I %p", time.localtime(start + span * i / 4)).lower()) for i in range(5)]
                  if days == 1 else [(i / days, time.strftime("%a", time.localtime(start + 86400 * i))) for i in range(days)])
        colors = {"grid": theme["faint"], "line": theme["fg"], "text": theme["dim"]}
        self.level_chart.set_data(bars=[(v or 0, theme["accent"]) for v in levels], labels=labels, colors=colors)
        self.use_chart.set_data(bars=[(on / total if total else 0, theme["c4"]) for on, total in screen],
                                line=[(sum(w) / len(w) / peak) if w else None for w in watts],
                                labels=labels, colors=colors)
        parts = []
        if usage:
            parts.append(f"screen on {duration(screen_minutes * 60)}")
            parts.append(f"on battery {duration(battery_minutes * 60)}")
        if any(watts):
            average = [sum(w) / len(w) for w in watts if w]
            parts.append(f"average draw {sum(average) / len(average):.1f} w · peak {peak:.1f} w")
        self.summary.set_label("  ·  ".join(parts) or "no history yet")
        total = sum(app_energy.values()) or 1
        top = sorted(app_energy.items(), key=lambda kv: -kv[1])[:8]
        self.apps.set_items((app, app, f"{energy / total * 100:.0f}%  ·  {energy:.1f} wh", False) for app, energy in top)

    def set_limit(self, percent):
        path = f"{self.path}/charge_control_end_threshold"
        self.limit_note.set_label("setting...")

        def work():
            try:
                with open(path, "w") as f:
                    f.write(str(percent))
                ok, output = True, ""
            except PermissionError:  # install.sh's udev rule makes it writable; until then ask polkit
                ok, output = run_ok("pkexec", "tee", path, input=str(percent), timeout=120)
            except OSError as e:
                ok, output = False, str(e)
            if ok:
                os.makedirs(STATE, exist_ok=True)
                with open(SAVED_LIMIT, "w") as f:
                    f.write(f"{percent}\n")
            return ok, output

        def done(result):
            ok, output = result
            actual = read(path)
            if not ok:
                note = f"couldn't change it: {output or 'permission denied'}"
            elif actual and int(actual) != percent:
                note = f"this firmware only supports {actual}%"  # older firmware: just 80% or off
            else:
                note = LIMIT_NOTE
            self.limit_note.set_label(note)
            self.refresh()

        in_background(work, done)

    def start_sampler(self):
        os.system("systemctl --user daemon-reload; systemctl --user enable --now usage-sampler.service")
        self.refresh()
