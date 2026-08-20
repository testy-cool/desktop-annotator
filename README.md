# Desktop Annotator

Capture selected or copied text from any application on a Linux Mint X11
desktop, add comments, and keep them in one editable Markdown list.

## Use

1. Select or copy text in a browser, editor, PDF viewer, terminal, or another app.
2. Press `Ctrl+Alt+A`.
3. Choose `Selected text` or `Clipboard` when both are available. `Ctrl+1`
   and `Ctrl+2` switch between them.
4. Write a comment and press `Ctrl+Enter` to add it. The popup closes
   immediately after saving.
5. To review the accumulated annotations later, open the tool again and choose
   the List tab or press `Ctrl+L`. Edit any quote or comment, then press
   `Ctrl+Enter` or `Save edits`.

Annotations are appended to `~/Annotations/annotations.md`:

```markdown
## 2026-08-20 16:42 · Firefox — Agent response

> The selected text appears here.

→ The comment appears here.
```

The annotation directory and files are created with private user-only
permissions. Set `ANNOTATIONS_DIR` to use a different directory.

In the List tab, timestamps and source-window names are dim, display-only
labels embedded between entries. They cannot be selected or edited. All quotes
and comments live in one continuous editable text area. `Copy all` copies only
that text, without timestamps or source metadata. `Open in Sublime` (or
`Ctrl+O`) saves current edits, opens `annotations.md` with the installed `subl`
command, and closes the popup.

On first use, existing daily files such as `2026-08-20.md` are copied into the
continuous list. The original daily files remain untouched as backups.

## How capture works

On X11, selecting text usually publishes it to the `PRIMARY` selection. The
tool reads both that selection and the live `CLIPBOARD` only when launched. If
PRIMARY is empty, it briefly uses `Ctrl+C` to cover applications that do not
publish PRIMARY, then restores the clipboard's previous contents. It does not
run continuously or monitor typing.

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
