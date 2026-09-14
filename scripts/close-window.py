#!/usr/bin/env python3
"""Close overlay popups before letting Super+W close the focused Sway window."""
import subprocess

from gi.repository import Gio, GLib

POPUPS = ("dev.dotfiles.WallpaperPicker", "dev.dotfiles.SettingsPanel")


def main():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    names = bus.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "ListNames", None, GLib.VariantType.new("(as)"),
        Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    popups = [name for name in POPUPS if name in names]
    for name in popups:
        # Never fall through to Sway if a popup exits during this request.
        bus.call_sync(
            name, "/" + name.replace(".", "/"), "org.gtk.Actions", "Activate",
            GLib.Variant("(sava{sv})", ("quit", [], {})), None,
            Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
    if not popups:
        subprocess.run(["swaymsg", "kill"], check=True)


if __name__ == "__main__":
    main()
