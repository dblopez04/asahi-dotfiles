#!/bin/sh
# Text power menu (fuzzel dmenu mode)
choice=$(printf 'lock\nlogout\nreboot\nshutdown\n' | fuzzel --dmenu --prompt 'power > ' --lines 4 --width 20)

case $choice in
    lock) swaylock -f ;;
    logout) swaymsg exit ;;
    reboot) systemctl reboot ;;
    shutdown) systemctl poweroff ;;
esac
