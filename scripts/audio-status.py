#!/usr/bin/env python3
"""Waybar output volume and mute tooltip, refreshed by PulseAudio events."""
import json
import os
import subprocess


def status():
    default = subprocess.check_output(["pactl", "get-default-sink"], text=True).strip()
    sinks = json.loads(subprocess.check_output(["pactl", "-f", "json", "list", "sinks"], text=True))
    sink = next((sink for sink in sinks if sink["name"] == default), None)
    if sink is None:
        return {"text": "", "tooltip": "no audio output", "class": "disconnected"}
    channels = list(sink["volume"].values())
    volume = round(sum(channel["value"] for channel in channels) / len(channels) * 100 / 65536)
    if sink["mute"]:
        return {"text": "", "tooltip": "muted", "class": "muted"}
    port = sink.get("active_port", "")
    icon = "" if any(word in port for word in ("headphone", "headset")) else ("", "", "")[min(volume // 34, 2)]
    return {"text": icon, "tooltip": f"playing at {volume}%"}


def emit():
    try:
        value = status()
    except (subprocess.CalledProcessError, ValueError, KeyError, ZeroDivisionError):
        value = {"text": "", "tooltip": "audio unavailable", "class": "disconnected"}
    print(json.dumps(value), flush=True)


def main():
    with subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True,
                          env={**os.environ, "LC_ALL": "C"}) as events:
        emit()
        for event in events.stdout:
            if " on sink #" in event or " on server #" in event:
                emit()


if __name__ == "__main__":
    main()
