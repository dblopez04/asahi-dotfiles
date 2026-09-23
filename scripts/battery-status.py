#!/usr/bin/env python3
"""Waybar battery. The percentage shows next to the icon unless it's turned off with a right click."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path('/sys/class/power_supply')
# kept across reboots, so turning the percentage off sticks
STATE = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'waybar-battery-percentage'
DISCHARGING = ['󰁺', '󰁻', '󰁼', '󰁽', '󰁾', '󰁿', '󰂀', '󰂁', '󰂂', '󰁹']
CHARGING = ['󰢜', '󰂆', '󰂇', '󰂈', '󰢝', '󰂉', '󰢞', '󰂊', '󰂋', '󰂅']


def read(path, key, default=''):
    try:
        return (path / key).read_text().strip()
    except OSError:
        return default


def amount(path, key):
    try:
        return float(read(path, key, '0'))
    except ValueError:
        return 0


def visible():
    try:
        return STATE.read_text().strip() != '0'
    except OSError:
        return True


def toggle():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.open('a+') as state:
        fcntl.flock(state, fcntl.LOCK_EX)
        state.seek(0)
        value = state.read().strip() == '0'
        state.seek(0)
        state.truncate()
        state.write('1' if value else '0')
        state.flush()
    subprocess.run(['pkill', f'-{signal.SIGRTMIN + 13}', '-x', 'waybar'], capture_output=True)


def status():
    batteries = [p for p in ROOT.iterdir() if read(p, 'type') == 'Battery'
                 and read(p, 'scope') != 'Device']
    if not batteries:
        return {'text': '', 'tooltip': 'no battery'}
    capacity = round(sum(amount(p, 'capacity') for p in batteries) / len(batteries))
    capacity = max(0, min(100, capacity))
    states = [read(p, 'status') for p in batteries]
    charging = 'Charging' in states
    full = all(s == 'Full' for s in states)
    plugged = not charging and 'Discharging' not in states and any(
        read(p, 'online') == '1' for p in ROOT.iterdir())
    icon = '󰂅' if full else '' if plugged else (CHARGING if charging else DISCHARGING)[min(9, capacity // 10)]
    power = sum(abs(amount(p, 'power_now')) for p in batteries) / 1e6
    energy = sum(amount(p, 'energy_now') for p in batteries) / 1e6
    maximum = sum(amount(p, 'energy_full') for p in batteries) / 1e6
    tooltip = f'{capacity}% · {power:.1f} W'
    hours = ((maximum - energy) if charging else energy) / power if power else 0
    if hours > 0 and not (full or plugged):
        minutes = round(hours * 60)
        tooltip += f" · {minutes // 60}h {minutes % 60}m {'until full' if charging else 'left'}"
    classes = ['charging' if charging else 'full' if full else 'plugged' if plugged else 'discharging']
    if capacity <= 10 and not charging:
        classes.append('critical')
    elif capacity <= 20:
        classes.append('warning')
    return {'text': f'{icon} {capacity}%' if visible() else icon, 'tooltip': tooltip, 'class': classes,
            'percentage': capacity}


if __name__ == '__main__':
    if sys.argv[1:] == ['toggle']:
        toggle()
    else:
        print(json.dumps(status()))
