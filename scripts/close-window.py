#!/usr/bin/env python3
"""Super+W: close the focused Sway window.

The settings panel and wallpaper picker used to be keyboard-grabbing overlays that needed to be
asked to quit first; they're normal windows now, so this is a plain kill. Kept as a script so the
keybinding has one place to grow special cases again.
"""
import subprocess


def main():
    subprocess.run(["swaymsg", "kill"], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
