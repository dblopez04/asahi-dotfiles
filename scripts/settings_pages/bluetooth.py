import re
import time

from .common import ItemList, Page, Toggle, button, confirm, in_background, label, row, run, run_ok, value_row


def device_info(mac):
    info = run("bluetoothctl", "info", mac, timeout=5)
    field = lambda name: (re.search(rf"^\s*{name}: (.*)$", info, re.M) or [None, ""])[1]
    return {
        "connected": field("Connected") == "yes",
        "paired": field("Paired") == "yes",
        "trusted": field("Trusted") == "yes",
        "icon": field("Icon"),
        "battery": (re.search(r"\((\d+)\)", field("Battery Percentage")) or [None, ""])[1],
    }


class BluetoothPage(Page):
    name = "bluetooth"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        self.busy = False
        self.powered = None
        self.known = {}  # mac: info

        self.toggle = Toggle(self.set_power)
        self.discoverable = Toggle(lambda on: self.run_steps("", [("discoverable", "on" if on else "off")]))
        self.add(row("bluetooth", self.toggle),
                 row("discoverable", self.discoverable, sub=label("other devices can find this mac", "dim")))
        self.adapter_rows = {}
        for key in ("name", "address"):
            line, value = value_row(key)
            self.adapter_rows[key] = value
            self.add(line)

        self.section("my devices")
        self.devices = ItemList(self.pick, empty="no paired devices", extra=self._device_buttons)
        self.add(self.devices)
        self.scan_button = button("scan", self.scan)
        self.section("other devices", self.scan_button)
        self.others = ItemList(self.pick, empty="scan to find devices")
        self.status = label("", "dim", "row", ellipsize=True)
        self.add(self.others, self.status)

    def refresh(self):
        if not self.busy:
            in_background(self._read, self._update)

    @staticmethod
    def _read():
        show = run("bluetoothctl", "show", timeout=5)
        powered = "Powered: yes" in show
        adapter = {"name": (re.search(r"Alias: (.*)", show) or [None, ""])[1],
                   "address": (re.search(r"Controller (\S+)", show) or [None, ""])[1],
                   "discoverable": "Discoverable: yes" in show}
        devices = []
        for line in run("bluetoothctl", "devices", timeout=5).splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3 or parts[0] != "Device":
                continue
            info = device_info(parts[1])
            # scans turn up lots of nameless devices, only show those if they're paired
            if info["paired"] or parts[2].replace("-", ":") != parts[1]:
                devices.append((parts[1], parts[2], info))
        return powered, adapter, devices

    def _update(self, result):
        if isinstance(result, Exception):
            self.status.set_label(str(result))
            return
        powered, adapter, devices = result
        if powered != self.powered:
            self.powered = powered
            self.devices.items = self.others.items = None
        self.toggle.set_active(powered)
        self.discoverable.set_active(adapter["discoverable"])
        self.discoverable.set_sensitive(powered)
        self.scan_button.set_sensitive(powered)
        for key, value in self.adapter_rows.items():
            value.set_label(adapter[key])
        self.known = {mac: info for mac, _name, info in devices}
        paired = sorted((d for d in devices if d[2]["paired"]), key=lambda d: (not d[2]["connected"], d[1].lower()))
        others = sorted((d for d in devices if not d[2]["paired"]), key=lambda d: d[1].lower())

        def detail(info):
            parts = []
            if info["battery"]:
                parts.append(f"{info['battery']}%")
            parts.append("connected" if info["connected"] else "not connected")
            return "  ".join(parts)

        self.devices.empty = "no paired devices" if powered else "bluetooth is off (paired devices still listed)"
        self.devices.set_items((mac, name, detail(info), info["connected"]) for mac, name, info in paired)
        self.others.empty = "scan to find devices" if powered else "bluetooth is off"
        self.others.set_items((mac, name, "", False) for mac, name, info in others)

    def _device_buttons(self, mac):
        info = self.known.get(mac, {})
        auto = Toggle(lambda on: self.run_steps("", [("trust" if on else "untrust", mac)]))
        auto.set_active(info.get("trusted"))
        auto.set_tooltip_text("connect automatically when it's nearby")
        return [label("auto", "dim"), auto, button("forget", lambda: self.forget(mac), "danger")]

    def run_steps(self, message, steps):
        """Run bluetoothctl commands in order on a thread, stopping at the first failure."""
        self.busy = True
        if message:
            self.status.set_label(message)

        def work():
            for step in steps:
                ok, output = step() if callable(step) else run_ok("bluetoothctl", *step, timeout=30)
                if not ok:
                    return False, output
            return True, ""

        def done(result):
            ok, output = result if not isinstance(result, Exception) else (False, str(result))
            self.busy = False
            self.status.set_label("" if ok else f"failed: {output.lower()}")
            self.devices.items = None  # rebuild so the switches show the new state
            self.refresh()

        in_background(work, done)

    def set_power(self, on):
        def power_on():
            # bluez can take a moment to notice the adapter after the rfkill unblock
            run("rfkill", "unblock", "bluetooth")
            ok, output = False, ""
            for _ in range(10):
                ok, output = run_ok("bluetoothctl", "power", "on", timeout=5)
                if ok:
                    break
                time.sleep(0.5)
            return ok, output

        self.run_steps("turning on..." if on else "turning off...", [power_on] if on else [("power", "off")])

    def scan(self):
        self.run_steps("scanning for 10 seconds...",
                       [lambda: (run_ok("bluetoothctl", "--timeout", "10", "scan", "on", timeout=20), (True, ""))[1]])

    def pick(self, mac):
        info = self.known.get(mac, {})
        if info.get("connected"):
            self.run_steps("disconnecting...", [("disconnect", mac)])
        elif info.get("paired"):
            self.run_steps("connecting...", [("connect", mac)])
        else:
            self.run_steps("pairing...", [("pair", mac), ("trust", mac), ("connect", mac)])

    def forget(self, mac):
        confirm(self.panel, "forget device", "Remove this device? It will need to be paired again.", "forget",
                lambda: self.run_steps("removing...", [("remove", mac)]))
