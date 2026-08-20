from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Callable


def _read_x_selection(selection: str) -> str:
    try:
        result = subprocess.run(
            ["xclip", "-selection", selection, "-out"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def read_primary_selection() -> str:
    return _read_x_selection("primary")


def _write_clipboard(text: str) -> bool:
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-in"],
            input=text,
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def copy_focused_selection() -> str:
    previous = _read_x_selection("clipboard")
    sentinel = f"desktop-annotator-{uuid.uuid4()}"
    if not _write_clipboard(sentinel):
        return ""

    try:
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+c"],
            check=False,
            capture_output=True,
            timeout=1,
        )
        time.sleep(0.18)
        copied = _read_x_selection("clipboard")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        copied = ""
    finally:
        _write_clipboard(previous)

    return "" if copied == sentinel else copied


def capture_selected_text(
    primary_reader: Callable[[], str] | None = None,
    clipboard_copy: Callable[[], str] | None = None,
) -> str:
    primary_reader = primary_reader or read_primary_selection
    clipboard_copy = clipboard_copy or copy_focused_selection
    selected = primary_reader().strip()
    if selected:
        return selected
    return clipboard_copy().strip()


def active_window_title() -> str:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "Unknown window"
    title = result.stdout.strip()
    return title if result.returncode == 0 and title else "Unknown window"
