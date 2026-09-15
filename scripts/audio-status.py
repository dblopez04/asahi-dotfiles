#!/usr/bin/env python3
"""Waybar output volume and mute tooltip, refreshed by PulseAudio events."""
import ctypes
import json
import os
import signal
import subprocess


def status():
    default = subprocess.check_output(["pactl", "get-default-sink"], text=True, timeout=5).strip()
    sinks = json.loads(subprocess.check_output(["pactl", "-f", "json", "list", "sinks"], text=True, timeout=5))
    sink = next((sink for sink in sinks if sink["name"] == default), None)
    if sink is None:
        return {"text": "", "tooltip": "no audio output", "class": "disconnected"}
    channels = list(sink["volume"].values())
    volume = round(sum(channel["value"] for channel in channels) / len(channels) * 100 / 65536)
    if sink["mute"]:
        return {"text": "", "tooltip": "muted", "class": "muted"}
    # the speakers' DSP sink (j313-convolver) has no port at all, so check the name too
    where = " ".join(str(sink.get(key) or "") for key in ("active_port", "name", "description")).lower()
    icon = "" if any(word in where for word in ("headphone", "headset")) else ("", "", "")[min(volume // 34, 2)]
    return {"text": icon, "tooltip": f"playing at {volume}%"}


def emit():
    try:
        value = status()
    except Exception:  # never die here: waybar would keep the last icon forever
        value = {"text": "", "tooltip": "audio unavailable", "class": "disconnected"}
    print(json.dumps(value), flush=True)


def die_with_parent():
    """Kill `pactl subscribe` when this script exits, so waybar restarts don't leak them."""
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def main():
    events = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True,
                              env={**os.environ, "LC_ALL": "C"}, preexec_fn=die_with_parent)
    try:
        emit()
        for event in events.stdout:
            if " on sink #" in event or " on server #" in event:
                emit()
    finally:
        events.kill()


if __name__ == "__main__":
    main()
