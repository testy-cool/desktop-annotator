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
