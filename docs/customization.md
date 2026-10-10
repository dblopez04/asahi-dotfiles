# Customization and troubleshooting

## Customization

- **Display:** set the scale in Settings → displays, or change `output eDP-1 scale` in the Sway config. Pick a scale that divides the 2560x1600 panel evenly; others leave a glitchy row at the bottom.
- **Session environment:** [`sway-session`](../scripts/sway-session) makes Qt apps follow the GTK theme, runs Electron and Firefox as native Wayland apps, and puts `~/.local/bin` on the PATH. The installer copies it to `/usr/local/bin`, so run the installer again, or reinstall it by hand, after editing.
- **Hardware:** check the installer's Apple keyboard settings, ARM64 downloads, and the M1 Air function-key bindings before using this on another machine.
- **Shell:** aliases include `v` for Neovim, `cd` for zoxide, `ls` for eza, and `lg` for lazygit.
- **Neovim:** see its [README](../.config/nvim/README.md) for editor-specific setup.

## Troubleshooting

- **A script can't find `wal`, `oomox-cli`, or another tool:** Sway gives apps only `/usr/local/bin:/usr/bin`. Scripts that need `~/.local/bin` add it themselves, and logging in through `sway-session` adds it for everything.
- **The desktop never locks or sleeps:** stay awake is probably on. Look for the coffee cup in the bar, or check for `~/.cache/stay-awake`.
- **Closing the lid does nothing:** check that sway's lid inhibitor is listed in `systemd-inhibit --list`, and what Settings → lock & sleep says the lid should do.
- **Spotlight doesn't find a new file:** the file index refreshes daily; run `sudo updatedb` to refresh it now.
- **A setting looks wrong after a change:** review or discard it in the bar at the bottom of Settings, or restore an earlier config from Settings → backups.
- **Walwrite's preview is plain:** install `webkitgtk6.0` and `python3-markdown` (the installer does), then reopen Walwrite.
- **No color in the emoji picker, or PDFs don't preview:** install `google-noto-color-emoji-fonts` and `poppler-utils` (the installer does).
- **The emoji picker says it needs the emoji list:** install `unicode-emoji` and `cldr-emoji-annotation` (the installer does).
- **Battery apps list is empty:** check that the sampler is running with `systemctl --user status usage-sampler`. The list fills in after it has run for a while on battery.
