#!/bin/bash
# Themes the whole desktop from an image: wal.sh IMAGE
# (the wallpaper itself is set in the sway config; see the wallpaper picker)
img=$1

# wal, oomox-cli and pywalfox live in ~/.local/bin, which apps started by sway (the wallpaper
# picker, the settings panel) don't have on their PATH
export PATH="$HOME/.local/bin:$PATH"

if [ -z "$img" ]; then
    echo "Usage: $0 IMAGE" >&2
    exit 1
fi

# generate colorscheme (-n: keep the wallpaper set in the sway config).
# The backend (palette style) is picked in the settings panel's appearance page; colorz picks
# livelier accents than pywal's default. Fall back to the default if it breaks.
backend=${WAL_BACKEND:-$(cat "$HOME/.config/wal/backend" 2>/dev/null)}
wal -n -q --backend "${backend:-colorz}" -i "$img" || wal -n -q -i "$img" || exit 1

# reload sway: re-reads ~/.cache/wal/colors-sway (borders) and restarts waybar, whose
# colors.css links to the new palette. (Don't also signal waybar: mid-restart that kills it.)
swaymsg reload >/dev/null

# gtk 3: rebuild the oomox theme. gtk 4 / libadwaita: the generated gtk.css
oomox-cli ~/.cache/wal/colors-oomox >/dev/null 2>&1
mkdir -p "$HOME/.config/gtk-4.0"
cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"
cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk-dark.css"
# running gtk 3 apps only reload their theme when its name changes, so switch away and back
gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita'
sleep 0.3
gsettings set org.gnome.desktop.interface gtk-theme 'oomox-colors-oomox'
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
# gtk 4 apps never re-read gtk.css. Nautilus stays running in the background after its last
# window closes, so new windows would keep the old colors; quit it if no window is open.
if pgrep -x nautilus >/dev/null && ! swaymsg -t get_tree | grep -q '"app_id": "org.gnome.Nautilus"'; then
    nautilus -q 2>/dev/null
fi

# restart the volume/brightness popup so it picks up the new colors
pkill -x swayosd-server
swaymsg exec swayosd-server >/dev/null

# reload notification colors
swaync-client -rs >/dev/null 2>&1

# btop: the generated theme (selected by color_theme in btop.conf)
mkdir -p "$HOME/.config/btop/themes"
ln -sfn "$HOME/.cache/wal/btopwal.theme" "$HOME/.config/btop/themes/wal.theme"

# update firefox colors
command -v pywalfox >/dev/null && pywalfox update >/dev/null 2>&1

# kitty and other terminals get the new colors from wal's escape sequences; walwrite, the
# settings panel and the wallpaper picker watch ~/.cache/wal/colors.json themselves

if [ -t 1 ]; then
    echo " Colors generated from $img"
    wal --preview
fi
