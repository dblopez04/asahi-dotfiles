#!/usr/bin/env python3
"""Waybar's tray arrow: shown only while some app has a tray icon.

Waybar hides a custom module with empty text, which also hides the tray drawer behind it.
Updates on the tray watcher's D-Bus signals, with a slow poll as a fallback.
"""
import ctypes
import json
import select
import signal
import subprocess

WATCHER = ["--session", "--dest", "org.kde.StatusNotifierWatcher", "--object-path", "/StatusNotifierWatcher"]


def item_count():
    try:
        output = subprocess.run(["gdbus", "call", *WATCHER, "--method", "org.freedesktop.DBus.Properties.Get",
                                 "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems"],
                                capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return output.count("'")  // 2  # (<['item1', 'item2']>,)


def emit(count):
    text = "" if count else ""
    print(json.dumps({"text": text, "tooltip": f"{count} tray item{'' if count == 1 else 's'}"}), flush=True)


def die_with_parent():
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def main():
    monitor = subprocess.Popen(["gdbus", "monitor", *WATCHER], stdout=subprocess.PIPE, text=True,
                               preexec_fn=die_with_parent)
    last = None
    try:
        while True:
            count = item_count()
            if count != last:
                emit(count)
                last = count
            ready, _, _ = select.select([monitor.stdout], [], [], 30)
            if ready and not monitor.stdout.readline():
                break  # the monitor exited; waybar's restart-interval starts us again
    finally:
        monitor.kill()


if __name__ == "__main__":
    main()
