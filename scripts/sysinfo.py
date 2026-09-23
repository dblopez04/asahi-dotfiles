#!/usr/bin/env python3
"""Optional Waybar modules: weather, network speed, and CPU/memory (turn them on in Settings > toolbar).

Usage: sysinfo.py weather     current weather, 3-day forecast in the tooltip (wttr.in, every 20 minutes)
       sysinfo.py net         download/upload speed of the active connection
       sysinfo.py system      CPU and memory use

The weather location comes from ~/.local/state/weather-location (empty or missing = detected from your IP).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

STATE = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
LOCATION_FILE = os.path.join(STATE, "weather-location")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "waybar-weather.json")


def emit(text, tooltip="", css=""):
    print(json.dumps({"text": text, "tooltip": tooltip, "class": css}), flush=True)


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


###############
### WEATHER ###
###############

# wttr.in weather codes -> nerd font glyphs
GLYPHS = [((113,), ""), ((116,), ""), ((119, 122), ""), ((143, 248, 260), ""),
          ((176, 263, 266, 293, 296, 353), ""), ((299, 302, 305, 308, 356, 359), ""),
          ((200, 386, 389, 392, 395), ""),
          ((179, 182, 185, 227, 230, 317, 320, 323, 326, 329, 332, 335, 338, 350, 362, 365, 368, 371, 374, 377), ""),
          ((281, 284, 311, 314), "")]


def glyph(code):
    code = int(code or 0)
    return next((g for codes, g in GLYPHS if code in codes), "")


def weather():
    while True:
        location = read(LOCATION_FILE)
        try:
            url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1&u"
            request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)
            with open(CACHE, "w") as f:
                json.dump(data, f)
        except (OSError, ValueError):
            try:
                with open(CACHE) as f:
                    data = json.load(f)  # offline: keep showing the last report
            except (OSError, ValueError):
                emit("")
                time.sleep(300)
                continue
        now = data["current_condition"][0]
        area = (data.get("nearest_area") or [{}])[0]
        place = ", ".join(x[0]["value"] for x in (area.get("areaName"), area.get("region")) if x)
        lines = [f"<b>{now['weatherDesc'][0]['value'].strip().lower()}</b> · {place.lower()}",
                 f"feels like {now['FeelsLikeF']}° · humidity {now['humidity']}% · wind {now['windspeedMiles']} mph", ""]
        for day in data.get("weather", [])[:3]:
            label = time.strftime("%a", time.strptime(day["date"], "%Y-%m-%d")).lower()
            midday = day["hourly"][len(day["hourly"]) // 2]
            lines.append(f"{label}  {glyph(midday['weatherCode'])}  {day['mintempF']}° – {day['maxtempF']}°  "
                         f"{midday['weatherDesc'][0]['value'].strip().lower()}")
        emit(f"{glyph(now['weatherCode'])} {now['temp_F']}°", "\n".join(lines), "weather")
        time.sleep(1200)


###############
### NETWORK ###
###############

def default_interface():
    for line in read("/proc/net/route").splitlines()[1:]:
        fields = line.split()
        if len(fields) > 1 and fields[1] == "00000000":
            return fields[0]
    return None


def counters(interface):
    for line in read("/proc/net/dev").splitlines()[2:]:
        name, _, data = line.partition(":")
        if name.strip() == interface:
            fields = data.split()
            return int(fields[0]), int(fields[8])
    return None


def rate(bytes_per_second):
    for unit, size in (("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if bytes_per_second >= size:
            return f"{bytes_per_second / size:.1f}{unit}"
    return f"{bytes_per_second:.0f}B"


def net(interval=2):
    last, last_time, interface = None, time.time(), None
    while True:
        interface = default_interface()
        current = counters(interface) if interface else None
        now = time.time()
        if current is None:
            emit("")
        elif last is not None:
            elapsed = max(0.1, now - last_time)
            down, up = (current[0] - last[0]) / elapsed, (current[1] - last[1]) / elapsed
            emit(f" {rate(down)}  {rate(up)}",
                 f"{interface} · received {rate(current[0])} · sent {rate(current[1])} since it connected", "net")
        last, last_time = current, now
        time.sleep(interval)


##############
### SYSTEM ###
##############

def cpu_times():
    fields = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
    idle = fields[3] + fields[4]
    return idle, sum(fields)


def system(interval=3):
    last = cpu_times()
    while True:
        time.sleep(interval)
        current = cpu_times()
        idle, total = current[0] - last[0], current[1] - last[1]
        last = current
        cpu = 100 * (1 - idle / total) if total else 0
        mem = {k: int(v.split()[0]) for k, v in (l.split(":", 1) for l in read("/proc/meminfo").splitlines() if ":" in l)}
        used = (mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) / 2**20
        load = " ".join(read("/proc/loadavg").split()[:3])
        emit(f" {cpu:.0f}%   {used:.1f}G",
             f"cpu {cpu:.0f}% · load {load}\nmemory {used:.1f} of {mem.get('MemTotal', 0) / 2**20:.1f} gb\nclick for btop",
             "busy" if cpu > 80 else "system")


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # exit quietly when waybar goes away
    modes = {"weather": weather, "net": net, "system": system}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    try:
        modes[sys.argv[1]]()
    except KeyboardInterrupt:
        pass
