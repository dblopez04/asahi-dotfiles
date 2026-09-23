#!/bin/bash
# Wi-Fi menu (fuzzel dmenu mode). Reopens after each action until closed with Escape.

menu() { fuzzel --dmenu --index --prompt "$1" --minimal-lines --lines 10 --width 40; }
notify() { notify-send -u low wifi "$1"; }
run() {
    local out
    out=$("$@" 2>&1) || { notify-send -u critical wifi "$out"; return 1; }
}

dev=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2 == "wifi" { print $1; exit }')
[ -n "$dev" ] || { notify-send -u critical wifi "no wifi device found"; exit 1; }

rescan=no
while true; do
    if [ "$(nmcli radio wifi)" = disabled ]; then
        i=$(printf 'turn wifi on\n' | menu 'wifi > ')
        [ "$i" = 0 ] || exit
        run nmcli radio wifi on
        rescan=yes
        continue
    fi

    current=$(nmcli -g GENERAL.CONNECTION device show "$dev")

    labels=() actions=()
    unset seen security
    declare -A seen security # seen: SSID -> its index in labels
    if [ -n "$current" ]; then
        labels+=("disconnect from $current"); actions+=(disconnect)
    fi
    labels+=(rescan "turn wifi off"); actions+=(rescan off)

    # terse output is IN-USE:SIGNAL:SECURITY:SSID, with colons in the SSID escaped as \:
    while IFS= read -r line; do
        in_use=${line%%:*}; line=${line#*:}
        signal=${line%%:*}; line=${line#*:}
        sec=${line%%:*}; ssid=${line#*:}
        ssid=${ssid//\\:/:}
        [ -n "$ssid" ] || continue
        if [ -n "${seen[$ssid]:-}" ]; then
            # the same network on another band/access point; the one in use may not be the strongest
            [ "$in_use" = "*" ] && labels[${seen[$ssid]}]+=" (connected)"
            continue
        fi
        seen[$ssid]=${#labels[@]}
        security[$ssid]=$sec
        label="$ssid  $signal%"
        [ "$in_use" = "*" ] && label="$label (connected)"
        labels+=("$label"); actions+=("connect:$ssid")
    done < <(nmcli -t -f IN-USE,SIGNAL,SECURITY,SSID device wifi list ifname "$dev" --rescan "$rescan")
    rescan=no

    i=$(printf '%s\n' "${labels[@]}" | menu 'wifi > ')
    [[ $i =~ ^[0-9]+$ ]] || exit
    action=${actions[$i]}

    case $action in
        disconnect) run nmcli connection down id "$current" && notify "disconnected from $current" ;;
        rescan) rescan=yes ;;
        off) run nmcli radio wifi off ;;
        connect:*)
            ssid=${action#connect:}
            if nmcli -g NAME connection show | grep -qxF "$ssid"; then
                run nmcli connection up id "$ssid" && notify "connected to $ssid"
            elif [[ ${security[$ssid]} == *802.1X* ]]; then
                # enterprise (eduroam, work, school): a username and password, sent with PEAP/MSCHAPv2.
                # other EAP setups (certificates, TTLS) can be made in nmtui
                user=$(fuzzel --dmenu --prompt-only "username > ")
                [ -n "$user" ] || continue
                pass=$(fuzzel --dmenu --prompt-only "password > " --password)
                [ -n "$pass" ] || continue
                if run nmcli connection add type wifi ifname "$dev" con-name "$ssid" ssid "$ssid" \
                        wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
                        802-1x.identity "$user" 802-1x.password "$pass" \
                    && run nmcli connection up id "$ssid"; then
                    notify "connected to $ssid"
                else
                    nmcli connection delete id "$ssid" >/dev/null 2>&1
                fi
            else
                args=()
                if [ -n "${security[$ssid]}" ]; then
                    pass=$(fuzzel --dmenu --prompt-only "password > " --password)
                    [ -n "$pass" ] || continue
                    args=(password "$pass")
                fi
                if run nmcli device wifi connect "$ssid" "${args[@]}" ifname "$dev"; then
                    notify "connected to $ssid"
                else
                    # don't keep a saved profile with a wrong password
                    nmcli connection delete id "$ssid" >/dev/null 2>&1
                fi
            fi
            ;;
    esac
done
