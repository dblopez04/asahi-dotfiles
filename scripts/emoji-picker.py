#!/usr/bin/env python3
"""Emoji picker: search emoji by name in fuzzel and type the one you pick (Super+Ctrl+Space).

The pick is typed into the window you were in and also left on the clipboard. The ones you use
most show first.
"""
import json
import os
import subprocess
import sys
import time
import unicodedata

STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "emoji-picker")
RECENT = os.path.join(STATE, "recent.json")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                     f"emoji-picker-{unicodedata.unidata_version}.txt")

# blocks that are (mostly) emoji; symbols in the older blocks get the emoji presentation selector
RANGES = [(0x1F600, 0x1F64F), (0x1F910, 0x1F9FF), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF), (0x1FA70, 0x1FAFF),
          (0x2600, 0x26FF), (0x2700, 0x27BF), (0x1F0CF, 0x1F0CF), (0x1F170, 0x1F251)]
TEXT_STYLE = (0x2600, 0x27BF)
SKIP_WORDS = ("VARIATION", "COMBINING", "REGIONAL INDICATOR", "TAG ", "SKIN TONE", "PLAYING CARD")
# a few everyday words the unicode names don't use
ALIASES = {
    "👍": "thumbs up yes ok like", "👎": "thumbs down no dislike", "😂": "laugh lol haha crying laughing",
    "🤣": "rofl laugh", "😭": "cry sad sob", "❤": "love heart red", "🔥": "fire lit hot", "🎉": "party tada celebrate",
    "✅": "check done yes", "❌": "cross no wrong x", "🙏": "please thanks pray", "🤷": "shrug idk",
    "👀": "eyes look", "💀": "dead skull lmao", "😅": "sweat nervous awkward", "🥲": "smile tear",
    "🙃": "upside down sarcasm", "😊": "blush happy smile", "🤔": "think hmm", "🚀": "rocket ship launch",
    "✨": "sparkles magic", "💯": "hundred perfect", "👋": "wave hi hello bye", "🫡": "salute",
}


def emoji_list():
    """[(emoji, name)] for every emoji this Python knows a name for, cached per Unicode version."""
    try:
        with open(CACHE) as f:
            return [tuple(line.rstrip("\n").split("\t", 1)) for line in f if "\t" in line]
    except OSError:
        pass
    items = []
    for start, end in RANGES:
        for code in range(start, end + 1):
            name = unicodedata.name(chr(code), "")
            if not name or any(word in name for word in SKIP_WORDS):
                continue
            char = chr(code) + ("️" if TEXT_STYLE[0] <= code <= TEXT_STYLE[1] else "")
            items.append((char, name.lower()))
    try:
        with open(CACHE, "w") as f:
            f.writelines(f"{char}\t{name}\n" for char, name in items)
    except OSError:
        pass
    return items


def load_recent():
    try:
        with open(RECENT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    recent = load_recent()
    items = emoji_list()
    # most used first (by count, then how recently), then everything else in unicode order
    order = sorted(recent, key=lambda char: (-recent[char][0], -recent[char][1]))
    known = dict(items)
    rows = [(char, known.get(char, "")) for char in order if char in known]
    used = {char for char, _ in rows}
    rows += [(char, name) for char, name in items if char not in used]
    lines = []
    for char, name in rows:
        extra = ALIASES.get(char.rstrip("️"), "")
        lines.append(f"{char}  {name}" + (f"  ·  {extra}" if extra else ""))

    result = subprocess.run(["fuzzel", "--dmenu", "--index", "--prompt", "emoji > ", "--width", "45", "--lines", "14"],
                            input="\n".join(lines), text=True, capture_output=True)
    choice = result.stdout.strip()
    if result.returncode != 0 or not choice.isdigit():
        return
    char = rows[int(choice)][0]

    count, _when = recent.get(char, (0, 0))
    recent[char] = (count + 1, time.time())
    os.makedirs(STATE, exist_ok=True)
    with open(RECENT, "w") as f:
        json.dump(recent, f)

    subprocess.run(["wl-copy", char])
    time.sleep(0.15)  # let focus go back to the window that was active before fuzzel
    subprocess.run(["wtype", char], stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    main()
