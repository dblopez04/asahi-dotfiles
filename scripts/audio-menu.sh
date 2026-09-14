#!/bin/bash
# Audio menu (fuzzel dmenu mode): mute, mixer, and output/input device picker.
# Reopens after each action until closed with Escape.

while true; do
    default_sink=$(pactl get-default-sink)
    default_source=$(pactl get-default-source)
    volume=$(pactl get-sink-volume @DEFAULT_SINK@ | grep -o '[0-9]*%' | head -n 1)

    labels=() actions=()
    if [ "$(pactl get-sink-mute @DEFAULT_SINK@)" = "Mute: yes" ]; then
        labels+=(unmute)
    else
        labels+=(mute)
    fi
    actions+=(mute)
    labels+=("open mixer"); actions+=(mixer)

    while IFS=$'\t' read -r name desc; do
        label="output: $desc"
        [ "$name" = "$default_sink" ] && label="$label (current)"
        labels+=("$label"); actions+=("sink:$name")
    done < <(pactl -f json list sinks | jq -r '.[] | "\(.name)\t\(.description)"')

    while IFS=$'\t' read -r name desc; do
        label="input: $desc"
        [ "$name" = "$default_source" ] && label="$label (current)"
        labels+=("$label"); actions+=("source:$name")
    done < <(pactl -f json list sources | jq -r '.[] | select(.name | endswith(".monitor") | not) | "\(.name)\t\(.description)"')

    i=$(printf '%s\n' "${labels[@]}" | fuzzel --dmenu --index --prompt "audio $volume > " --minimal-lines --lines 10 --width 44)
    [[ $i =~ ^[0-9]+$ ]] || exit
    action=${actions[$i]}

    case $action in
        mute) swayosd-client --output-volume mute-toggle ;;
        mixer) exec pavucontrol ;;
        sink:*) pactl set-default-sink "${action#sink:}" ;;
        source:*) pactl set-default-source "${action#source:}" ;;
    esac
done
