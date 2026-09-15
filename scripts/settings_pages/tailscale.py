import os

from gi.repository import Gdk, Gtk

from .common import (Choice, ItemList, Page, Toggle, button, in_background, label, row, run_json, run_ok,
                     value_row)

# (flag for `tailscale set`, pref key in `tailscale debug prefs`, title, subtitle)
SWITCHES = [
    ("accept-routes", "RouteAll", "use subnet routes", "reach networks other devices share"),
    ("accept-dns", "CorpDNS", "use tailscale dns", "magicdns names and your tailnet's dns settings"),
    ("shields-up", "ShieldsUp", "shields up", "block incoming connections"),
    ("ssh", "RunSSH", "tailscale ssh", "let tailnet devices ssh in"),
    ("advertise-exit-node", None, "offer to be an exit node", "route other devices' internet through this mac"),
    ("exit-node-allow-lan-access", "ExitNodeAllowLANAccess", "local network with an exit node", "keep lan access"),
    ("webclient", "RunWebClient", "web interface", "serve the device web ui on port 5252"),
]


class TailscalePage(Page):
    name = "tailscale"
    interval = 5

    def __init__(self, panel):
        super().__init__(panel)
        self.busy = False
        self.prefs = {}
        self.status_data = {}

        self.toggle = Toggle(self.set_up)
        self.state = label("", "dim")
        self.add(row("tailscale", self.toggle, sub=self.state))
        self.operator_row = row("permission", button("allow changes without sudo", self.set_operator),
                                sub=label("tailscale only lets its operator change settings", "dim"))
        self.add(self.operator_row)

        self.section("this device")
        self.info = {}
        for key in ("name", "tailscale ip", "ipv6", "tailnet", "account", "version"):
            line, self.info[key] = value_row(key)
            self.add(line)

        self.section("devices")
        self.devices = ItemList(self.copy_ip, empty="not connected")
        self.add(self.devices, label("click a device to copy its ip", "dim", "row"))

        self.section("settings")
        self.switches = {}
        for flag, pref, title, sub in SWITCHES:
            toggle = Toggle(lambda on, flag=flag: self.set_flag(flag, "true" if on else "false"))
            self.switches[flag] = (toggle, pref)
            self.add(row(title, toggle, sub=label(sub, "dim")))
        self.exit_node = Choice([("", "none")], lambda v: self.set_flag("exit-node", v))
        self.add(row("exit node", self.exit_node, sub=label("send internet traffic through another device", "dim")))
        self.hostname = Gtk.Entry(placeholder_text="machine name", width_chars=18)
        self.hostname.connect("activate", lambda e: self.set_flag("hostname", e.get_text().strip()))
        self.add(row("machine name", self.hostname, button("set", lambda: self.set_flag("hostname", self.hostname.get_text().strip()))))
        self.message = label("", "dim", "row", wrap=True)
        self.add(self.message)

    def refresh(self):
        if self.busy:
            return
        in_background(lambda: (run_json("tailscale", "status", "--json", default={}),
                               run_json("tailscale", "debug", "prefs", default={})), self._update)

    def _update(self, result):
        if isinstance(result, Exception):
            return
        status, prefs = result
        self.status_data, self.prefs = status, prefs
        backend = status.get("BackendState", "NoState")
        running = backend == "Running"
        self.toggle.set_active(running)
        self.state.set_label({"Running": "connected", "Stopped": "off", "NeedsLogin": "needs login: run sudo tailscale up",
                              "NoState": "tailscaled isn't running"}.get(backend, backend.lower()))
        operator = prefs.get("OperatorUser")
        self.operator_row.set_visible(operator != os.environ.get("USER"))

        me = status.get("Self") or {}
        user = (status.get("User") or {}).get(str(me.get("UserID")), {})
        ips = status.get("TailscaleIPs") or me.get("TailscaleIPs") or []
        values = {
            "name": me.get("HostName", ""),
            "tailscale ip": next((ip for ip in ips if "." in ip), ""),
            "ipv6": next((ip for ip in ips if ":" in ip), ""),
            "tailnet": (status.get("CurrentTailnet") or {}).get("Name", ""),
            "account": user.get("LoginName", ""),
            "version": status.get("Version", "").split("-")[0],
        }
        for key, widget in self.info.items():
            widget.set_label(values[key])

        peers = sorted((status.get("Peer") or {}).values(), key=lambda p: (not p.get("Online"), p.get("HostName", "").lower()))
        self.devices.empty = "no other devices" if running else "not connected"
        self.devices.set_items((
            next((ip for ip in p.get("TailscaleIPs", []) if "." in ip), ""),
            p.get("HostName", "?") + ("  (exit node)" if p.get("ExitNode") else ""),
            f"{next((ip for ip in p.get('TailscaleIPs', []) if '.' in ip), '')}  {p.get('OS', '')}  "
            f"{'online' if p.get('Online') else 'offline'}",
            bool(p.get("Online")),
        ) for p in peers)

        for flag, (toggle, pref) in self.switches.items():
            if flag == "advertise-exit-node":
                toggle.set_active(any(r in ("0.0.0.0/0", "::/0") for r in prefs.get("AdvertiseRoutes") or []))
            elif pref:
                toggle.set_active(bool(prefs.get(pref)))
        exits = [("", "none")] + [(p.get("DNSName", "").rstrip(".") or p.get("HostName"), p.get("HostName"))
                                  for p in peers if p.get("ExitNodeOption")]
        self.exit_node.set_options(exits)
        current_exit = next((p.get("DNSName", "").rstrip(".") for p in peers if p.get("ExitNode")), "")
        self.exit_node.set_value(current_exit)
        if not self.hostname.has_focus():
            self.hostname.set_text(prefs.get("Hostname") or "")

    def run(self, message, *cmd):
        self.busy = True
        self.message.set_label(message)

        def done(result):
            self.busy = False
            ok, output = result if not isinstance(result, Exception) else (False, str(result))
            if not ok and "access denied" in output.lower():
                output = "access denied: use \"allow changes without sudo\" above first"
            self.message.set_label("" if ok else f"failed: {output.lower()}")
            self.refresh()

        in_background(lambda: run_ok(*cmd, timeout=60), done)

    def set_up(self, on):
        self.run("connecting..." if on else "disconnecting...", "tailscale", "up" if on else "down")

    def set_flag(self, flag, value):
        self.run("", "tailscale", "set", f"--{flag}={value}")

    def set_operator(self):
        # one polkit password prompt, then settings change without sudo
        self.run("waiting for permission...", "pkexec", "tailscale", "set", f"--operator={os.environ.get('USER', '')}")

    def copy_ip(self, ip):
        if ip:
            Gdk.Display.get_default().get_clipboard().set(ip)
            self.message.set_label(f"copied {ip}")
