#!/bin/sh
# Closing and opening the lid, run by sway's bindswitch (see the end of the sway config).
#
# Usage: lid.sh close [sleep|lock|nothing]   what to do when it closes (set in Settings > lock & sleep)
#        lid.sh open
#        lid.sh inhibit                      keep logind from also suspending on its own (sway starts this)
#
# With an external display connected the laptop screen just turns off (clamshell), and while
# ~/.cache/stay-awake exists closing the lid only blanks the screen. LID_DRY_RUN=1 prints the
# commands instead of running them.

internal=eDP-1
flag=${XDG_CACHE_HOME:-$HOME/.cache}/stay-awake

run() {
    if [ -n "$LID_DRY_RUN" ]; then echo "$*"; else "$@"; fi
}

case $1 in
    inhibit)
        # logind suspends on lid close by default; hold its lid switch while sway runs. The loop
        # ends (releasing the lock) within a minute of sway exiting, so the login screen isn't affected.
        exec systemd-inhibit --what=handle-lid-switch --who=sway --mode=block \
            --why="lid.sh decides what closing the lid does" \
            sh -c 'while swaymsg -t get_version >/dev/null 2>&1; do sleep 60; done'
        ;;
    open)
        run swaymsg output "$internal" enable
        run swaymsg output "$internal" power on
        ;;
    close)
        others=$(swaymsg -r -t get_outputs | jq --arg name "$internal" '[.[] | select(.active and .name != $name)] | length')
        if [ "${others:-0}" -gt 0 ]; then
            run swaymsg output "$internal" disable  # clamshell: keep working on the external display
        elif [ -e "$flag" ]; then
            run swaymsg output "$internal" power off
        else
            case ${2:-sleep} in
                sleep)
                    run swaylock -f
                    run systemctl suspend
                    ;;
                lock)
                    run swaylock -f
                    run swaymsg output "$internal" power off
                    ;;
                *)
                    run swaymsg output "$internal" power off
                    ;;
            esac
        fi
        ;;
    *)
        sed -n '4,7p' "$0" >&2
        exit 1
        ;;
esac
