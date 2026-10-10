# Installation

The [installer](../scripts/install.sh) targets Fedora Asahi Remix and downloads ARM64 builds of some tools. The checkout can live anywhere and nothing depends on your username: Stow links into your home directory, and the few files that need absolute paths are made when you run the installer.

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
  - makes greetd the login screen, starting Sway through [`sway-session`](../scripts/sway-session)
  - opens LocalSend's ports when firewalld is running
  - sets BlueZ's `AlwaysPairable` so Bluetooth pairings are saved without a desktop agent (otherwise AirPods forget the laptop)
  - swaps Fn with left Ctrl through `hid_apple`

## Installer options

```sh
# Skip the package, service, and system-tweak sections that use sudo.
# Required dependencies must already be installed.
bash scripts/install.sh --no-sudo

# Also configure a larger console font for tuigreet.
bash scripts/install.sh --console-font

# Also set up Dexcom glucose in the bar (see below).
bash scripts/install.sh --dexcom
```

`--no-sudo` still downloads user-level tools, links configs, generates themes, and tries to change the login shell. It is not a dry run. If Stow reports conflicts, move the conflicting files into your backup and run the installer again.

### Dexcom glucose

`--dexcom` adds your current glucose reading and trend to the bar with [waybar-pydexcom](https://github.com/dblopez04/waybar-pydexcom). It needs Dexcom Share turned on with at least one follower. The installer:

- installs `gnome-keyring` and its PAM module. greetd's PAM config already unlocks the keyring when you log in, so the Dexcom login stays encrypted at rest without a separate password prompt.
- clones waybar-pydexcom into `~/.local/share/waybar-pydexcom` and gives it its own Python venv with `pydexcom` and `keyring`.
- asks for your Dexcom username and password if the keyring is already running. Otherwise, log out and back in, then sign in under Settings → toolbar → dexcom.

Then turn on **dexcom glucose** in Settings → toolbar. You can also skip the flag and do the whole setup from that page. [`dexcom.sh`](../scripts/dexcom.sh) does the work for both: `install`, `login`, `status`, and `bar`.

## After installing

- Reboot, or log out and back in, to start the desktop.
- Run `claude`, `codex`, and `opencode` to sign in to the tools you use.
- Run `sudo tailscale up` to connect to your tailnet.
- Install the Pywalfox extension in Firefox, then run `pywalfox update`.

## What's included

| Component | Setup |
| --- | --- |
| Desktop | Sway with autotiling, Waybar, Fuzzel, SwayNC notifications, SwayOSD popups, swaylock, and swayidle |
| Login | greetd with tuigreet |
| Terminal and shell | Kitty, Zsh, Oh My Zsh, Powerlevel10k, Fastfetch, zoxide, eza, fzf, and lazygit |
| Editor | Neovim based on Kickstart, themed with pywal16.nvim |
| Theme | pywal16 (colorz palettes by default), Oomox GTK 3 themes, generated GTK 4/libadwaita colors, Pywalfox, btop, and Rosé Pine cursors |
| Font | BlexMono Nerd Font |
| Apps | [Spotlight](apps.md#spotlight), [Quick Look](apps.md#quick-look), [emoji picker](apps.md#emoji-picker), [Settings](settings.md), [wallpaper picker](theming.md), [clipboard history](apps.md#clipboard-history), and [Walwrite](walwrite.md) |
| Status bar | Workspaces, clock, stay awake, notifications, tray, coding-agent usage, Bluetooth, Wi-Fi, Tailscale, volume, and battery |
