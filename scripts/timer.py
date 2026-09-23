#!/usr/bin/env python3
"""Timers and reminders, shown in the bar and set from Spotlight ("timer 25m", "remind me at 5pm to call mom").

Usage: timer.py add SECONDS [LABEL...]        a countdown
       timer.py at UNIX_TIME MESSAGE...        a reminder at a time
       timer.py cancel ID|all
       timer.py menu                           pick a running timer to cancel (the bar's click)
       timer.py bar                            waybar module output
       timer.py resume                         restart the waiters after logging in (sway runs this)
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta

STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "timers.json")
UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60, "minute": 60,
         "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save(timers):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(timers, f)
    os.replace(tmp, STATE)


def refresh_bar():
    subprocess.run(["pkill", "-RTMIN+15", "-x", "waybar"], capture_output=True)


def spawn_waiter(timer_id):
    subprocess.Popen([sys.executable, os.path.realpath(__file__), "wait", timer_id], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def add(end, label, kind):
    timer = {"id": uuid.uuid4().hex[:8], "end": end, "label": label, "kind": kind, "start": time.time()}
    timers = load()
    timers.append(timer)
    save(timers)
    spawn_waiter(timer["id"])
    refresh_bar()
    return timer


def left(seconds):
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def wait(timer_id):
    while True:
        timer = next((t for t in load() if t["id"] == timer_id), None)
        if timer is None:
            return  # cancelled
        remaining = timer["end"] - time.time()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 20))
    save([t for t in load() if t["id"] != timer_id])
    refresh_bar()
    if timer["kind"] == "reminder":
        title, body = "Reminder", timer["label"] or "reminder"
    else:
        title = "Timer done"
        body = (timer["label"] + " · " if timer["label"] else "") + left(timer["end"] - timer["start"])
    subprocess.run(["notify-send", "-a", "timer", "-u", "critical", "-i", "alarm-symbolic", title, body])
    for sound in ("/usr/share/sounds/freedesktop/stereo/complete.oga", "/usr/share/sounds/freedesktop/stereo/bell.oga"):
        if os.path.exists(sound):
            subprocess.run(["paplay", sound], capture_output=True)
            break


def describe(timer, now=None):
    now = now or time.time()
    if timer["kind"] == "reminder":
        when = datetime.fromtimestamp(timer["end"]).strftime("%-I:%M %p").lower()
        return f"{timer['label'] or 'reminder'} at {when}"
    return f"{timer['label'] or 'timer'} · {left(timer['end'] - now)} left"


def bar():
    """Continuous waybar output: the soonest timer counting down (hidden when there are none)."""
    last = None
    while True:
        timers = sorted(load(), key=lambda t: t["end"])
        now = time.time()
        if timers:
            soonest = timers[0]
            glyph = "" if soonest["kind"] == "reminder" else ""
            text = f"{glyph} {left(soonest['end'] - now)}"
            if len(timers) > 1:
                text += f" +{len(timers) - 1}"
            tooltip = "\n".join(describe(t, now) for t in timers) + "\nclick to cancel one"
            value = {"text": text, "tooltip": tooltip, "class": soonest["kind"]}
        else:
            value = {"text": "", "tooltip": "", "class": "none"}
        line = json.dumps(value)
        if line != last:
            print(line, flush=True)
            last = line
        time.sleep(1 if timers else 5)


def menu():
    timers = sorted(load(), key=lambda t: t["end"])
    if not timers:
        return
    rows = [f"cancel: {describe(t)}" for t in timers] + (["cancel all"] if len(timers) > 1 else [])
    result = subprocess.run(["fuzzel", "--dmenu", "--index", "--prompt", "timers > ", "--width", "40",
                             "--lines", str(len(rows))], input="\n".join(rows), text=True, capture_output=True)
    choice = result.stdout.strip()
    if result.returncode == 0 and choice.isdigit():
        cancel("all" if int(choice) >= len(timers) else timers[int(choice)]["id"])


def cancel(timer_id):
    save([] if timer_id == "all" else [t for t in load() if t["id"] != timer_id])
    refresh_bar()


def resume():
    now = time.time()
    for timer in load():
        spawn_waiter(timer["id"])  # overdue ones fire right away
    return now


def parse_duration(text):
    """'25m', '1h30m', '90 seconds', '1.5 hours' -> seconds, or None."""
    total, matched = 0.0, False
    for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", text.lower()):
        if unit not in UNITS:
            return None
        total += float(number) * UNITS[unit]
        matched = True
    rest = re.sub(r"(\d+(?:\.\d+)?)\s*([a-z]+)", "", text.lower()).strip(" ,and")
    return int(total) if matched and not rest else None


def parse_clock(text, now=None):
    """'5pm', '5:30 pm', '17:30', 'noon' -> the next unix time at that clock time, or None."""
    now = now or datetime.now()
    text = text.strip().lower()
    if text in ("noon", "midday"):
        hour, minute = 12, 0
    elif text == "midnight":
        hour, minute = 0, 0
    else:
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if match.group(3) == "pm" and hour < 12:
            hour += 12
        elif match.group(3) == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.timestamp()


def parse(query):
    """A Spotlight query as (kind, end time, label), or None if it isn't a timer or reminder.

    timer 25m · timer 1h30m tea · 10 min timer · remind me in 20m to stretch · remind me at 5pm to call mom
    """
    q = query.strip()
    lowered = q.lower()
    match = re.match(r"^remind(?: me)?\s+(in|at)\s+(.+)$", lowered)
    if match:
        words = q[match.start(2):].split()
        # the time is the longest leading run of words that parses; the rest (minus "to") is the message
        for cut in range(len(words), 0, -1):
            when = " ".join(words[:cut]).lower()
            end = (time.time() + s if (s := parse_duration(when)) else None) if match.group(1) == "in" else parse_clock(when)
            if end:
                message = " ".join(words[cut:])
                message = re.sub(r"^(to|that|about)\s+", "", message, flags=re.I)
                return ("reminder", end, message)
        return None
    match = re.match(r"^(?:timer|countdown)\s+(.+)$", lowered) or re.match(r"^(.+?)\s+timer$", lowered)
    if match:
        words = match.group(1).split()
        # the duration is the leading words that parse; anything after is the label
        for cut in range(len(words), 0, -1):
            seconds = parse_duration(" ".join(words[:cut]))
            if seconds:
                label = " ".join(q.split()[len(q.split()) - len(match.group(1).split()) + cut:]) if cut < len(words) else ""
                return ("timer", time.time() + seconds, label)
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else "menu"
    if command == "add" and len(args) >= 2 and args[1].isdigit():
        add(time.time() + int(args[1]), " ".join(args[2:]), "timer")
    elif command == "at" and len(args) >= 2:
        add(float(args[1]), " ".join(args[2:]), "reminder")
    elif command == "wait" and len(args) == 2:
        wait(args[1])
    elif command == "cancel" and len(args) == 2:
        cancel(args[1])
    elif command in ("menu", "bar", "resume"):
        {"menu": menu, "bar": bar, "resume": resume}[command]()
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
