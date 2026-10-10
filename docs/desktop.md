# Control Center and status bar

## Control Center

`Super+N` (or clicking the clock) opens a Control Center on the right, like macOS:

- **Toggles:** Wi-Fi, Bluetooth, do not disturb, stay awake, and Tailscale. They show what's on and flip with a click.
- **Quick actions:** screenshot an area, pick a color, clipboard history, Settings, and lock.
- **Sliders:** volume, screen brightness, and keyboard backlight. The volume slider picks up changes made elsewhere each time the Control Center opens.
- **Now playing:** the song with album art and controls, hidden when nothing is playing.
- **Notifications** underneath.

It's SwayNC, configured in [`.config/swaync/config.json`](../.config/swaync/config.json) and styled from the pywal template. The toggles run [`control-center.sh`](../scripts/control-center.sh).

## Status bar

Waybar's config is generated from [`.config/wal/templates/waybar-config.jsonc`](../.config/wal/templates/waybar-config.jsonc). Settings → toolbar can show or hide modules (including the optional weather, network speed, and CPU & memory ones), set the weather location, move the bar, change its height, and switch the clock format.

| Module | Click | Other |
| --- | --- | --- |
| Now playing | Play / pause | The song from any player; right-click skips, middle-click goes back; hidden when nothing is playing |
| Clock | Notification center | |
| Timers | Cancel a timer | Counts down the soonest timer or reminder; hidden when there are none |
| Stay awake | Turns stay awake off | Only shown while stay awake is on |
| Notifications | Toggle do not disturb | |
| Tray arrow | Expands the tray | Only shown when an app has a tray icon |
| Coding agents | Usage menu for Claude Code, Codex, and opencode | Right-click refreshes account limits |
| Bluetooth, Wi-Fi, Tailscale | Fuzzel menus to connect, pick devices, and copy IPs | |
| Volume | Output and input menu | Scroll changes volume, right-click mutes, middle-click opens pavucontrol |
| Battery | Power menu (lock, log out, reboot, shut down) | Shows the percentage; right-click hides or shows it (remembered across reboots); the tooltip shows time left |
| Weather (optional) | | Temperature and conditions; the tooltip has a 3-day forecast |
| Network speed (optional) | | Download and upload speed of the active connection |
| CPU & memory (optional) | Opens btop | Turns yellow when the CPU is busy |
