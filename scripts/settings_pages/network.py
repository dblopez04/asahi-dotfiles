import re

from gi.repository import GLib, Gtk

from .common import (ItemList, Page, Toggle, button, confirm, in_background, label, row, run, run_ok,
                     value_row)


def nmcli_fields(line):
    """Split a line of `nmcli -t` output on its unescaped colons."""
    return [field.replace("\\:", ":").replace("\\\\", "\\") for field in re.split(r"(?<!\\):", line)]


def device_details(device):
    """{field: value} from `nmcli dev show`, with repeated fields (IP4.ADDRESS[1]...) joined."""
    details = {}
    for line in run("nmcli", "-t", "dev", "show", device).splitlines():
        key, _, value = line.partition(":")
        key = re.sub(r"\[\d+\]$", "", key)
        if value and value != "--":
            details[key] = f"{details[key]}, {value}" if key in details else value
    return details


class WifiPage(Page):
    name = "wi-fi"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        self.active_ssid = None
        self.device = None
        self.saved = {}  # ssid: (connection name, autoconnect)
        self.security = {}
        self.pending_ssid = None
        self.busy = False

        self.toggle = Toggle(self.set_radio)
        self.connection = label("", "dim", ellipsize=True)
        self.disconnect = button("disconnect", self.disconnect_current)
        self.add(row("wi-fi", self.toggle), row("network", self.disconnect, sub=self.connection))

        self.section("networks", button("scan", lambda: self.refresh(rescan=True)),
                     button("hidden network", self.show_hidden))
        self.networks = ItemList(self.pick, empty="no networks found")
        self.password_label = label("", "title", ellipsize=True)
        self.hidden_ssid = Gtk.Entry(placeholder_text="network name", hexpand=True, visible=False)
        # for enterprise (802.1X) networks like eduroam
        self.username = Gtk.Entry(placeholder_text="username", hexpand=True, visible=False)
        self.password = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True, placeholder_text="password")
        self.password.connect("activate", lambda _: self.submit_password())
        self.username.connect("activate", lambda _: self.password.grab_focus())
        self.hidden_ssid.connect("activate", lambda _: (self.username if self.username.get_visible()
                                                        else self.password).grab_focus())
        self.password_row = Gtk.Box(spacing=12, css_classes=["row"], visible=False)
        for widget in (self.password_label, self.hidden_ssid, self.username, self.password,
                       button("join", self.submit_password)):
            self.password_row.append(widget)
        self.status = label("", "dim", "row", ellipsize=True)
        self.add(self.networks, self.password_row, self.status)

        self.section("connection details")
        self.details = {}
        for key in ("ip address", "ipv6", "router", "dns", "security", "channel", "speed", "signal", "mac address"):
            line, value = value_row(key)
            self.details[key] = (line, value)
            self.add(line)

        self.section("saved networks")
        self.saved_list = ItemList(lambda _k: None, empty="no saved networks", extra=self._saved_buttons)
        self.add(self.saved_list)

    # ----- reading -----

    def refresh(self, rescan=False):
        if self.busy:
            return
        self.busy = True
        if rescan:
            self.status.set_label("scanning...")

        def work():
            radio = run("nmcli", "radio", "wifi").strip() == "enabled"
            devices = [nmcli_fields(l) for l in run("nmcli", "-t", "-f", "DEVICE,TYPE", "dev").splitlines()]
            device = next((d[0] for d in devices if len(d) == 2 and d[1] == "wifi"), None)
            networks = run("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,CHAN,FREQ,RATE", "dev", "wifi", "list",
                           "--rescan", "yes" if rescan else "no", timeout=30).splitlines()
            saved = {}
            for line in run("nmcli", "-t", "-f", "NAME,TYPE,AUTOCONNECT,TIMESTAMP-REAL", "con", "show").splitlines():
                fields = nmcli_fields(line)
                if len(fields) >= 3 and fields[1] == "802-11-wireless":
                    ssid = run("nmcli", "-g", "802-11-wireless.ssid", "con", "show", fields[0]).strip() or fields[0]
                    saved[ssid] = (fields[0], fields[2] == "yes", fields[3] if len(fields) > 3 else "")
            details = device_details(device) if device else {}
            return radio, device, networks, saved, details

        in_background(work, self._update)

    def _update(self, result):
        self.busy = False
        if isinstance(result, Exception):
            self.status.set_label(f"nmcli: {result}")
            return
        radio, self.device, lines, self.saved, details = result
        networks = {}  # ssid: [in use, signal, security, channel, freq, rate]
        for line in lines:
            in_use, ssid, signal, security, chan, freq, rate = (nmcli_fields(line) + [""] * 7)[:7]
            if not ssid:
                continue
            old = networks.get(ssid)
            if old is None or in_use == "*" or int(signal or 0) > old[1]:
                networks[ssid] = [in_use == "*" or (old and old[0]), int(signal or 0), security, chan, freq, rate]
        self.security = {ssid: n[2] for ssid, n in networks.items()}
        self.active_ssid = next((ssid for ssid, n in networks.items() if n[0]), None)

        self.toggle.set_active(radio)
        if not radio:
            self.connection.set_label("wi-fi is off")
        else:
            self.connection.set_label(f"connected to {self.active_ssid}" if self.active_ssid else "not connected")
        self.disconnect.set_visible(self.active_ssid is not None)
        self.networks.empty = "no networks found" if radio else "wi-fi is off"
        ordered = sorted(networks.items(), key=lambda kv: (not kv[1][0], -kv[1][1]))[:20] if radio else []
        self.networks.set_items(
            (ssid, ssid, f"{'saved  ' if ssid in self.saved else ''}{(n[2] or 'open').lower()}  {n[1]:>3}%", n[0])
            for ssid, n in ordered)
        if self.status.get_label() == "scanning...":
            self.status.set_label("")

        active = networks.get(self.active_ssid)
        values = {
            "ip address": details.get("IP4.ADDRESS", ""),
            "ipv6": ", ".join(a for a in details.get("IP6.ADDRESS", "").split(", ") if not a.startswith("fe80")),
            "router": details.get("IP4.GATEWAY", ""),
            "dns": details.get("IP4.DNS", ""),
            "security": (active[2] or "open") if active else "",
            "channel": f"{active[3]} ({active[4]})" if active else "",
            "speed": active[5] if active else "",
            "signal": f"{active[1]}%" if active else "",
            "mac address": details.get("GENERAL.HWADDR", ""),
        }
        for key, (line, value) in self.details.items():
            value.set_label(values[key].lower() if key == "security" else values[key])
            line.set_visible(bool(values[key]) and self.active_ssid is not None)

        self.saved_list.set_items((ssid, ssid, "auto-join" if auto else "", ssid == self.active_ssid)
                                  for ssid, (_name, auto, _when) in sorted(self.saved.items(), key=lambda kv: kv[0].lower()))

    def _saved_buttons(self, ssid):
        name, auto, _when = self.saved.get(ssid, (ssid, True, ""))
        toggle = Toggle(lambda on, name=name: self.set_autoconnect(name, on))
        toggle.set_active(auto)
        toggle.set_tooltip_text("join automatically")
        return [toggle, button("forget", lambda: self.forget(ssid, name), "danger")]

    # ----- actions -----

    def set_radio(self, on):
        self.busy = True
        in_background(lambda: run("nmcli", "radio", "wifi", "on" if on else "off"),
                      lambda _: GLib.timeout_add(1000, self._after_action))

    def _after_action(self):
        self.busy = False
        self.refresh()
        return False

    def disconnect_current(self):
        if self.device:
            in_background(lambda: run("nmcli", "dev", "disconnect", self.device), lambda _: self._after_action())

    def set_autoconnect(self, name, on):
        in_background(lambda: run_ok("nmcli", "con", "modify", name, "connection.autoconnect", "yes" if on else "no"),
                      lambda r: (self.status.set_label("" if r[0] else f"failed: {r[1].lower()}"), self.refresh()))

    def forget(self, ssid, name):
        confirm(self.panel, "forget network", f"Forget {ssid} and its password?", "forget",
                lambda: in_background(lambda: run_ok("nmcli", "con", "delete", "id", name),
                                      lambda r: (self.status.set_label(f"forgot {ssid}" if r[0] else f"failed: {r[1].lower()}"),
                                                 self._after_action())))

    def pick(self, ssid):
        if ssid == self.active_ssid:
            return
        if ssid in self.saved or not self.security.get(ssid):
            self.connect_to(ssid)
            return
        self.ask_password(ssid)

    def ask_password(self, ssid, hidden=False):
        self.pending_ssid = ssid
        self.password_label.set_label(ssid or "")
        self.password_label.set_visible(not hidden)
        self.hidden_ssid.set_visible(hidden)
        self.hidden_ssid.set_text("")
        # a hidden network's security isn't known, so the username is optional there
        self.username.set_visible(hidden or "802.1X" in self.security.get(ssid, ""))
        self.username.set_placeholder_text("username (if it needs one)" if hidden else "username")
        self.username.set_text("")
        self.password.set_text("")
        self.password_row.set_visible(True)
        (self.hidden_ssid if hidden else self.username if self.username.get_visible() else self.password).grab_focus()

    def show_hidden(self):
        self.ask_password(None, hidden=True)

    def submit_password(self):
        hidden = self.hidden_ssid.get_visible()
        ssid = self.hidden_ssid.get_text().strip() if hidden else self.pending_ssid
        username = self.username.get_text().strip() if self.username.get_visible() else ""
        if ssid:
            self.connect_to(ssid, self.password.get_text() or None, hidden=hidden, username=username or None)

    def connect_to(self, ssid, password=None, hidden=False, username=None):
        self.hide_password()
        self.status.set_label(f"connecting to {ssid}...")
        self.busy = True
        saved = self.saved.get(ssid)
        device = self.device

        def work():
            if password is None and username is None and saved and not hidden:
                return run_ok("nmcli", "con", "up", "id", saved[0], timeout=60)
            if username:
                # enterprise: PEAP with MSCHAPv2, what eduroam and most work/school networks use
                # (other EAP setups, like certificates or TTLS, can be made in nmtui)
                cmd = ["nmcli", "con", "add", "type", "wifi", "con-name", ssid, "ssid", ssid,
                       "wifi-sec.key-mgmt", "wpa-eap", "802-1x.eap", "peap", "802-1x.phase2-auth", "mschapv2",
                       "802-1x.identity", username, "802-1x.password", password or ""]
                if device:
                    cmd += ["ifname", device]
                if hidden:
                    cmd += ["802-11-wireless.hidden", "yes"]
                ok, message = run_ok(*cmd)
                if ok:
                    ok, message = run_ok("nmcli", "con", "up", "id", ssid, timeout=60)
            else:
                cmd = ["nmcli", "dev", "wifi", "connect", ssid]
                if password:
                    cmd += ["password", password]
                if hidden:
                    cmd += ["hidden", "yes"]
                ok, message = run_ok(*cmd, timeout=60)
            if not ok and not saved:
                run("nmcli", "con", "delete", "id", ssid)  # don't keep a profile with a wrong password
            return ok, message

        def done(result):
            ok, message = result if not isinstance(result, Exception) else (False, str(result))
            self.status.set_label(f"connected to {ssid}" if ok else f"failed: {message.lower()}")
            self._after_action()

        in_background(work, done)

    def hide_password(self):
        if self.password_row.get_visible():
            self.password_row.set_visible(False)
            if item := self.networks.buttons.get(self.pending_ssid):
                item.grab_focus()

    def escape(self, focus):
        if self.password_row.get_visible() and focus and focus.is_ancestor(self.password_row):
            self.hide_password()
            return True
        return False
