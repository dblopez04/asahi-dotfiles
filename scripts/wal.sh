#!/bin/bash
img=$1

if [ -z "$img" ]; then
    echo "Usage: $0 IMAGE" >&2
    exit 1
fi

# generate colorscheme (-n: keep the wallpaper set in the sway config)
wal -n -i "$img"

# reload sway: re-reads ~/.cache/wal/colors-sway and restarts waybar
swaymsg reload

# update gtk colors
oomox-cli ~/.cache/wal/colors-oomox
gsettings set org.gnome.desktop.interface gtk-theme 'oomox-colors-oomox'
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"
cp "$HOME/.cache/wal/gtk.css" "$HOME/.config/gtk-4.0/gtk-dark.css"

# restart the volume/brightness popup so it picks up the new colors
pkill -x swayosd-server
swaymsg exec swayosd-server >/dev/null

# reload notification colors
swaync-client -rs >/dev/null

# update firefox colors
command -v pywalfox >/dev/null && pywalfox update

clear
echo " Wallpaper colors generated from $img"
echo " Terminal colors changed"
echo " Sway colors changed"
echo " Waybar colors changed"
echo " GTK themed"
wal --preview
