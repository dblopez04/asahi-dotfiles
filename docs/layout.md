# Repository layout

```text
.config/
  sway/           Sway config, fallback colors, and the ignored settings.conf
  waybar/         Style; config.jsonc and colors.css link to the generated copies
  wal/            Palette backend and pywal templates (GTK, Oomox, Waybar, SwayNC, swaylock)
  systemd/user/   The usage-sampler service
  kitty/ fuzzel/ swaync/ swayosd/ swaylock/ fastfetch/ feh/ gtk-3.0/ gtk-4.0/ nvim/
.local/share/     Launcher entries and the default cursor
.zshrc .p10k.zsh  Shell environment, plugins, aliases, and prompt
docs/             This documentation and the README's screenshots
scripts/          Installer, apps, Waybar modules, and helpers (linked into ~/.local/bin)
  settings-panel.py, settings_pages/   Settings and its pages
  wallpaper-picker.py, wal.sh          Wallpapers and theming
  dotconfig.py                         Unsaved changes, merging, and backups
  walwrite                             Markdown editor
  spotlight.py, quicklook.py           Search and file previews
  clipboard-history.py, emoji-picker.py   Clipboard history and emoji
  conversions.py, timer.py             Spotlight conversions, timers and reminders
  cheatsheet.py, taildrop.py           Shortcut cheat sheet and sending files
  control-center.sh, sysinfo.py        Control Center toggles, and the weather/network/CPU bar modules
  screenshot.sh, color-picker.sh       Screenshots with markup, and the color picker
  idle.sh, lid.sh, stay-awake.sh       Idle timers, the lid, and stay awake
  usage-sampler.py                     Battery and app usage history
  sway-session                         Starts Sway with the session environment
  *-status.*, *-menu.sh, agent-usage.py   Waybar modules and fuzzel menus
wallpapers/       Bundled wallpapers (gallery downloads land here too)
backups/          Config backups made by Settings (ignored)
```

GNU Stow links the configuration into your home directory. The links to pywal's generated files (Waybar, SwayNC, swaylock, and SwayOSD colors) and the file manager bookmarks are made by the installer and git-ignored, since they hold absolute paths; see [`.stow-local-ignore`](../.stow-local-ignore) for what it skips. The installer links the utilities in `scripts/` into `~/.local/bin` separately. The configs are symlinks, so editing them (or saving from Settings) changes the repository checkout.
