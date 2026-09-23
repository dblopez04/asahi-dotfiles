#!/usr/bin/env python3
"""Taildrop: send files to your other Tailscale devices, and receive theirs into ~/Downloads.

Usage: taildrop.py send FILE...   pick a device in fuzzel and send (Quick Look and Spotlight use this)
       taildrop.py receive        wait for incoming files (the taildrop-receive user service)

Needs Tailscale connected, and you as its operator (Settings > tailscale > allow changes without sudo).
"""
import json
import os
import subprocess
import sys
import time

DOWNLOADS = os.path.expanduser("~/Downloads")


def notify(title, body, urgency="normal"):
    subprocess.run(["notify-send", "-a", "taildrop", "-u", urgency, "-i", "network-transmit", title, body])


def status():
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10).stdout
        return json.loads(out or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def explain(error):
    lowered = error.lower()
    if "access denied" in lowered or "permission" in lowered:
        return "Tailscale needs you as its operator: Settings > tailscale > allow changes without sudo"
    if "stopped" in lowered or "not running" in lowered or "needslogin" in lowered:
        return "Tailscale is off: turn it on in Settings > tailscale"
    return error.strip().splitlines()[-1] if error.strip() else "unknown error"


def send(files):
    files = [os.path.abspath(f) for f in files if os.path.isfile(f)]
    if not files:
        notify("Nothing to send", "Taildrop sends files, not folders", "normal")
        return
    state = status()
    if state.get("BackendState") != "Running":
        notify("Can't send", explain("stopped"))
        return
    peers = sorted((p for p in (state.get("Peer") or {}).values() if p.get("Online")),
                   key=lambda p: p.get("HostName", "").lower())
    if not peers:
        notify("Can't send", "none of your other devices are online")
        return
    rows = [f"{p.get('HostName')}  ·  {p.get('OS', '')}" for p in peers]
    names = ", ".join(os.path.basename(f) for f in files)
    result = subprocess.run(["fuzzel", "--dmenu", "--index", "--prompt", "send to > ", "--width", "40",
                             "--lines", str(min(len(rows), 10))], input="\n".join(rows), text=True, capture_output=True)
    choice = result.stdout.strip()
    if result.returncode != 0 or not choice.isdigit():
        return
    peer = peers[int(choice)]
    target = (peer.get("TailscaleIPs") or [peer.get("HostName")])[0]
    notify("Sending", f"{names} → {peer.get('HostName')}")
    proc = subprocess.run(["tailscale", "file", "cp", *files, f"{target}:"], capture_output=True, text=True)
    if proc.returncode == 0:
        notify("Sent", f"{names} → {peer.get('HostName')}")
    else:
        notify("Couldn't send", explain(proc.stderr or proc.stdout), "critical")


def receive():
    """Move incoming files into ~/Downloads as they arrive, with a notification for each batch."""
    os.makedirs(DOWNLOADS, exist_ok=True)
    while True:
        before = set(os.listdir(DOWNLOADS))
        proc = subprocess.run(["tailscale", "file", "get", "--wait", "--conflict=rename", DOWNLOADS],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            time.sleep(60)  # tailscale off, or no permission yet; try again later
            continue
        new = sorted(set(os.listdir(DOWNLOADS)) - before)
        if new:
            notify("Received", ", ".join(new) + " · in Downloads")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "send":
        send(sys.argv[2:])
    elif sys.argv[1:] == ["receive"]:
        receive()
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
