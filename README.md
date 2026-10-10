# Asahi dotfiles

A Sway desktop for Fedora Asahi Remix on an Apple Silicon MacBook, set up to feel like home coming from macOS. Colors come from the wallpaper and follow it everywhere. Shortcuts use Command the way macOS does. The desktop comes with its own Spotlight, Quick Look, emoji picker, settings app, wallpaper picker, clipboard history, Markdown editor and calculator, all styled to match.

## What's included

| Component | Setup |
| --- | --- |
| Desktop | Sway with autotiling, Waybar, Fuzzel, SwayNC notifications, SwayOSD popups, swaylock, and swayidle |
| Login | greetd with tuigreet |
| Terminal and shell | Kitty, Zsh, Oh My Zsh, Powerlevel10k, Fastfetch, zoxide, eza, fzf, and lazygit |
| Editor | Neovim based on Kickstart, themed with pywal16.nvim |
| Theme | pywal16 (colorz palettes by default), Oomox GTK 3 themes, generated GTK 4/libadwaita colors, Pywalfox, btop, and Rosé Pine cursors |
| Font | BlexMono Nerd Font |
| Apps | [Spotlight](#spotlight), [Quick Look](#quick-look), [emoji picker](#emoji-picker), [Settings](#settings), [wallpaper picker](#wallpapers-and-colors), [clipboard history](#clipboard-history), [Walwrite](#walwrite), and Walcalc |
| Status bar | Workspaces, clock, stay awake, notifications, tray, coding-agent usage, Bluetooth, Wi-Fi, Tailscale, volume, and battery |

## Installation

The [installer](scripts/install.sh) targets Fedora Asahi Remix and downloads ARM64 builds of some tools. The checkout can live anywhere and nothing depends on your username: Stow links into your home directory, and the few files that need absolute paths are made when you run the installer.

```sh
git clone https://github.com/dblopez04/asahi-dotfiles.git ~/dotfiles
cd ~/dotfiles
bash scripts/install.sh
```

Read the installer and back up your existing configs before you run it. It's safe to re-run, and it does a lot:

- **Packages:** installs the desktop, apps and development tools with dnf, adding the SwayOSD COPR and Microsoft's VS Code repository. It also installs LocalSend, Pinta and Video Trimmer from Flathub.
- **User tools:**
  - pywal16 (with the colorz, haishoku and colorthief palette backends), Pywalfox and autotiling through pipx
  - Claude Code, Codex, opencode and lazygit
  - LibrePods, built from source for AirPods battery, noise control and ear detection, with a launcher entry
  - the Nerd Font and cursors
- **Links:** links the configs with Stow and every script in `scripts/` into `~/.local/bin`.
- **Theme:** generates the theme from the default wallpaper, sets up btop's theme, and enables the `usage-sampler` user service.
- **Shell:** makes Zsh your login shell.
- **System changes:**
  - enables Tailscale and makes you its operator, so settings can change without sudo
  - sets up a PostgreSQL role and database named after you
  - makes greetd the login screen, starting Sway through [`sway-session`](scripts/sway-session)
  - opens LocalSend's ports when firewalld is running
  - sets BlueZ's `AlwaysPairable` so Bluetooth pairings are saved without a desktop agent (otherwise AirPods forget the laptop)
  - swaps Fn with left Ctrl through `hid_apple`

Installer options:

```sh
# Skip the package, service, and system-tweak sections that use sudo.
# Required dependencies must already be installed.
bash scripts/install.sh --no-sudo

# Also configure a larger console font for tuigreet.
bash scripts/install.sh --console-font
```

`--no-sudo` still downloads user-level tools, links configs, generates themes, and tries to change the login shell. It is not a dry run. If Stow reports conflicts, move the conflicting files into your backup and run the installer again.

After installing:

- Reboot, or log out and back in, to start the desktop.
- Run `claude`, `codex`, and `opencode` to sign in to the tools you use.
- Run `sudo tailscale up` to connect to your tailnet.
- Install the Pywalfox extension in Firefox, then run `pywalfox update`.

## Keybindings

`Super` is the Command key. Open Settings → keyboard to search, change, or add shortcuts, or see the [Sway config](.config/sway/config).

| Shortcut | Action |
| --- | --- |
| `Super+Q` | Open the terminal (Kitty) |
| `Super+Space` | Open or close Spotlight |
| `Super+R` | Open the application launcher |
| `Super+E` | Open the file manager (Nautilus) |
| `Super+F` | Open Firefox |
| `Super+W` | Close the focused window |
| `Super+C/X/V/A` | Copy, cut, paste, or select all, in terminals too |
| `Super+Ctrl+V` | Clipboard history |
| `Super+Ctrl+Space` | Emoji picker |
| `Super+Shift+P` | Pick a color on screen (copies its hex code) |
| `Super+/` | Keyboard shortcut cheat sheet |
| `Super+,` | Open or close Settings |
| `Super+P` | Open or close the wallpaper picker |
| `Super+N` | Open or close the Control Center (quick toggles, sliders, media, notifications) |
| `Super+Shift+W` | Open Walwrite |
| `Super+Ctrl+Q` or the calculator key | Open Walcalc |
| `Super+K` / `Super+L` / `Super+Shift+K` | Screenshot the window / the screen / an area (saved to `~/Screenshots` and copied; click the notification to mark it up) |
| `Super+G` | Toggle fullscreen |
| `Super+Shift+V` | Toggle floating |
| `Super+J` | Toggle the split direction |
| `Super+Arrow` / `Super+Shift+Arrow` | Focus / move a window |
| `Super+1…9/0` / `Super+Shift+1…9/0` | Switch to / move a window to workspace 1–10 |
| `Super+scroll` | Cycle workspaces |
| `Super+S` / `Super+Shift+S` | Show the scratchpad / send a window to it |
| `Super+drag` | Move a floating window (right-drag resizes) |
| `Super+Shift+R` | Resize mode: arrows resize, Escape or Enter leaves |
| `Super+Shift+C` | Reload Sway |
| `Super+M` | Exit Sway |

Trackpad gestures: three fingers left or right switch workspaces, up opens Spotlight, and down opens the notification center; four fingers left or right move the window to the next or previous workspace. Change any of them in Settings → trackpad.

Firefox's picture-in-picture video floats in the bottom-right corner and follows you to every workspace (a window rule you can change in Settings → window rules).

`Super+/` shows every shortcut and gesture grouped by what it does (apps & tools, windows, workspaces, screenshots, clipboard, gestures, media & hardware, session). It's read from your Sway config, so it always matches your real bindings.

The media keys show SwayOSD popups for volume and brightness. F3 and F4 dim and brighten the keyboard backlight.

## Control Center

`Super+N` (or clicking the clock) opens a Control Center on the right, like macOS:

- **Toggles:** Wi-Fi, Bluetooth, do not disturb, stay awake, and Tailscale. They show what's on and flip with a click.
- **Quick actions:** screenshot an area, pick a color, clipboard history, Settings, and lock.
- **Sliders:** volume, screen brightness, and keyboard backlight. The volume slider picks up changes made elsewhere each time the Control Center opens.
- **Now playing:** the song with album art and controls, hidden when nothing is playing.
- **Notifications** underneath.

It's SwayNC, configured in [`.config/swaync/config.json`](.config/swaync/config.json) and styled from the pywal template. The toggles run [`control-center.sh`](scripts/control-center.sh).

## Status bar

Waybar's config is generated from [`.config/wal/templates/waybar-config.jsonc`](.config/wal/templates/waybar-config.jsonc). Settings → toolbar can show or hide modules (including the optional weather, network speed, and CPU & memory ones), set the weather location, move the bar, change its height, and switch the clock format.

| Module | Click | Other |
| --- | --- | --- |
| Now playing | Play / pause | The song from any player; right-click skips, middle-click goes back; hidden when nothing is playing |
| Clock | Notification center | |
| Timers | Cancel a timer | Counts down the soonest timer or reminder; hidden when there are none |
| Stay awake | Turns stay awake off | Only shown while stay awake is on |
| Notifications | Toggle do not disturb | |
| Tray arrow | Expands the tray | Only shown when an app has a tray icon |
| Coding agents | Usage menu for Claude Code, Codex, and opencode | Right-click refreshes account limits |
| Bluetooth, Wi-Fi, Tailscale | Fuzzel menus to connect, pick devices, and copy IPs | |
| Volume | Output and input menu | Scroll changes volume, right-click mutes, middle-click opens pavucontrol |
| Battery | Power menu (lock, log out, reboot, shut down) | Shows the percentage; right-click hides or shows it (remembered across reboots); the tooltip shows time left |
| Weather (optional) | | Temperature and conditions; the tooltip has a 3-day forecast |
| Network speed (optional) | | Download and upload speed of the active connection |
| CPU & memory (optional) | Opens btop | Turns yellow when the CPU is busy |

## Settings

`Super+,` opens a macOS-style settings window, styled like the fuzzel menus. Drag it by its top bar. The sidebar is grouped into connections, devices, personal, system, and manage. Use the arrows (or `j`/`k`) to pick a page, `→` or `Enter` to go into it, `←` or `Esc` to go back, and `Alt+1…5` to jump to a group. It's also in the launcher as System Settings.

| Group | Page | What it does |
| --- | --- | --- |
| connections | wi-fi | Networks, joining (including hidden ones and username/password networks like eduroam), connection details (IP, router, DNS, channel, speed), and saved networks with auto-join and forget |
|  | bluetooth | Power, discoverability, paired devices with battery levels, auto-connect and forget, and scanning for new devices |
|  | tailscale | Up/down, this device, the tailnet's devices (click to copy an IP), exit nodes, subnet routes, DNS, shields up, SSH, and the machine name |
| devices | sound | Output and input volume, mute, and default devices |
|  | displays | Screen and keyboard brightness, and scaling |
|  | trackpad | Tap to click, tap and drag, natural scrolling, disable while typing, click method, pointer and scroll speed |
|  | keyboard | Key repeat, and a searchable shortcut list where you record new keys, change commands, add, or remove |
|  | battery | Charge, time left, draw, health, a 24-hour or 10-day history of level, screen-on time and power draw, and the apps using the most energy |
| personal | appearance | Gaps, borders, focus follows mouse, cursor theme and size, palette style, and regenerating the colors |
|  | wallpaper | The wallpaper picker's grid, local and gallery |
|  | toolbar | Waybar modules, position, height, and the 12/24-hour clock |
|  | notifications | Do not disturb, clearing, and the notification center |
| system | lock & sleep | Stay awake, when to lock, turn off the display, and sleep, what closing the lid does, plus lock or sleep now |
|  | date & time | 12/24-hour clock, time zone search, and network time |
|  | default apps | Browser, mail, text editor, images, video, music, PDFs, archives, terminal, and file manager |
|  | window rules | Per-app rules: float, stay on every workspace, size, position, which workspace, opacity, and border |
|  | storage | Disk use split into apps, documents, media, developer files, caches and system, plus your home folders |
| manage | packages & apps | Search and uninstall dnf, Flatpak, pipx, npm/pnpm, and self-installed tools; edit, hide, or create launcher entries |
|  | maintenance | Updates (dnf, Flatpak, pipx, firmware) and cleanup (autoremove, unused runtimes, caches, thumbnails, trash, logs, containers) |
|  | dotfiles | This repo's branch and sync state, changed files with diffs (and undo), commit, pull, and push |
|  | backups | Earlier versions of the configs Settings replaced, with a diff and one-click restore |
|  | about | Model, chip, memory, OS, and current usage |

Anything that needs root, like uninstalling a package or running updates, opens in a terminal so you can see the command and enter your password.

### Unsaved changes and backups

Settings applies changes right away but doesn't touch your configs until you say so:

1. Sway changes go into `~/.config/sway/settings.conf`, which the main config includes near its end, so they apply live and survive reloads. Changes to other files, such as the Waybar template and the palette style, are kept in `~/.cache/settings-panel/pending`.
2. A bar at the bottom shows how many changes are unsaved, and lets you **review** them as a diff, **discard** them, or **save** them (also `Ctrl+S`).
3. Saving checks the merged Sway config with `sway -C`, backs up the old file to `backups/<path>/<date>` in the repository, and merges each change into the line it replaces.

The last 10 backups of each file are kept. Both `backups/` and `settings.conf` are ignored by Git.

The [staging code](scripts/dotconfig.py) is shared by Settings and the wallpaper picker.

### Battery and usage history

Level and power-draw history come from upower, so they cover time before the service below was set up. Screen-on time and per-app energy come from the `usage-sampler` user service, which runs [`usage-sampler.py`](scripts/usage-sampler.py).

Once a minute it records the battery level, power draw, whether the screen is on, and each app's share of CPU time. It writes these to `~/.local/state/usage/` and keeps 14 days.

Per-app energy is an estimate: CPU share multiplied by the battery's power draw.

The same service warns you when the battery runs low: notifications at 20%, 10% and 5% with the time left, and a button that opens Settings → battery. Plugging in resets the warnings.

## Wallpapers and colors

`Super+P` opens the wallpaper picker, which is also Settings → wallpaper and Wallpaper Picker in the launcher:

- **Browsing:** type to filter, use the arrows to move, and press `Enter` to pick. `Tab` switches between `~/wallpapers` and the [dharmx/walls](https://github.com/dharmx/walls) gallery, which downloads a pick into `~/wallpapers`.
- **Picking:** a pick becomes the wallpaper as an unsaved change and themes the whole desktop. The window stays open so you can try others. **Save** keeps the wallpaper, **undo** goes back.

Picking the current wallpaper again re-runs the theming.

To theme from any image without changing the wallpaper:

```sh
wal.sh ~/Pictures/some-image.jpg
```

[`wal.sh`](scripts/wal.sh):

1. Generates a pywal palette with the backend in [`.config/wal/backend`](.config/wal/backend) (`colorz` by default; set in Settings → appearance, or override with `WAL_BACKEND=wal wal.sh IMAGE`).
2. Reloads Sway, which redraws the window borders and restarts Waybar.
3. Rebuilds the Oomox GTK 3 theme and copies the generated GTK 4/libadwaita colors into `~/.config/gtk-4.0`.
4. Switches the GTK theme away and back, so open GTK 3 apps repaint.
5. Restarts SwayOSD, reloads SwayNC, and updates btop and Firefox (Pywalfox).

Kitty, Fuzzel, Neovim, swaylock, Walwrite, Walcalc, Settings, and the picker all read the palette themselves. Kitty and the apps recolor while running; Fuzzel, Neovim, and swaylock pick it up the next time they start.

Open GTK 4 apps like Nautilus keep their old colors until they're reopened. `wal.sh` quits Nautilus's background process when no Nautilus window is open.

Customize the generated styles by editing the templates in [`.config/wal/templates`](.config/wal/templates):

- `gtk.css` holds the GTK 4 and libadwaita colors.
- `colors-oomox` sets up the GTK 3 theme.
- The others cover Waybar, SwayNC, and swaylock.

The generated `.config/gtk-4.0/gtk.css` and `gtk-dark.css` are ignored by Git.

## Spotlight

`Super+Space` opens a search box in the middle of the screen, like Spotlight on macOS. Start typing to find:

- **Apps:** by name, description, or keywords. The ones you open most rank higher, and they're what you see before you type.
- **Settings pages:** like "trackpad" or "tailscale".
- **Commands:** lock, sleep, log out, restart, shut down, stay awake, do not disturb, clipboard history, the wallpaper picker, and more. Log out, restart and shut down ask you to press `Enter` twice.
- **Files and folders** in your home folder, from the `plocate` index (refreshed daily), plus recently opened files.
- **Math:** `2^10`, `sqrt(144)*2`, `15% * 200`. `Enter` copies the answer.
- **Conversions:** units (`5 km in miles`, `3 cups in ml`, `2.5 gb in mib`), temperature (`72f to c`), currency (`20 usd to eur`, with daily rates), and time zones (`time in tokyo`, `3pm in london`). `Enter` copies the answer.
- **Timers and reminders:** `timer 25m`, `timer 1h30m tea`, `remind me in 20m to stretch`, `remind me at 5pm to call mom`. They count down in the bar and notify you when they're done, and they survive logging out.
- **The web:** the last result always searches DuckDuckGo.

Use the arrows to pick, `Enter` to open, `Ctrl+Y` to [Quick Look](#quick-look) a file, `Ctrl+T` to send a file with [Taildrop](#taildrop), and `Ctrl+Enter` to show a file in its folder. `Esc` or clicking away closes it.

### Browsing folders

Type `~` or `/` (or pick "browse files") to look through folders instead of searching:

- **Moving around:** `Tab` or `Enter` goes into the selected folder, and `Shift+Tab` (or the `..` row) goes up.
- **Filtering:** anything typed after the last `/` filters the folder. Folders come first, and hidden files show once you type a leading `.`.
- **Opening:** `Enter` opens a file in its app, `Ctrl+Y` previews it with Quick Look, and `Ctrl+Enter` opens the folder (or shows the file) in the file manager.
- **From search:** `Tab` on any file or folder result starts browsing right there.

## Quick Look

A fast preview of a file without opening an app, like Space in Finder. Press `Ctrl+Y` on a file in Spotlight, or run `quicklook.py FILE`.

- **Previews:** images, text and code, PDFs (the first pages, with `poppler-utils`), video and audio (plays right away), and folders (their contents). Anything else shows its type and details.
- **Keys:** `←`/`→` step through the other files in the same folder, `Enter` opens the file in its app, and `Esc` or `Space` closes. The buttons at the top open the file or show it in its folder.
- **Back to Spotlight:** closing a preview you opened from Spotlight (`Esc`, `Space`, or ×) brings Spotlight back where you were, with the file you ended on selected. Opening the file or its folder doesn't.

## Taildrop

Send files to your other Tailscale devices: `Ctrl+T` on a file in Spotlight, the **send** button (or `t`) in Quick Look, or `taildrop.py send FILE…`. Pick a device from the list of online ones and you get a notification when it arrives. Files sent to this Mac land in `~/Downloads` automatically (the `taildrop-receive` user service).

Taildrop needs Tailscale connected and you as its operator: Settings → tailscale → allow changes without sudo.

## Screenshots and colors

Screenshots are saved to `~/Screenshots` and copied. Click the notification to mark one up in Swappy (arrows, text, highlights, blur); if you don't, it simply stays copied. `Super+Shift+P` picks the color of any pixel, copies its hex code, and shows a swatch.

## Emoji picker

`Super+Ctrl+Space` opens a grid of emoji by category, like the macOS picker, with the ones you use most on top. Type to search by name or keyword ("thumbs", "lol", "party"), move with the arrows, and press `Enter` (or click): the emoji is typed into the window you were in and copied to the clipboard. `Tab` and `Shift+Tab` jump between categories, the icons along the bottom do the same, and `Shift+Enter` or a right-click picks a skin tone. The grid remembers the tone you used last.

Emoji are drawn with Noto Color Emoji. For Twemoji or OpenMoji instead, install `twitter-twemoji-fonts` or `hfg-gmuend-openmoji-color-fonts` and prefer it in `~/.config/fontconfig/fonts.conf`:

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias binding="same"><family>emoji</family><prefer><family>Twemoji</family></prefer></alias>
</fontconfig>
```

Emoji the font can't draw (Twemoji stops at Unicode 14) are left out of the picker.

## Clipboard history

Everything you copy, text and images, is kept so you can paste it again. `Super+Ctrl+V` (or "clipboard history" in Spotlight) lists recent copies in fuzzel; pick one to copy it again, or clear the history from the bottom of the list.

[`clipboard-history.py`](scripts/clipboard-history.py) keeps the newest 200 copies, up to 100 MB, as private files in `~/.local/share/clipboard-history`. Copies that password managers mark as sensitive aren't recorded.

## Walwrite

A Markdown and plain-text editor in the pywal colors, opened with `Super+Shift+W`, `walwrite FILE…`, or the launcher.

- **Documents:** open several files at once. The sidebar (`Ctrl+\`) lists open documents and a folder's text files (`Ctrl+Shift+O` picks the folder).
- **Saving:** saved files autosave a moment after each edit and when you leave the window. Untitled documents are kept as drafts, so closing never loses text. The files you had open come back the next time it starts.
- **Markdown:** syntax is highlighted with dimmed markers. Return continues lists (and ends them on an empty item), and `Tab`/`Shift+Tab` indent list items.
- **Preview:** `Ctrl+E` shows the rendered Markdown and `Ctrl+Shift+E` shows it side by side. The preview uses WebKitGTK and python-markdown when they're installed, and a simpler built-in renderer otherwise.
- **Menus:** press `Alt` for the File, Edit, Format, View, and Help menus. `Ctrl+?` lists every shortcut.

Other shortcuts:

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` / `Ctrl+Shift+N` | New document / new window |
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | Open / save / save as |
| `Ctrl+W` | Close the document |
| `Ctrl+Tab` or `Ctrl+PageDown`, `Ctrl+Shift+Tab` or `Ctrl+PageUp` | Next / previous document |
| `Ctrl+F` / `Ctrl+H` | Find / replace |
| `Ctrl+B` / `Ctrl+I` / `Ctrl+K` / `` Ctrl+` `` | Bold / italic / link / inline code |
| `Ctrl+1…3` | Heading level (press again to remove) |
| `Ctrl+=` / `Ctrl+-` / `Ctrl+0` | Text size |
| `Ctrl+Alt+=` / `Ctrl+Alt+-` / `Ctrl+Alt+0` | Interface size (sidebar, footer, menus, and dialogs) |
| `Ctrl+P` | Print |
| `F11` | Fullscreen |

Pasting a URL over selected text turns it into a link. Drafts and the session are stored in `~/.local/state/walwrite`.

## Walcalc

A simple calculator in the pywal colors, based on Omarchy's Omacalc. Open it with `Super+Ctrl+Q`, the calculator key, or the launcher. It works from the keyboard or the keypad.

## Idle, lid, locking, and sleep

[`idle.sh`](scripts/idle.sh) starts swayidle with the timers set at the top of the Sway config:

- lock after 5 minutes idle
- turn the screen off 30 seconds later
- suspend after 30 minutes

It also locks before sleeping. It runs on every Sway reload, so new timers from Settings take effect right away.

Closing the lid goes through [`lid.sh`](scripts/lid.sh) instead of logind:

- **On its own:** the laptop sleeps (or locks, or just turns the screen off, set in Settings → lock & sleep).
- **With an external display:** only the laptop screen turns off, so you can keep working.
- **Opening the lid** turns the screen back on.

**Stay awake** keeps the laptop from locking, blanking, or sleeping, and closing the lid only turns the screen off. Turn it on from Spotlight or Settings → lock & sleep. While it's on, a coffee cup shows in the bar; click it to turn stay awake off.

Everything goes through [`stay-awake.sh`](scripts/stay-awake.sh) `on`, `off`, or `toggle`, which creates or removes `~/.cache/stay-awake` and restarts swayidle with the same timers.

## Repository layout

```text
.config/
  sway/           Sway config, fallback colors, and the ignored settings.conf
  waybar/         Style; config.jsonc and colors.css link to the generated copies
  wal/            Palette backend and pywal templates (GTK, Oomox, Waybar, SwayNC, swaylock)
  systemd/user/   The usage-sampler service
  kitty/ fuzzel/ swaync/ swayosd/ swaylock/ fastfetch/ feh/ gtk-3.0/ gtk-4.0/ nvim/
.local/share/     Launcher entries and the default cursor
.zshrc .p10k.zsh  Shell environment, plugins, aliases, and prompt
scripts/          Installer, apps, Waybar modules, and helpers (linked into ~/.local/bin)
  settings-panel.py, settings_pages/   Settings and its pages
  wallpaper-picker.py, wal.sh          Wallpapers and theming
  dotconfig.py                         Unsaved changes, merging, and backups
  walwrite, walcalc                    Editor and calculator
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

GNU Stow links the configuration into your home directory. The links to pywal's generated files (Waybar, SwayNC, swaylock, and SwayOSD colors) and the file manager bookmarks are made by the installer and git-ignored, since they hold absolute paths; see [`.stow-local-ignore`](.stow-local-ignore) for what it skips. The installer links the utilities in `scripts/` into `~/.local/bin` separately. The configs are symlinks, so editing them (or saving from Settings) changes the repository checkout.

## Customization

- **Display:** set the scale in Settings → displays, or change `output eDP-1 scale` in the Sway config. Pick a scale that divides the 2560x1600 panel evenly; others leave a glitchy row at the bottom.
- **Session environment:** [`sway-session`](scripts/sway-session) makes Qt apps follow the GTK theme, runs Electron and Firefox as native Wayland apps, and puts `~/.local/bin` on the PATH. The installer copies it to `/usr/local/bin`, so run the installer again, or reinstall it by hand, after editing.
- **Hardware:** check the installer's Apple keyboard settings, ARM64 downloads, and the M1 Air function-key bindings before using this on another machine.
- **Shell:** aliases include `v` for Neovim, `cd` for zoxide, `ls` for eza, and `lg` for lazygit.
- **Neovim:** see its [README](.config/nvim/README.md) for editor-specific setup.

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
