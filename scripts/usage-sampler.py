#!/usr/bin/env python3
"""Records battery, screen and per-app CPU use once a minute for the settings panel's battery page.

Runs as the usage-sampler systemd user service. Each sample is one JSON line in
~/.local/state/usage/YYYY-MM-DD.jsonl; files older than 14 days are removed. It reads a handful of
files in /proc and /sys per minute and sleeps otherwise.

Sample: {"t": unix time, "level": percent, "watts": draw (negative while charging),
         "charging": bool, "screen": bool, "apps": {name: share of the minute's cpu time}}
"""
import json
import os
import re
import subprocess
import threading
import time

STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "usage")
SUPPLIES = "/sys/class/power_supply"
INTERVAL = 60
KEEP_DAYS = 14
TICKS = os.sysconf("SC_CLK_TCK")


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def battery_path():
    try:
        names = sorted(os.listdir(SUPPLIES))
    except OSError:
        return None
    return next((os.path.join(SUPPLIES, n) for n in names if read(os.path.join(SUPPLIES, n, "type")) == "Battery"), None)


def screen_on():
    """The panel counts as on unless sway powered it off (idle) or the backlight is at 0."""
    try:
        outputs = json.loads(subprocess.run(["swaymsg", "-r", "-t", "get_outputs"], capture_output=True,
                                            text=True, timeout=3).stdout or "[]")
        if outputs and not any(o.get("power", o.get("dpms", True)) for o in outputs):
            return False
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    for name in os.listdir("/sys/class/backlight") if os.path.isdir("/sys/class/backlight") else []:
        if read(f"/sys/class/backlight/{name}/bl_power", "0") not in ("0", "") or read(f"/sys/class/backlight/{name}/brightness", "1") == "0":
            return False
    return True


def cpu_times():
    """{app name: total cpu ticks} over all processes, grouped by command name."""
    totals = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        stat = read(f"/proc/{pid}/stat")
        if not stat:
            continue
        # comm can contain spaces and parentheses: it's everything between the first ( and the last )
        name = stat[stat.find("(") + 1:stat.rfind(")")]
        fields = stat[stat.rfind(")") + 2:].split()
        try:
            ticks = int(fields[11]) + int(fields[12])  # utime + stime
        except (IndexError, ValueError):
            continue
        key = (pid, name)
        totals[key] = ticks
    return totals


def app_name(name):
    """Fold helper processes into the app people know."""
    lowered = name.lower()
    if re.fullmatch(r"\d+(\.\d+)+", lowered):
        return "claude code"  # its binary is named after its version
    for prefix, app in (("firefox", "firefox"), ("isolated web", "firefox"), ("web content", "firefox"),
                        ("socket process", "firefox"), ("code", "vs code"), ("electron", "electron apps"),
                        ("vesktop", "vesktop"), ("kitty", "kitty"), ("python", "python"), ("node", "node"),
                        ("claude", "claude"), ("waybar", "waybar"), ("sway", "sway"), ("pipewire", "audio"),
                        ("wireplumber", "audio"), ("gnome-shell", "gnome")):
        if lowered.startswith(prefix):
            return app
    return lowered


WARNINGS = [(20, "normal"), (10, "critical"), (5, "critical")]
warned = set()


def warn_low_battery(level, charging, seconds_left):
    """A notification when the battery drops to 20%, 10% and 5%. Plugging in resets them."""
    if charging:
        warned.clear()
        return
    for threshold, urgency in WARNINGS:
        if level <= threshold and threshold not in warned:
            warned.update(t for t, _u in WARNINGS if t >= threshold)  # don't also send the higher ones
            left = f" · about {seconds_left // 3600}h {seconds_left // 60 % 60}m left" if seconds_left else ""
            body = f"{level}% remaining{left}" + (" · plug in soon" if threshold <= 10 else "")

            def notify():
                # -A waits for a click; the action opens the battery page
                try:
                    chosen = subprocess.run(
                        ["notify-send", "-a", "battery", "-u", urgency, "-i", "battery-caution",
                         "-A", "settings=battery settings", "Low battery", body],
                        capture_output=True, text=True, timeout=3600).stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    return
                if chosen == "settings":
                    subprocess.Popen([os.path.expanduser("~/.local/bin/settings-panel.py"), "battery"],
                                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            threading.Thread(target=notify, daemon=True).start()
            break


def main():
    os.makedirs(STATE, exist_ok=True)
    battery = battery_path()
    previous = cpu_times()
    while True:
        time.sleep(INTERVAL)
        current = cpu_times()
        usage = {}
        for key, ticks in current.items():
            delta = ticks - previous.get(key, ticks if key not in previous else 0)
            if key not in previous:
                delta = 0  # started this minute; count it next time
            if delta > 0:
                name = app_name(key[1])
                usage[name] = usage.get(name, 0) + delta
        previous = current
        total = sum(usage.values()) or 1
        apps = {name: round(ticks / total, 3) for name, ticks in sorted(usage.items(), key=lambda kv: -kv[1])[:8]
                if ticks / total >= 0.01}

        sample = {"t": int(time.time()), "screen": screen_on(), "apps": apps,
                  "cpu": round(sum(usage.values()) / TICKS / INTERVAL, 3)}
        if battery:
            status = read(f"{battery}/status").lower()
            power = int(read(f"{battery}/power_now", "0") or 0) / 1e6
            level = int(read(f"{battery}/capacity", "0") or 0)
            charging = status in ("charging", "full", "not charging")
            sample.update(level=level, watts=round(power, 2), charging=charging)
            warn_low_battery(level, charging, int(read(f"{battery}/time_to_empty_now", "0") or 0))
        path = os.path.join(STATE, time.strftime("%Y-%m-%d") + ".jsonl")
        try:
            with open(path, "a") as f:
                f.write(json.dumps(sample, separators=(",", ":")) + "\n")
        except OSError:
            pass

        cutoff = time.time() - KEEP_DAYS * 86400
        for name in os.listdir(STATE):
            full = os.path.join(STATE, name)
            try:
                if name.endswith(".jsonl") and os.path.getmtime(full) < cutoff:
                    os.remove(full)
            except OSError:
                pass


if __name__ == "__main__":
    main()
