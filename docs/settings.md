# Settings

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
|  | wallpaper | The [wallpaper picker](theming.md#wallpaper-picker)'s grid, local and gallery |
|  | toolbar | Waybar modules, position, height, and the 12/24-hour clock |
|  | notifications | Do not disturb, clearing, and the notification center |
| system | lock & sleep | Stay awake, when to lock, turn off the display, and sleep, what closing the lid does, plus lock or sleep now |
|  | date & time | 12/24-hour clock, time zone search, and network time |
|  | default apps | Browser, mail, text editor, images, video, music, PDFs, archives, terminal, and file manager |
|  | window rules | Per-app rules: float, stay on every workspace, size, position, which workspace, opacity, and border |
|  | storage | Disk use split into apps, documents, media, developer files, caches and system, with a folder browser to find what's taking up space ([details](#storage)) |
| manage | packages & apps | Search and uninstall dnf, Flatpak, pipx, npm/pnpm, and self-installed tools; edit, hide, or create launcher entries |
|  | maintenance | Updates (dnf, Flatpak, pipx, firmware) and cleanup (autoremove, unused runtimes, caches, thumbnails, trash, logs, containers) |
|  | dotfiles | This repo's branch and sync state, changed files with diffs (and undo), commit, pull, and push |
|  | backups | Earlier versions of the configs Settings replaced, with a diff and one-click restore |
|  | about | Model, chip, memory, OS, and current usage |

Anything that needs root, like uninstalling a package or running updates, opens in a terminal so you can see the command and enter your password.

## Storage

The storage page shows how the disk is used, split into apps, documents, media, developer files, caches and system. Click a category in the legend to list what's in it, biggest first, or click "other" to browse the whole disk from `/`. The browser starts in your home folder.

- **Look inside:** click a folder to see the biggest subfolders and files in it. Up to 50 are listed, with a note when smaller ones are hidden.
- **Go back:** click any part of the path bar, or use `[ up ]`, Backspace, or Esc. `[ home ]` returns to your home folder.
- **Right-click** a file or folder (or press the Menu key) to **open it in the file browser**, which selects a file inside its folder, or to **move it to the trash**. Trash is greyed out where you'd need root.

Sizes are measured in the background and kept until you close Settings. `[ measure again ]` starts over. The browser counts actual disk use, so its numbers can differ slightly from the category totals, which count file sizes.

## Unsaved changes and backups

Settings applies changes right away but doesn't touch your configs until you say so:

1. Sway changes go into `~/.config/sway/settings.conf`, which the main config includes near its end, so they apply live and survive reloads. Changes to other files, such as the Waybar template and the palette style, are kept in `~/.cache/settings-panel/pending`.
2. A bar at the bottom shows how many changes are unsaved, and lets you **review** them as a diff, **discard** them, or **save** them (also `Ctrl+S`).
3. Saving checks the merged Sway config with `sway -C`, backs up the old file to `backups/<path>/<date>` in the repository, and merges each change into the line it replaces.

The last 10 backups of each file are kept. Both `backups/` and `settings.conf` are ignored by Git.

The [staging code](../scripts/dotconfig.py) is shared by Settings and the wallpaper picker.

## Battery and usage history

Level and power-draw history come from upower, so they cover time before the service below was set up. Screen-on time and per-app energy come from the `usage-sampler` user service, which runs [`usage-sampler.py`](../scripts/usage-sampler.py).

Once a minute it records the battery level, power draw, whether the screen is on, and each app's share of CPU time. It writes these to `~/.local/state/usage/` and keeps 14 days.

Per-app energy is an estimate: CPU share multiplied by the battery's power draw.

The same service warns you when the battery runs low: notifications at 20%, 10% and 5% with the time left, and a button that opens Settings → battery. Plugging in resets the warnings.
