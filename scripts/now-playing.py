#!/usr/bin/env python3
"""Waybar's now playing: the song from any media player (Spotify, Firefox, mpv...).

Hidden while nothing is playing or paused. Click plays/pauses, right-click skips, middle-click goes back.
"""
import html
import json
import subprocess
import time

FIELDS = ["status", "playerName", "artist", "title", "album", "position", "mpris:length"]


def players():
    try:
        out = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [p for p in out.split() if p]


def metadata(player):
    fmt = "\x1f".join("{{%s}}" % f for f in FIELDS)
    try:
        out = subprocess.run(["playerctl", "-p", player, "metadata", "--format", fmt], capture_output=True,
                             text=True, timeout=3).stdout.rstrip("\n")
    except (OSError, subprocess.SubprocessError):
        return None
    values = out.split("\x1f")
    return dict(zip(FIELDS, values)) if len(values) == len(FIELDS) else None


def clock(microseconds):
    try:
        seconds = int(microseconds) // 1_000_000
    except ValueError:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


def status():
    found = [m for m in (metadata(p) for p in players()) if m and m["status"] in ("Playing", "Paused")]
    if not found:
        return {"text": "", "tooltip": "", "class": "stopped"}, False
    # the one playing, or the most recently listed paused one
    song = next((m for m in found if m["status"] == "Playing"), found[0])
    playing = song["status"] == "Playing"
    title = song["title"] or "unknown"
    label = f"{song['artist']} – {title}" if song["artist"] else title
    if len(label) > 38:
        label = label[:37] + "…"
    glyph = "" if playing else ""
    lines = [f"<b>{html.escape(title)}</b>"]
    if song["artist"]:
        lines.append(html.escape(song["artist"]))
    if song["album"]:
        lines.append(f"<i>{html.escape(song['album'])}</i>")
    position, length = clock(song["position"]), clock(song["mpris:length"])
    lines.append(f"{position} / {length}  ·  {song['playerName']}" if length else song["playerName"])
    lines.append("click play/pause · right-click next · middle-click previous")
    return {"text": f"{glyph}  {html.escape(label)}", "tooltip": "\n".join(lines),
            "class": "playing" if playing else "paused"}, playing


def main():
    last = None
    while True:
        value, playing = status()
        line = json.dumps(value)
        if line != last:
            print(line, flush=True)
            last = line
        time.sleep(1 if playing else 3)


if __name__ == "__main__":
    main()
