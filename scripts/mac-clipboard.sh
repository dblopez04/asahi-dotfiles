#!/bin/sh
# macOS-style Cmd+<key>: send Ctrl+<key> to apps, Ctrl+Shift+C/V to terminals.
# Usage: mac-clipboard.sh c|x|v|a

key=$1

app=$(swaymsg -t get_tree | jq -r '
    [.. | objects | select(.focused == true)][0]
    | .app_id // .window_properties.class // empty')

case $app in
    kitty|foot|footclient|Alacritty|org.wezfurlong.wezterm|com.mitchellh.ghostty|org.gnome.Ptyxis|org.gnome.Console)
        case $key in
            c|v) exec wtype -M ctrl -M shift -k "$key" -m shift -m ctrl ;;
            # Ctrl+A / Ctrl+X mean something else in a shell, so don't send them
            *) exit 0 ;;
        esac
        ;;
    *)
        exec wtype -M ctrl -k "$key" -m ctrl
        ;;
esac
