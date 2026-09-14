#!/usr/bin/env python3
"""Set feh as the default for the image types its desktop entry supports."""
import os
from pathlib import Path
import subprocess

data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
roots = [data_home, *(Path(p) for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"))]
desktop = next((p / "applications/feh.desktop" for p in roots
                if (p / "applications/feh.desktop").is_file()), None)
if desktop is None:
    raise SystemExit("feh.desktop not found; install feh first")
for line in desktop.read_text().splitlines():
    if line.startswith("MimeType="):
        for mime in line.partition("=")[2].split(";"):
            if mime.startswith("image/"):
                subprocess.run(["xdg-mime", "default", "feh.desktop", mime], check=True)
                print(f"{mime} → feh")
