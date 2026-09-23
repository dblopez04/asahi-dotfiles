#!/bin/sh
# The Control Center's toggle buttons and volume slider (swaync; see ~/.config/swaync/config.json).
#
# Usage: control-center.sh state wifi|bluetooth|dnd|stay-awake|tailscale   prints true or false
#        control-center.sh set NAME                                         turns it on or off to match
#                                                                           $SWAYNC_TOGGLE_STATE
#        control-center.sh volume [PERCENT]                                 prints or sets the output volume
# Kept as a script so the swaync config needs no nested shell quoting.

name=$2

state() {
    case $name in
        wifi) [ "$(nmcli radio wifi)" = enabled ] ;;
        bluetooth) bluetoothctl show | grep -q "Powered: yes" ;;
        dnd) [ "$(swaync-client -D)" = true ] ;;
        stay-awake) [ -e "${XDG_CACHE_HOME:-$HOME/.cache}/stay-awake" ] ;;
        tailscale) tailscale status --json 2>/dev/null | grep -q '"BackendState": "Running"' ;;
        *) return 1 ;;
    esac
}

set_state() {
    on=$SWAYNC_TOGGLE_STATE
    case $name in
        wifi) nmcli radio wifi "$([ "$on" = true ] && echo on || echo off)" ;;
        bluetooth)
            if [ "$on" = true ]; then rfkill unblock bluetooth; bluetoothctl power on; else bluetoothctl power off; fi ;;
        dnd) swaync-client "$([ "$on" = true ] && echo -dn || echo -df)" ;;
        stay-awake) "$HOME/.local/bin/stay-awake.sh" "$([ "$on" = true ] && echo on || echo off)" ;;
        tailscale) tailscale "$([ "$on" = true ] && echo up || echo down)" ;;
    esac
} >/dev/null 2>&1

volume() {
    if [ -z "$name" ]; then
        wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{ printf "%d\n", $2 * 100 + 0.5 }'
    else
        wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ "${name%.*}%"
        [ "${name%.*}" -gt 0 ] && wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
    fi
}

case $1 in
    volume) volume ;;
    state) if state; then echo true; else echo false; fi ;;
    set) set_state ;;
    *) sed -n '4,8p' "$0" >&2; exit 1 ;;
esac
