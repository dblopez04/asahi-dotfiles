#!/usr/bin/env bash
# Sets up this sway rice on Fedora Asahi Remix. Safe to re-run.
#
# Usage: ~/dotfiles/scripts/install.sh [--no-sudo] [--console-font]
#   --no-sudo       skip everything that needs sudo (packages, system services and tweaks)
#   --console-font  use a large console font so the tuigreet login screen is readable
set -euo pipefail

DOTFILES="$(cd "$(dirname "$0")/.." && pwd)"
WALLPAPER="$HOME/wallpapers/homer_on_the_trail.jpg"
USE_SUDO=true
CONSOLE_FONT=false

for arg in "$@"; do
    case $arg in
        --no-sudo) USE_SUDO=false ;;
        --console-font) CONSOLE_FONT=true ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done

export PATH="$HOME/.local/bin:$PATH"
step() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
clone() { [ -d "$2" ] || git clone -q --depth 1 "$1" "$2"; }
github_asset_url() { # repo, exact asset name
    curl -fsSL "https://api.github.com/repos/$1/releases/latest" \
        | jq -r --arg name "$2" '.assets[] | select(.name == $name) | .browser_download_url'
}

PACKAGES=(
    # desktop
    sway swaybg swayidle swaylock waybar SwayNotificationCenter swayosd fuzzel
    xdg-desktop-portal-wlr mate-polkit greetd tuigreet
    # used by keybindings and scripts
    grim slurp grimshot wl-clipboard wtype jq brightnessctl playerctl pavucontrol
    # apps
    kitty nautilus firefox code neovim vim-enhanced feh mpv libreoffice flatpak
    # shell and terminal tools
    zsh fzf eza zoxide fastfetch tmux ripgrep fd-find bat btop tree powertop
    # development
    gcc gcc-c++ make cmake gdb valgrind clang git-delta podman podman-compose
    postgresql-server postgresql postgresql-contrib
    nodejs22 nodejs22-npm pnpm
    # fonts
    google-noto-fonts-common google-noto-emoji-fonts
    # theming: pywal and the oomox GTK theme builder
    ImageMagick pipx sassc librsvg2-tools gdk-pixbuf2-devel glib2-devel bc glib2 elementary-icon-theme
    # this script
    stow git curl tar xz
)

if $USE_SUDO; then
    step "Adding package repositories"
    sudo dnf -y copr enable erikreider/swayosd
    # Visual Studio Code (Microsoft's repo has aarch64 builds)
    vscode_repo='[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
autorefresh=1
type=rpm-md
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc'
    if [ "$(cat /etc/yum.repos.d/vscode.repo 2>/dev/null)" != "$vscode_repo" ]; then
        sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
        printf '%s\n' "$vscode_repo" | sudo tee /etc/yum.repos.d/vscode.repo >/dev/null
    fi

    step "Installing packages"
    sudo dnf -y group install development-tools
    sudo dnf -y install "${PACKAGES[@]}"

    step "Setting up Flathub and installing Flatpak apps"
    sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    sudo flatpak install -y --noninteractive flathub org.localsend.localsend_app com.github.PintaProject.Pinta

    step "Opening the LocalSend port in the firewall"
    if firewall-cmd --state >/dev/null 2>&1; then
        sudo firewall-cmd -q --permanent --add-port=53317/tcp --add-port=53317/udp
        sudo firewall-cmd -q --reload
    else
        echo "firewalld is not running, skipping"
    fi
fi

step "Installing BlexMono Nerd Font"
font_dir="$HOME/.local/share/fonts/BlexMonoNerdFont"
if [ ! -d "$font_dir" ]; then
    mkdir -p "$font_dir"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/latest/download/IBMPlexMono.tar.xz | tar -xJ -C "$font_dir"
    fc-cache -f "$HOME/.local/share/fonts" >/dev/null
fi

step "Installing pywal and pywalfox"
pipx list --short 2>/dev/null | grep -q '^pywal16 ' || pipx install pywal16
pipx list --short 2>/dev/null | grep -q '^pywalfox ' || pipx install pywalfox
pywalfox install >/dev/null

step "Installing oh-my-zsh, powerlevel10k, and the oomox theme builder"
clone https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
clone https://github.com/romkatv/powerlevel10k.git "$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
clone https://github.com/themix-project/oomox-gtk-theme "$HOME/.local/share/oomox-gtk-theme"

mkdir -p "$HOME/.local/bin"

