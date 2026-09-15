#!/bin/sh
# (Re)starts swayidle with the timers from the sway config. Run by `exec_always` in the sway
# config, so a reload picks up new values.
#
# Usage: idle.sh LOCK_SECONDS SCREEN_OFF_SECONDS SUSPEND_SECONDS   (0 turns that step off)
# While ~/.cache/stay-awake exists nothing locks, blanks or suspends (the settings panel's
# "stay awake" switch).

lock=${1:-300}
screen=${2:-330}
suspend=${3:-1800}

pkill -x swayidle
[ -e "${XDG_CACHE_HOME:-$HOME/.cache}/stay-awake" ] && exit 0

set -- -w
[ "$lock" -gt 0 ] && set -- "$@" timeout "$lock" 'swaylock -f'
[ "$screen" -gt 0 ] && set -- "$@" timeout "$screen" 'swaymsg "output * power off"' resume 'swaymsg "output * power on"'
[ "$suspend" -gt 0 ] && set -- "$@" timeout "$suspend" 'systemctl suspend'
set -- "$@" before-sleep 'swaylock -f' after-resume 'swaymsg "output * power on"' lock 'swaylock -f'

exec swayidle "$@"
