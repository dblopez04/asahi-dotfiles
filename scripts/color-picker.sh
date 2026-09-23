#!/bin/sh
# Color picker: click anywhere on screen to copy that pixel's hex code (Super+Shift+P).
# A notification shows a swatch with the hex and rgb values.

point=$(slurp -p 2>/dev/null) || exit 0
values=$(grim -g "$point" -t ppm - | magick - -format '%[fx:int(255*r)] %[fx:int(255*g)] %[fx:int(255*b)]' info:) || exit 1
set -- $values
hex=$(printf '#%02x%02x%02x' "$1" "$2" "$3")

printf '%s' "$hex" | wl-copy
swatch="${XDG_RUNTIME_DIR:-/tmp}/color-picker.png"
magick -size 96x96 "xc:$hex" "$swatch"
notify-send -a "color picker" -i "$swatch" "$hex" "rgb($1, $2, $3) · copied"
