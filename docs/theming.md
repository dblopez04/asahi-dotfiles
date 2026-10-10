# Wallpapers and colors

## Wallpaper picker

`Super+P` opens the wallpaper picker, which is also Settings → wallpaper and Wallpaper Picker in the launcher:

- **Browsing:** type to filter, use the arrows to move, and press `Enter` to pick. `Tab` switches between `~/wallpapers` and the [dharmx/walls](https://github.com/dharmx/walls) gallery, which downloads a pick into `~/wallpapers`.
- **Picking:** a pick becomes the wallpaper as an unsaved change and themes the whole desktop. The window stays open so you can try others. **Save** keeps the wallpaper, **undo** goes back.

Picking the current wallpaper again re-runs the theming.

### Where the gallery comes from

The gallery tab browses [dharmx/walls](https://github.com/dharmx/walls), a community wallpaper collection on GitHub; the link at the bottom of its category list (in the picker and in Settings → wallpaper) opens the repo. Thumbnails are resized through the images.weserv.nl proxy, and a wallpaper is downloaded into `~/wallpapers` only when you pick it.

## Theming from any image

To theme from any image without changing the wallpaper:

```sh
wal.sh ~/Pictures/some-image.jpg
```

[`wal.sh`](../scripts/wal.sh):

1. Generates a pywal palette with the backend in [`.config/wal/backend`](../.config/wal/backend) (`colorz` by default; set in Settings → appearance, or override with `WAL_BACKEND=wal wal.sh IMAGE`).
2. Reloads Sway, which redraws the window borders and restarts Waybar.
3. Rebuilds the Oomox GTK 3 theme and copies the generated GTK 4/libadwaita colors into `~/.config/gtk-4.0`.
4. Switches the GTK theme away and back, so open GTK 3 apps repaint.
5. Restarts SwayOSD, reloads SwayNC, and updates btop and Firefox (Pywalfox).

Kitty, Fuzzel, Neovim, swaylock, Walwrite, Settings, and the picker all read the palette themselves. Kitty and the apps recolor while running; Fuzzel, Neovim, and swaylock pick it up the next time they start.

Open GTK 4 apps like Nautilus keep their old colors until they're reopened. `wal.sh` quits Nautilus's background process when no Nautilus window is open.

## Templates

Customize the generated styles by editing the templates in [`.config/wal/templates`](../.config/wal/templates):

- `gtk.css` holds the GTK 4 and libadwaita colors. It keeps popovers transparent outside their menu, so right-click menus in apps like Nautilus don't paint a box over the window.
- `colors-oomox` sets up the GTK 3 theme.
- The others cover Waybar, SwayNC, and swaylock.

The generated `.config/gtk-4.0/gtk.css` and `gtk-dark.css` are ignored by Git.
