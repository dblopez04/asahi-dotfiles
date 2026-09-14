#!/bin/bash
# Bluetooth menu (fuzzel dmenu mode). Reopens after each action until closed with Escape.

menu() { fuzzel --dmenu --index --prompt "$1" --minimal-lines --lines 10 --width 40; }
notify() { notify-send -u low bluetooth "$1"; }
run() {
    local out
    out=$("$@" 2>&1) || { notify-send -u critical bluetooth "$out"; return 1; }
}

while true; do
    if ! bluetoothctl show 2>/dev/null | grep -q 'Powered: yes'; then
        i=$(printf 'turn bluetooth on\n' | menu 'bluetooth > ')
        [ "$i" = 0 ] || exit
        rfkill unblock bluetooth
        sleep 1 # the adapter takes a moment to come back after unblocking
        run bluetoothctl power on
        continue
    fi

    labels=("scan for devices" "turn bluetooth off") actions=(scan off) names=("" "")
    while read -r _ mac name; do
        info=$(bluetoothctl info "$mac")
        if grep -q 'Connected: yes' <<<"$info"; then
            labels+=("$name (connected)"); actions+=("disconnect:$mac")
        elif grep -q 'Paired: yes' <<<"$info"; then
            labels+=("$name"); actions+=("connect:$mac")
        else
            labels+=("$name (new)"); actions+=("pair:$mac")
        fi
        names+=("$name")
    done < <(bluetoothctl devices)

    i=$(printf '%s\n' "${labels[@]}" | menu 'bluetooth > ')
    [[ $i =~ ^[0-9]+$ ]] || exit
    action=${actions[$i]} name=${names[$i]} mac=${actions[$i]#*:}

    case $action in
        scan)
            notify "scanning for 8 seconds"
            bluetoothctl --timeout 8 scan on >/dev/null
            ;;
        off) run bluetoothctl power off ;;
        connect:*) run bluetoothctl connect "$mac" && notify "connected to $name" ;;
        disconnect:*) run bluetoothctl disconnect "$mac" && notify "disconnected from $name" ;;
        pair:*)
            notify "pairing with $name"
            run bluetoothctl pair "$mac" && run bluetoothctl trust "$mac" \
                && run bluetoothctl connect "$mac" && notify "connected to $name"
            ;;
    esac
done
