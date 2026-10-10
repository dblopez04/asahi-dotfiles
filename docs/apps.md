# Apps

Spotlight, Quick Look, Taildrop, screenshots, the emoji picker, and clipboard history. [Settings](settings.md), the [wallpaper picker](theming.md), and [Walwrite](walwrite.md) have their own pages.

## Spotlight

`Super+Space` opens a search box in the middle of the screen, like Spotlight on macOS. Start typing to find:

- **Apps:** by name, description, or keywords. The ones you open most rank higher, and they're what you see before you type.
- **Settings pages:** like "trackpad" or "tailscale".
- **Commands:** lock, sleep, log out, restart, shut down, stay awake, do not disturb, clipboard history, the wallpaper picker, and more. Log out, restart and shut down ask you to press `Enter` twice.
- **Files and folders** in your home folder, from the `plocate` index (refreshed daily), plus recently opened files.
- **Math:** `2^10`, `sqrt(144)*2`, `15% * 200`. `Enter` copies the answer.
- **Conversions:** units (`5 km in miles`, `3 cups in ml`, `2.5 gb in mib`), temperature (`72f to c`), currency (`20 usd to eur`, with daily rates), and time zones (`time in tokyo`, `3pm in london`). `Enter` copies the answer.
- **Timers and reminders:** `timer 25m`, `timer 1h30m tea`, `remind me in 20m to stretch`, `remind me at 5pm to call mom`. They count down in the bar and notify you when they're done, and they survive logging out.
- **The web:** the last result always searches DuckDuckGo.

Use the arrows to pick, `Enter` to open, `Ctrl+Y` to [Quick Look](#quick-look) a file, `Ctrl+T` to send a file with [Taildrop](#taildrop), and `Ctrl+Enter` to show a file in its folder. `Esc` or clicking away closes it.

### Browsing folders

Type `~` or `/` (or pick "browse files") to look through folders instead of searching:

- **Moving around:** `Tab` or `Enter` goes into the selected folder, and `Shift+Tab` (or the `..` row) goes up.
- **Filtering:** anything typed after the last `/` filters the folder. Folders come first, and hidden files show once you type a leading `.`.
- **Opening:** `Enter` opens a file in its app, `Ctrl+Y` previews it with Quick Look, and `Ctrl+Enter` opens the folder (or shows the file) in the file manager.
- **From search:** `Tab` on any file or folder result starts browsing right there.

## Quick Look

A fast preview of a file without opening an app, like Space in Finder. Press `Ctrl+Y` on a file in Spotlight, or run `quicklook.py FILE`.

- **Previews:** images, text and code, PDFs (the first pages, with `poppler-utils`), video and audio (plays right away), and folders (their contents). Anything else shows its type and details.
- **Keys:** `←`/`→` step through the other files in the same folder, `Enter` opens the file in its app, and `Esc` or `Space` closes. The buttons at the top open the file or show it in its folder.
- **Back to Spotlight:** closing a preview you opened from Spotlight (`Esc`, `Space`, or ×) brings Spotlight back where you were, with the file you ended on selected. Opening the file or its folder doesn't.

## Taildrop

Send files to your other Tailscale devices: `Ctrl+T` on a file in Spotlight, the **send** button (or `t`) in Quick Look, or `taildrop.py send FILE…`. Pick a device from the list of online ones and you get a notification when it arrives. Files sent to this Mac land in `~/Downloads` automatically (the `taildrop-receive` user service).

Taildrop needs Tailscale connected and you as its operator: Settings → tailscale → allow changes without sudo.

## Screenshots and colors

Screenshots are saved to `~/Screenshots` and copied. Click the notification to mark one up in Swappy (arrows, text, highlights, blur); if you don't, it simply stays copied. `Super+Shift+P` picks the color of any pixel, copies its hex code, and shows a swatch.

## Emoji picker

`Super+Ctrl+Space` opens a grid of emoji by category, like the macOS picker, with the ones you use most on top. Type to search by name or keyword ("thumbs", "lol", "party"), move with the arrows, and press `Enter` (or click): the emoji is typed into the window you were in and copied to the clipboard. `Tab` and `Shift+Tab` jump between categories, the icons along the bottom do the same, and `Shift+Enter` or a right-click picks a skin tone. The grid remembers the tone you used last. Drag the window by any empty spot. It stays open until you pick an emoji or press `Esc`; pressing `Super+Ctrl+Space` again brings it back to the front.

Emoji are drawn with Noto Color Emoji. For Twemoji or OpenMoji instead, install `twitter-twemoji-fonts` or `hfg-gmuend-openmoji-color-fonts` and prefer it in `~/.config/fontconfig/fonts.conf`:

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias binding="same"><family>emoji</family><prefer><family>Twemoji</family></prefer></alias>
</fontconfig>
```

Emoji the font can't draw (Twemoji stops at Unicode 14) are left out of the picker.

## Clipboard history

Everything you copy, text and images, is kept so you can paste it again. `Super+Ctrl+V` (or "clipboard history" in Spotlight) lists recent copies in fuzzel; pick one to copy it again, or clear the history from the bottom of the list.

[`clipboard-history.py`](../scripts/clipboard-history.py) keeps the newest 200 copies, up to 100 MB, as private files in `~/.local/share/clipboard-history`. Copies that password managers mark as sensitive aren't recorded.
