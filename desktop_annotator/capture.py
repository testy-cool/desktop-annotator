from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass


# The marker written to the clipboard while asking an application to copy. The
# restore afterwards can lose a race with X selection ownership, so a marker
# occasionally outlives the run that wrote it and must never be offered back as
# if the user had copied it.
SENTINEL_PREFIX = "desktop-annotator-"

COPY_RESPONSE_TIMEOUT = 0.18
COPY_POLL_INTERVAL = 0.008


@dataclass(frozen=True)
class TextCandidate:
    label: str
    text: str


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


def read_clipboard_selection() -> str:
    return _read_x_selection("clipboard")


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


def _send_copy_keystroke() -> None:
    subprocess.run(
        ["xdotool", "key", "--clearmodifiers", "ctrl+c"],
        check=False,
        capture_output=True,
        timeout=1,
    )


def _await_copied_text(
    sentinel: str,
    *,
    clipboard_reader: Callable[[], str],
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> str:
    """Wait only as long as the focused application actually needs.

    The clipboard still holds the sentinel until the application answers the
    keystroke, so anything else means the copy landed. An empty read is treated
    as "not yet" rather than as an answer, because xclip also returns empty
    while ownership is changing hands.
    """
    deadline = monotonic() + COPY_RESPONSE_TIMEOUT
    while True:
        copied = clipboard_reader()
        if copied and copied != sentinel:
            return copied
        if monotonic() >= deadline:
            return ""
        sleep(COPY_POLL_INTERVAL)


def copy_focused_selection(
    *,
    clipboard_reader: Callable[[], str] | None = None,
    clipboard_writer: Callable[[str], bool] | None = None,
    key_sender: Callable[[], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> str:
    clipboard_reader = clipboard_reader or read_clipboard_selection
    clipboard_writer = clipboard_writer or _write_clipboard
    key_sender = key_sender or _send_copy_keystroke

    previous = clipboard_reader()
    sentinel = f"{SENTINEL_PREFIX}{uuid.uuid4()}"
    if not clipboard_writer(sentinel):
        return ""

    try:
        key_sender()
        copied = _await_copied_text(
            sentinel,
            clipboard_reader=clipboard_reader,
            sleep=sleep,
            monotonic=monotonic,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        copied = ""
    finally:
        clipboard_writer(previous)

    return copied


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


def _without_own_marker(text: str) -> str:
    return "" if text.startswith(SENTINEL_PREFIX) else text


def capture_text_candidates(
    primary_reader: Callable[[], str] | None = None,
    clipboard_reader: Callable[[], str] | None = None,
    clipboard_copy: Callable[[], str] | None = None,
) -> list[TextCandidate]:
    primary_reader = primary_reader or read_primary_selection
    clipboard_reader = clipboard_reader or read_clipboard_selection
    clipboard_copy = clipboard_copy or copy_focused_selection

    clipboard = _without_own_marker(clipboard_reader().strip())
    selection = _without_own_marker(primary_reader().strip())
    if not selection:
        selection = _without_own_marker(clipboard_copy().strip())

    candidates = []
    if selection:
        candidates.append(TextCandidate(label="Selected text", text=selection))
    if clipboard and clipboard != selection:
        candidates.append(TextCandidate(label="Clipboard", text=clipboard))
    return candidates


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
