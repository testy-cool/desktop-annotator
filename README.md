# Desktop Annotator

Capture a selected piece of text from any application on a Linux Mint X11
desktop, add a comment, and save the pair as Markdown.

## Use

1. Select text in a browser, editor, PDF viewer, terminal, or another app.
2. Press `Ctrl+Alt+A`.
3. Write a comment in the popup.
4. Press `Ctrl+Enter` to save, or `Esc` to cancel.

Annotations are appended to `~/Annotations/YYYY-MM-DD.md`:

```markdown
## 16:42 · Firefox — Agent response

> The selected text appears here.

→ The comment appears here.
```

The annotation directory and files are created with private user-only
permissions. Set `ANNOTATIONS_DIR` to use a different directory.

## How capture works

On X11, selecting text usually publishes it to the `PRIMARY` selection. The
tool reads that selection only when launched. If it is empty, the tool briefly
uses `Ctrl+C`, reads the clipboard, and restores the clipboard's previous
contents. It does not run continuously or monitor typing.

## Requirements

- Python 3 with PyGObject and GTK 3
- `xclip`
- `xdotool`
- `zenity` for the no-selection warning

The launcher must use the system Python (`/usr/bin/python3`) on this Mint host,
because that interpreter has the GTK bindings installed.

## Current local installation

The executable is linked at `~/.local/bin/desktop-annotator`, and Cinnamon
custom shortcut `custom12` binds it to `Ctrl+Alt+A`.

To run it directly:

```bash
/home/testycool/.local/bin/desktop-annotator
```

To remove the local integration, delete the launcher link and remove
`custom12` in Cinnamon's Keyboard settings under Custom Shortcuts.

## Tests

```bash
/usr/bin/python3 -m unittest discover -v
```
