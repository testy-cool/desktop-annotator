# Rust + Slint implementation

An alternative front end for the same `~/Annotations/annotations.md` file. The
Python app is untouched and still owns `Ctrl+Alt+A`.

## Build and run

    cargo build --release
    ./target/release/desktop-annotator

`ANNOTATIONS_DIR` overrides the directory, as in the Python version.

## Editing the UI

`slint-viewer --check ui/popup.slint` compiles and reports errors in about
50ms, far quicker than a cargo build. `slint-viewer --auto-reload ui/popup.slint`
gives a live preview that repaints on save, with no build step at all. The
`in property` defaults exist so that preview shows realistic content.

Only `src/*.rs` changes need `cargo build`.

## What is deliberately missing

There is no List tab. The GTK version keeps every annotation in one editable
buffer with dim, non-editable labels interleaved between entries, which relies
on GTK text tags and has to parse the edited text back into entries. Slint has
no equivalent rich-text buffer.

Instead `Ctrl+O` opens `annotations.md` in `$VISUAL`, `$EDITOR`, `subl` or
`xdg-open`. Reviewing and editing history happens in a real editor.

## Why xrandr and xdotool

Slint exposes `set_position` but no monitor enumeration, so the monitor layout
comes from `xrandr --listmonitors` and the pointer from `xdotool
getmouselocation`. Both are parsed in `screen.rs` against captured real output,
so the formats are covered by tests. This is the X11-only part.

## Keyboard focus

Muffin does not hand this window keyboard focus by itself, so Slint would draw a
blinking caret in a window that never receives a key event. Slint cannot ask the
window manager for activation, so `activate_own_window` does it through X11.

Two traps, both found by measurement rather than reading:

- The window is findable by `xdotool search` roughly 25ms before the window
  manager has finished managing it. Activating in that gap fails with
  `XGetWindowProperty[_NET_WM_DESKTOP] failed`.
- `xdotool windowactivate` exits 0 even when it silently fails that way.

So the only trustworthy signal is whether focus actually moved. The code retries
until `getwindowfocus` reports our own window.

`ANNOT_FRAMED=1` gives the window normal decorations, which also restores the
close button and resizing. Focus works either way; framing was ruled out as the
cause.

## Testing this

A bare Xvfb has no window manager, so activation cannot succeed there and typing
never reaches the window. Run one in the harness:

    Xvfb :87 -screen 0 1400x900x24 &
    DISPLAY=:87 metacity &

Never drive the real display with `xdotool type`. If the popup does not hold
focus, the keystrokes go into whatever application does.
