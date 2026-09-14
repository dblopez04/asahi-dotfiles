#!/bin/bash
# Tailscale indicator for waybar (hidden when tailscaled isn't running)

status=$(tailscale status --json 2>/dev/null)
[ -n "$status" ] || { echo '{"text": ""}'; exit; }

jq -c --arg icon $'\U000F0582' '
    if .BackendState == "Running" then
        {text: $icon, class: "connected", tooltip: "tailscale: \(.CurrentTailnet.Name)\n\(.Self.TailscaleIPs[0])"}
    else
        {text: $icon, class: "disconnected", tooltip: "tailscale: \(.BackendState | ascii_downcase)"}
    end' <<<"$status"
