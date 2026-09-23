#!/usr/bin/env python3
"""Clipboard history: text and images you copy, kept so you can paste them again.

Usage: clipboard-history.py watch    record every copy (sway starts this)
       clipboard-history.py pick     choose an old entry in fuzzel and copy it again (Super+Ctrl+V)
       clipboard-history.py clear    forget everything

Entries are files in ~/.local/share/clipboard-history (private to you): the newest 200, up to 100 mb.
Copies password managers mark as sensitive (CLIPBOARD_STATE=sensitive) aren't recorded.
"""
import hashlib
import os
import struct
import subprocess
import sys
import time

HISTORY = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "clipboard-history")
MAX_ENTRIES = 200
MAX_BYTES = 100 * 2**20
MAX_ITEM = 20 * 2**20
IMAGE_TYPES = {b"\x89PNG\r\n\x1a\n": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"),
               b"GIF8": ("gif", "image/gif"), b"RIFF": ("webp", "image/webp")}


def entries():
    """Newest first: [(path, mtime, size)]."""
    try:
        names = os.listdir(HISTORY)
    except OSError:
        return []
    items = []
    for name in names:
        path = os.path.join(HISTORY, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        items.append((path, stat.st_mtime, stat.st_size))
    return sorted(items, key=lambda e: e[1], reverse=True)


def kind(data):
    for magic, (extension, mime) in IMAGE_TYPES.items():
        if data.startswith(magic):
            return extension, mime
    return "txt", "text/plain"


def store():
    """Save stdin (one copy, from `wl-paste --watch`) as the newest entry."""
    if os.environ.get("CLIPBOARD_STATE") in ("sensitive", "clear", "nil"):
        return
    data = sys.stdin.buffer.read(MAX_ITEM + 1)
    if not data or len(data) > MAX_ITEM or (not data.strip()):
        return
    extension, _mime = kind(data)
    if extension == "txt":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return  # some other binary type; not worth keeping
    os.makedirs(HISTORY, mode=0o700, exist_ok=True)
    digest = hashlib.sha1(data).hexdigest()[:16]
    path = os.path.join(HISTORY, f"{digest}.{extension}")
    if os.path.exists(path):
        os.utime(path)  # copied again: move it to the top
    else:
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            f.write(data)
    total = 0
    for index, (old, _mtime, size) in enumerate(entries()):
        total += size
        if index >= MAX_ENTRIES or total > MAX_BYTES:
            os.remove(old)


def watch():
    """Record copies until the session ends (wl-paste runs `store` for each one)."""
    os.execvp("wl-paste", ["wl-paste", "--watch", sys.executable, os.path.realpath(__file__), "store"])


def image_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(26)
        if head.startswith(b"\x89PNG"):
            return "%dx%d" % struct.unpack(">II", head[16:24])
    except (OSError, struct.error):
        pass
    return ""


def preview(path, size):
    if path.endswith(".txt"):
        with open(path, "rb") as f:
            text = f.read(400).decode("utf-8", errors="replace")
        line = " ".join(text.split())
        return (line[:90] + "…") if len(line) > 90 else line
    dimensions = image_size(path)
    return f"[image {dimensions} {path.rsplit('.', 1)[-1]}, {size // 1024} kb]".replace("  ", " ")


def ago(mtime):
    seconds = time.time() - mtime
    for unit, length in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= length:
            return f"{int(seconds // length)}{unit}"
    return "now"


def pick():
    items = entries()
    rows = [f"{preview(path, size)}  ·  {ago(mtime)}" for path, mtime, size in items]
    rows.append("clear history" if items else "nothing copied yet")
    result = subprocess.run(["fuzzel", "--dmenu", "--index", "--prompt", "clipboard > ", "--width", "60",
                             "--lines", "15"], input="\n".join(rows), text=True, capture_output=True)
    choice = result.stdout.strip()
    if result.returncode != 0 or not choice.isdigit():
        return
    index = int(choice)
    if index >= len(items):
        if items:
            clear()
        return
    path = items[index][0]
    with open(path, "rb") as f:
        data = f.read()
    _extension, mime = kind(data) if not path.endswith(".txt") else ("txt", "text/plain")
    subprocess.run(["wl-copy", "--type", mime], input=data)


def clear():
    for path, _mtime, _size in entries():
        os.remove(path)


if __name__ == "__main__":
    commands = {"watch": watch, "store": store, "pick": pick, "clear": clear}
    command = sys.argv[1] if len(sys.argv) > 1 else "pick"
    if command not in commands:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    commands[command]()
