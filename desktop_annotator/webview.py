"""An HTML front end for the annotator, hosted in a WebKitGTK window.

The whole interface lives in ``ui/index.html``. Python captures the text,
reads and writes ``annotations.md``, and owns the window. Everything the
user sees and clicks is HTML, so changing the interface never needs a
rebuild.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import (
    Annotation,
    DocumentSnapshot,
    load_document,
)
from desktop_annotator.capture import TextCandidate
from desktop_annotator.positioning import MonitorRect, popup_position
from desktop_annotator.workflow import annotation_source, save_comment, save_edited_annotations


WINDOW_WIDTH = 760
WINDOW_HEIGHT = 640
STAMP_FORMAT = "%Y-%m-%d %H:%M"
UI_FILE = Path(__file__).with_name("ui") / "index.html"


def entries_payload(annotations: list[Annotation]) -> list[dict]:
    """The list the interface renders, newest entry first."""
    return [
        {
            "stamp": f"{annotation.captured_at:{STAMP_FORMAT}}",
            "source": annotation.source,
            "quote": annotation.quote,
            "comment": annotation.comment,
        }
        for annotation in reversed(annotations)
    ]


def annotations_from_payload(payload: list[dict]) -> list[Annotation]:
    """Turn the edited list back into file order, oldest entry first."""
    annotations = []
    for entry in reversed(payload):
        quote = entry.get("quote", "").strip()
        comment = entry.get("comment", "").strip()
        if not quote or not comment:
            raise ValueError("every entry needs a quote and a comment")
        annotations.append(
            Annotation(
                quote=quote,
                comment=comment,
                source=entry.get("source", "") or "Unknown window",
                captured_at=datetime.strptime(entry["stamp"], STAMP_FORMAT),
            )
        )
    return annotations


def build_state(
    *,
    candidates: list[TextCandidate],
    source: str,
    annotations: list[Annotation],
    now: datetime | None = None,
    save_problem: str = "",
) -> dict:
    stamp = (now or datetime.now()).strftime(STAMP_FORMAT)
    return {
        "source": source,
        "stamp": stamp,
        "candidates": [{"label": item.label, "text": item.text} for item in candidates],
        "entries": entries_payload(annotations),
        "saveProblem": save_problem,
    }


def page_with_state(html: str, state: dict) -> str:
    """Hand the interface its starting state without a round trip."""
    payload = json.dumps(state).replace("</", "<\\/")
    return html.replace("<script>", f"<script>window.__STATE__={payload};</script>\n<script>", 1)


def _launch_sublime(path: Path) -> None:
    subprocess.Popen(
        ["subl", "--", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _monitor_rects(display) -> list[MonitorRect]:
    rects = []
    for index in range(display.get_n_monitors()):
        geometry = display.get_monitor(index).get_geometry()
        rects.append(
            MonitorRect(
                x=geometry.x, y=geometry.y, width=geometry.width, height=geometry.height
            )
        )
    return rects


class AnnotatorWindow:
    def __init__(self, *, candidates, source, directory, gtk, gdk, webkit, glib):
        self.Gtk, self.Gdk, self.WebKit2, self.GLib = gtk, gdk, webkit, glib
        self.candidates = candidates
        self.source = source
        self.directory = directory
        self.saved_path: Path | None = None

        self.window = gtk.Window(title="Annotate")
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window.set_size_request(640, 560)
        self.window.set_decorated(False)
        self.window.set_skip_taskbar_hint(False)
        self.window.connect("destroy", gtk.main_quit)

        manager = webkit.UserContentManager()
        manager.register_script_message_handler("host")
        manager.connect("script-message-received::host", self._on_message)

        self.view = webkit.WebView.new_with_user_content_manager(manager)
        self.view.set_background_color(self._rgba(0.11, 0.11, 0.11, 1.0))
        settings = self.view.get_settings()
        settings.set_enable_developer_extras(bool(os.environ.get("ANNOTATOR_DEVTOOLS")))
        settings.set_enable_write_console_messages_to_stdout(True)
        self.window.add(self.view)

        try:
            self.document = load_document(directory)
        except (OSError, ValueError) as error:
            self.document = DocumentSnapshot(
                directory / "annotations.md", None, (), (f"Could not load annotations: {error}",)
            )
        state = build_state(
            candidates=candidates, source=source, annotations=self.document.entries,
            save_problem=self.document.save_problem,
        )
        self.view.load_html(page_with_state(UI_FILE.read_text(encoding="utf-8"), state), "file:///")

    def _rgba(self, red, green, blue, alpha):
        colour = self.Gdk.RGBA()
        colour.red, colour.green, colour.blue, colour.alpha = red, green, blue, alpha
        return colour

    # ----- host side of the bridge -------------------------------------

    def _to_page(self, message: dict) -> None:
        script = f"window.fromHost({json.dumps(message)})"
        self.view.evaluate_javascript(script, -1, None, None, None, None, None)

    def _reload_entries(self, status: str) -> None:
        try:
            document = load_document(self.directory)
        except (OSError, ValueError) as error:
            self._to_page({"kind": "error", "pane": "list", "status": str(error)})
            return
        self.document = document
        self._send_document(status)

    def _send_document(self, status: str) -> None:
        self._to_page({
            "kind": "entries", "entries": entries_payload(self.document.entries),
            "saveProblem": self.document.save_problem, "status": status,
        })

    def _on_message(self, _manager, result) -> None:
        try:
            message = json.loads(result.get_js_value().to_string())
        except (AttributeError, ValueError):
            return
        handler = getattr(self, "_do_" + message.get("action", ""), None)
        if handler is not None:
            handler(message)

    def _do_close(self, _message) -> None:
        self.window.close()

    def _do_minimise(self, _message) -> None:
        self.window.iconify()

    def _do_drag(self, _message) -> None:
        x, y = self._pointer()
        self.window.begin_move_drag(1, x, y, self.Gtk.get_current_event_time())

    def _do_resize(self, _message) -> None:
        x, y = self._pointer()
        self.window.begin_resize_drag(
            self.Gdk.WindowEdge.SOUTH_EAST, 1, x, y, self.Gtk.get_current_event_time()
        )

    def _pointer(self) -> tuple[int, int]:
        seat = self.Gdk.Display.get_default().get_default_seat()
        _screen, x, y = seat.get_pointer().get_position()
        return x, y

    def _do_copy(self, message) -> None:
        clipboard = self.Gtk.Clipboard.get(self.Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(message.get("text", ""), -1)
        clipboard.store()

    def _do_add(self, message) -> None:
        try:
            self.saved_path = save_comment(
                quote=message.get("quote", ""),
                comment=message.get("comment", ""),
                source=annotation_source(message.get("label", ""), self.source),
                directory=self.directory,
            )
        except (ValueError, OSError) as error:
            self._to_page({"kind": "error", "pane": "add", "status": str(error)})
            return
        self.window.close()

    def _do_save(self, message) -> None:
        try:
            annotations = annotations_from_payload(message.get("entries", []))
            document = save_edited_annotations(annotations, self.directory, expected=self.document)
        except (ValueError, KeyError, OSError) as error:
            self._to_page({"kind": "error", "pane": "list", "status": str(error)})
            return
        self.document = document
        self.saved_path = document.path
        self._send_document(f"Saved {len(annotations)} entries.")

    def _do_revert(self, _message) -> None:
        self._reload_entries("Reverted to the saved file.")

    def _do_sublime(self, _message) -> None:
        path = self.directory / "annotations.md"
        try:
            _launch_sublime(path)
        except OSError:
            self._to_page(
                {"kind": "error", "pane": "list", "status": "Could not run the subl command."}
            )
            return
        # Keep unsaved browser edits available while the original file is open.

    # ----- showing it ---------------------------------------------------

    def place_on_right_monitor(self) -> None:
        display = self.Gdk.Display.get_default()
        if display is None or display.get_n_monitors() == 0:
            return
        seat = display.get_default_seat()
        if seat is None or seat.get_pointer() is None:
            return
        pointer_x, pointer_y = self._pointer()
        x, y = popup_position(
            _monitor_rects(display),
            pointer_x=pointer_x,
            pointer_y=pointer_y,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )
        self.window.move(x, y)

    def present(self) -> None:
        self.window.show_all()
        self.window.present_with_time(self.Gtk.get_current_event_time())
        self.view.grab_focus()


def show_annotation_popup(
    *, candidates, source: str, directory: Path, toggle_instance=None
) -> Path | None:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GLib, Gtk, WebKit2

    window = AnnotatorWindow(
        candidates=candidates,
        source=source,
        directory=directory,
        gtk=Gtk,
        gdk=Gdk,
        webkit=WebKit2,
        glib=GLib,
    )

    if toggle_instance is not None:
        closed = False

        def request_close():
            nonlocal closed
            closed = True
            GLib.idle_add(window.window.close)

        toggle_instance.set_toggle_callback(request_close)
        if closed:
            return None

    window.place_on_right_monitor()
    window.present()
    Gtk.main()
    return window.saved_path
