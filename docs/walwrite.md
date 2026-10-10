# Walwrite

A Markdown and plain-text editor in the pywal colors, opened with `Super+Shift+W`, `walwrite FILE…`, or the launcher.

- **Documents:** open several files at once. The sidebar (`Ctrl+\`) lists open documents and a folder's text files (`Ctrl+Shift+O` picks the folder).
- **Saving:** saved files autosave a moment after each edit and when you leave the window. Untitled documents are kept as drafts, so closing never loses text. The files you had open come back the next time it starts.
- **Markdown:** syntax is highlighted with dimmed markers. Return continues lists (and ends them on an empty item), and `Tab`/`Shift+Tab` indent list items.
- **Preview:** `Ctrl+E` shows the rendered Markdown and `Ctrl+Shift+E` shows it side by side. The preview uses WebKitGTK and python-markdown when they're installed, and a simpler built-in renderer otherwise.
- **Menus:** press `Alt` for the File, Edit, Format, View, and Help menus. `Ctrl+?` lists every shortcut.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` / `Ctrl+Shift+N` | New document / new window |
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | Open / save / save as |
| `Ctrl+W` | Close the document |
| `Ctrl+Tab` or `Ctrl+PageDown`, `Ctrl+Shift+Tab` or `Ctrl+PageUp` | Next / previous document |
| `Ctrl+F` / `Ctrl+H` | Find / replace |
| `Ctrl+B` / `Ctrl+I` / `Ctrl+K` / `` Ctrl+` `` | Bold / italic / link / inline code |
| `Ctrl+1…3` | Heading level (press again to remove) |
| `Ctrl+=` / `Ctrl+-` / `Ctrl+0` | Text size |
| `Ctrl+Alt+=` / `Ctrl+Alt+-` / `Ctrl+Alt+0` | Interface size (sidebar, footer, menus, and dialogs) |
| `Ctrl+P` | Print |
| `F11` | Fullscreen |

Pasting a URL over selected text turns it into a link. Drafts and the session are stored in `~/.local/state/walwrite`.
