#!/bin/bash
# Dexcom glucose in the bar, using waybar-pydexcom (github.com/dblopez04/waybar-pydexcom). Optional:
# install.sh --dexcom or Settings > toolbar sets it up. The login is kept in the keyring (gnome-keyring).
#
# Usage: dexcom.sh install   clone or update waybar-pydexcom and its venv in ~/.local/share
#        dexcom.sh login     save the Dexcom Share username and password (prompts, or two lines on stdin)
#        dexcom.sh status    prints missing, signed-out or ready
#        dexcom.sh bar       the waybar module's JSON (hidden until it's installed)

REPO=https://github.com/dblopez04/waybar-pydexcom.git
DIR=${XDG_DATA_HOME:-$HOME/.local/share}/waybar-pydexcom
PY=$DIR/venv/bin/python3
SERVICE=waybar-pydexcom  # the keyring names waybar-pydexcom's credentials.py uses

# prints yes if both credentials are in the keyring (and the keyring could be reached)
signed_in() {
    "$PY" - "$SERVICE" 2>/dev/null <<'EOF'
import sys, keyring
service = sys.argv[1]
print("yes" if keyring.get_password(service, "username") and keyring.get_password(service, "password") else "no")
EOF
}

case $1 in
    install)
        if [ -d "$DIR/.git" ]; then
            git -C "$DIR" pull -q --ff-only || echo "couldn't update $DIR, keeping the current version" >&2
        else
            mkdir -p "$(dirname "$DIR")"
            git clone -q --depth 1 "$REPO" "$DIR" || exit 1
        fi
        [ -x "$PY" ] || python3 -m venv "$DIR/venv" || exit 1
        "$PY" -m pip install -q --upgrade pip pydexcom keyring || exit 1
        command -v gnome-keyring-daemon >/dev/null ||
            echo "no keyring found: install gnome-keyring and gnome-keyring-pam, then log out and back in" >&2
        echo "waybar-pydexcom is installed in $DIR"
        ;;
    login)
        [ -x "$PY" ] || { echo "not installed: run dexcom.sh install first" >&2; exit 1; }
        if [ -t 0 ]; then
            read -rp "Dexcom username: " user
            read -rsp "Dexcom password: " pass
            echo
        else
            IFS= read -r user
            IFS= read -r pass
        fi
        [ -n "$user" ] && [ -n "$pass" ] || { echo "enter a username and a password" >&2; exit 1; }
        # the password goes through stdin, never the command line
        err=$(printf '%s\n%s\n' "$user" "$pass" | "$PY" -c '
import sys, keyring
user, password = sys.stdin.read().split("\n")[:2]
keyring.set_password(sys.argv[1], "username", user)
keyring.set_password(sys.argv[1], "password", password)
' "$SERVICE" 2>&1) || {
            err=${err##*$'\n'}
            [[ $err == *NoKeyringError* ]] && err="no keyring is running (install gnome-keyring, then log in again)"
            echo "couldn't save the login: $err" >&2
            exit 1
        }
        pkill -RTMIN+16 -x waybar 2>/dev/null
        echo "signed in"
        ;;
    status)
        if [ ! -x "$PY" ]; then echo missing
        elif [ "$(signed_in)" = yes ]; then echo ready
        else echo signed-out
        fi
        ;;
    bar)
        [ -x "$PY" ] || { echo '{"text": ""}'; exit 0; }
        out=$(timeout 30 "$PY" "$DIR/waybar-pydexcom.py" 2>&1)
        if jq -e . >/dev/null 2>&1 <<<"$out"; then
            echo "$out"
        else
            # no login, no keyring or no network: show a dash with the reason
            reason=$(tail -1 <<<"$out")
            case $reason in
                *NoKeyringError*) reason="no keyring is running (install gnome-keyring)" ;;
                "") reason="no reading" ;;
            esac
            jq -nc --arg why "${reason:0:160}" \
                '{text: "-", class: "error", tooltip: "dexcom: \($why)\nset it up in Settings > toolbar"}'
        fi
        ;;
    *)
        sed -n '5,8p' "$0" >&2
        exit 1
        ;;
esac