step "Installing lazygit"
if ! command -v lazygit >/dev/null; then
    url=$(curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest \
        | jq -r '.assets[].browser_download_url | select(test("linux_arm64\\.tar\\.gz$"))')
    curl -fsSL "$url" | tar -xz -C "$HOME/.local/bin" lazygit
fi

step "Installing Claude Code"
if ! command -v claude >/dev/null; then
    curl -fsSL https://claude.ai/install.sh | bash
fi

step "Installing OpenAI Codex"
if ! command -v codex >/dev/null; then
    tmp=$(mktemp -d)
    curl -fsSL "$(github_asset_url openai/codex codex-aarch64-unknown-linux-musl.tar.gz)" | tar -xz -C "$tmp"
    install -m 755 "$tmp/codex-aarch64-unknown-linux-musl" "$HOME/.local/bin/codex"
    rm -rf "$tmp"
fi

step "Linking dotfiles"
# create parents so stow links individual entries inside them instead of the whole directory
mkdir -p "$HOME/.config" "$HOME/.local/share"
(cd "$DOTFILES" && stow --restow .)

step "Linking scripts into ~/.local/bin"
for script in "$DOTFILES"/scripts/*; do
    name=$(basename "$script")
    [ "$name" = install.sh ] && continue
    ln -sfn "$script" "$HOME/.local/bin/$name"
done

step "Generating colors from $(basename "$WALLPAPER")"
gsettings set org.gnome.desktop.interface cursor-theme 'BreezeX-RosePine-Linux'
gsettings set org.gnome.desktop.interface cursor-size 24
if [ -n "${SWAYSOCK:-}" ]; then
    wal.sh "$WALLPAPER"
else
    # not inside sway: same as wal.sh minus reloading running programs
    wal -n -q -i "$WALLPAPER"
    oomox-cli "$HOME/.cache/wal/colors-oomox" >/dev/null
    gsettings set org.gnome.desktop.interface gtk-theme 'oomox-colors-oomox'
    gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
    cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"
    cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk-dark.css"
fi

step "Setting zsh as the login shell"
zsh_path=$(command -v zsh)
if [ "$(basename "$(getent passwd "$USER" | cut -d: -f7)")" != zsh ]; then
    chsh -s "$zsh_path"
fi

if $USE_SUDO; then
    step "Setting up PostgreSQL"
    if ! sudo test -f /var/lib/pgsql/data/PG_VERSION; then
        sudo postgresql-setup --initdb
    fi
    sudo systemctl enable --now postgresql.service
    # a superuser role and database named after you, so `psql` works without flags
    pg() { (cd / && sudo -u postgres psql -tAXc "$1"); }
    [ "$(pg "SELECT 1 FROM pg_roles WHERE rolname = '$USER'")" = 1 ] \
        || (cd / && sudo -u postgres createuser --superuser "$USER")
    [ "$(pg "SELECT 1 FROM pg_database WHERE datname = '$USER'")" = 1 ] \
        || (cd / && sudo -u postgres createdb --owner "$USER" "$USER")

    step "Setting up the tuigreet login screen"
    greetd_conf='[terminal]
vt = next

[default_session]
command = "tuigreet --time --remember --cmd sway"
user = "greetd"'
    if [ "$(cat /etc/greetd/config.toml 2>/dev/null)" != "$greetd_conf" ]; then
        printf '%s\n' "$greetd_conf" | sudo tee /etc/greetd/config.toml >/dev/null
    fi
    # --force replaces any other display manager (e.g. sddm) as the login screen
    sudo systemctl enable --force greetd.service

    step "Swapping Fn and left Ctrl"
    conf=/etc/modprobe.d/hid_apple.conf
    line='options hid_apple swap_fn_leftctrl=1'
    if [ "$(cat "$conf" 2>/dev/null)" != "$line" ]; then
        echo "$line" | sudo tee "$conf" >/dev/null
        echo 1 | sudo tee /sys/module/hid_apple/parameters/swap_fn_leftctrl >/dev/null || true
        sudo dracut -f
    fi

    if $CONSOLE_FONT; then
        step "Setting a large console font"
        sudo dnf -y install terminus-fonts-console
        sudo sed -i 's/^FONT=.*/FONT="ter-v32b"/' /etc/vconsole.conf
    fi
fi

step "Done"
cat <<'EOF'
Next:
  - reboot (or log out and back in) to start sway with everything
  - sign in: run `claude` and `codex` once each
  - add the Pywalfox extension in Firefox, then run: pywalfox update
  - change the theme any time with: wal.sh /path/to/image
EOF
