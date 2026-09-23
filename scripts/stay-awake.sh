#!/bin/sh
# Stay awake: while ~/.cache/stay-awake exists nothing locks, blanks the screen or sleeps on its
# own (idle.sh doesn't start swayidle), and closing the lid only turns the screen off.
#
# Usage: stay-awake.sh on|off|toggle   change it (the bar, Settings and Spotlight all use this)
#        stay-awake.sh status          the waybar module's JSON

flag=${XDG_CACHE_HOME:-$HOME/.cache}/stay-awake

case $1 in
    on) touch "$flag" ;;
    off) rm -f "$flag" ;;
    toggle) if [ -e "$flag" ]; then rm -f "$flag"; else touch "$flag"; fi ;;
    status)
        # U+F0F4 (coffee cup) while on; empty text hides the module while off
        if [ -e "$flag" ]; then
            printf '{"text": "\357\203\264", "tooltip": "staying awake · click to allow sleep", "class": "on"}\n'
        else
            printf '{"text": "", "tooltip": "", "class": "off"}\n'
        fi
        exit 0
        ;;
    *)
        sed -n '5,6p' "$0" >&2
        exit 1
        ;;
esac

# restart swayidle (or not) with the timers it last had, and redraw the bar icon
setsid -f "$HOME/.local/bin/idle.sh" >/dev/null 2>&1
pkill -RTMIN+14 -x waybar 2>/dev/null
exit 0
