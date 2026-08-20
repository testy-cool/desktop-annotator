from __future__ import annotations

import os
import subprocess
from pathlib import Path

from desktop_annotator.capture import active_window_title, capture_selected_text
from desktop_annotator.workflow import save_comment


def _load_gtk():
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, Pango

    return Gdk, Gtk, Pango


def _show_no_selection_message() -> None:
    try:
        subprocess.run(
            [
                "zenity",
                "--warning",
                "--title=Desktop Annotator",
                "--text=Select some text, then press the annotation shortcut again.",
                "--width=420",
            ],
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def show_annotation_popup(*, quote: str, source: str, directory: Path) -> Path | None:
    Gdk, Gtk, Pango = _load_gtk()

    class AnnotationWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title="Desktop Annotator")
            self.saved_path: Path | None = None
            self.set_default_size(620, 430)
            self.set_position(Gtk.WindowPosition.MOUSE)
            self.set_keep_above(True)
            self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
            self.set_border_width(18)
            self.connect("destroy", Gtk.main_quit)
            self.connect("key-press-event", self._on_key_press)

            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(layout)

            title = Gtk.Label()
            title.set_markup("<b>Comment on this selection</b>")
            title.set_halign(Gtk.Align.START)
            layout.pack_start(title, False, False, 0)

            source_label = Gtk.Label(label=source)
            source_label.set_halign(Gtk.Align.START)
            source_label.set_ellipsize(Pango.EllipsizeMode.END)
            source_label.get_style_context().add_class("dim-label")
            layout.pack_start(source_label, False, False, 0)

            quote_scroll = Gtk.ScrolledWindow()
            quote_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            quote_scroll.set_min_content_height(120)
            quote_scroll.set_max_content_height(170)
            quote_scroll.set_shadow_type(Gtk.ShadowType.IN)
            quote_view = Gtk.TextView()
            quote_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            quote_view.set_editable(False)
            quote_view.set_cursor_visible(False)
            quote_view.set_left_margin(10)
            quote_view.set_right_margin(10)
            quote_view.set_top_margin(8)
            quote_view.set_bottom_margin(8)
            quote_view.get_buffer().set_text(quote)
            quote_scroll.add(quote_view)
            layout.pack_start(quote_scroll, True, True, 0)

            prompt = Gtk.Label(label="Your comment")
            prompt.set_halign(Gtk.Align.START)
            layout.pack_start(prompt, False, False, 0)

            comment_scroll = Gtk.ScrolledWindow()
            comment_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            comment_scroll.set_min_content_height(105)
            comment_scroll.set_shadow_type(Gtk.ShadowType.IN)
            self.comment_view = Gtk.TextView()
            self.comment_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            self.comment_view.set_left_margin(10)
            self.comment_view.set_right_margin(10)
            self.comment_view.set_top_margin(8)
            self.comment_view.set_bottom_margin(8)
            comment_scroll.add(self.comment_view)
            layout.pack_start(comment_scroll, True, True, 0)

            footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.status = Gtk.Label(label="Ctrl+Enter saves · Esc cancels")
            self.status.set_halign(Gtk.Align.START)
            self.status.get_style_context().add_class("dim-label")
            footer.pack_start(self.status, True, True, 0)

            cancel = Gtk.Button(label="Cancel")
            cancel.connect("clicked", lambda _button: self.close())
            footer.pack_start(cancel, False, False, 0)

            save = Gtk.Button(label="Save annotation")
            save.get_style_context().add_class("suggested-action")
            save.connect("clicked", self._save)
            footer.pack_start(save, False, False, 0)
            layout.pack_start(footer, False, False, 0)

        def _comment(self) -> str:
            buffer = self.comment_view.get_buffer()
            return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

        def _save(self, _button=None) -> None:
            try:
                self.saved_path = save_comment(
                    quote=quote,
                    comment=self._comment(),
                    source=source,
                    directory=directory,
                )
            except ValueError:
                self.status.set_text("Write a comment before saving.")
                self.comment_view.grab_focus()
                return
            self.close()

        def _on_key_press(self, _widget, event):
            if event.keyval == Gdk.KEY_Escape:
                self.close()
                return True
            if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                if event.state & Gdk.ModifierType.CONTROL_MASK:
                    self._save()
                    return True
            return False

    window = AnnotationWindow()
    window.show_all()
    window.comment_view.grab_focus()
    window.present()
    Gtk.main()
    return window.saved_path


def main() -> int:
    source = active_window_title()
    quote = capture_selected_text()
    if not quote:
        _show_no_selection_message()
        return 1

    directory = Path(os.environ.get("ANNOTATIONS_DIR", "~/Annotations")).expanduser()
    show_annotation_popup(quote=quote, source=source, directory=directory)
    return 0

