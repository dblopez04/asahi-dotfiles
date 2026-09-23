#!/bin/sh
# Screenshots: saved to ~/Screenshots and copied. Clicking the notification opens it for markup
# (swappy, or Pinta if swappy isn't installed); otherwise it just stays copied.
#
# Usage: screenshot.sh area|window|output

dir=${XDG_SCREENSHOTS_DIR:-$HOME/Screenshots}
mkdir -p "$dir"
file="$dir/$(date +%Y-%m-%d_%H-%M-%S).png"

case $1 in
    area) target=area ;;
    window) target=active ;;
    output) target=output ;;
    *) echo "usage: screenshot.sh area|window|output" >&2; exit 1 ;;
esac

grimshot save "$target" "$file" >/dev/null 2>&1 || exit 0  # cancelled (esc while selecting)
wl-copy --type image/png < "$file"

markup() {
    if command -v swappy >/dev/null; then
        swappy -f "$file" -o "$file"   # saving writes back to the same file (and swappy can copy it)
    elif flatpak info com.github.PintaProject.Pinta >/dev/null 2>&1; then
        flatpak run com.github.PintaProject.Pinta "$file"
    else
        xdg-open "$file"
    fi
}

# notify-send -A waits for a click, so do that in the background
(
    action=$(notify-send -a screenshot -i "$file" -A default="mark up" -A markup="mark up" \
        "Screenshot copied" "$(basename "$file") · click to mark it up")
    case $action in default | markup) markup ;; esac
) >/dev/null 2>&1 &
