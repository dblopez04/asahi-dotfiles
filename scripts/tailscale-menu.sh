#!/bin/bash
# Tailscale menu (fuzzel dmenu mode): connect/disconnect and copy machine IPs.
# Reopens after each action until closed with Escape.

notify() { notify-send -u low tailscale "$1"; }
# up/down need root unless you're the operator (sudo tailscale set --operator=$USER),
# so fall back to a polkit password prompt
ts() {
    local out
    if ! out=$(tailscale "$@" 2>&1); then
        case $out in
            *[Aa]ccess\ denied*) out=$(pkexec tailscale "$@" 2>&1) && return 0 ;;
        esac
        notify-send -u critical tailscale "$out"
        return 1
    fi
}

while true; do
    # refresh the bar indicator
    pkill -RTMIN+11 waybar

    status=$(tailscale status --json 2>/dev/null)
    [ -n "$status" ] || { notify-send -u critical tailscale "tailscaled isn't running"; exit 1; }
    state=$(jq -r .BackendState <<<"$status")

    labels=() actions=()
    case $state in
        Running) labels+=(disconnect); actions+=(down) ;;
        NeedsLogin) labels+=("log in"); actions+=(login) ;;
        *) labels+=(connect); actions+=(up) ;;
    esac

    if [ "$state" = Running ]; then
        labels+=("copy this machine's ip"); actions+=("copy:$(jq -r '.Self.TailscaleIPs[0]' <<<"$status")")
        while IFS=$'\t' read -r name ip online; do
            labels+=("copy ip: $name ($online)"); actions+=("copy:$ip")
        done < <(jq -r '[.Peer // {} | .[]] | sort_by(.Online | not) | .[]
            | "\(.HostName)\t\(.TailscaleIPs[0])\t\(if .Online then "online" else "offline" end)"' <<<"$status")
    fi

    i=$(printf '%s\n' "${labels[@]}" | fuzzel --dmenu --index --prompt 'tailscale > ' --minimal-lines --lines 10 --width 40)
    [[ $i =~ ^[0-9]+$ ]] || exit
    action=${actions[$i]}

    case $action in
        up) ts up && notify connected ;;
        down) ts down && notify disconnected ;;
        login) exec kitty -e bash -c 'sudo tailscale up; read -rp "press enter to close"' ;;
        copy:*) printf '%s' "${action#copy:}" | wl-copy && notify "copied ${action#copy:}" ;;
    esac
done
