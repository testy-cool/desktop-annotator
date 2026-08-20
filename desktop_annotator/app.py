from __future__ import annotations

import os
import subprocess
from pathlib import Path

from desktop_annotator.annotation import (
    Annotation,
    load_annotation_list,
    parse_annotation_list,
    parse_editable_body,
    render_editable_body,
)
from desktop_annotator.capture import TextCandidate, active_window_title, capture_text_candidates
from desktop_annotator.workflow import (
    annotation_source,
    save_comment,
    save_edited_annotations,
)


def _load_gtk():
    import gi

    gi.require_version("Gdk", "3.0")
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
                "--text=Select or copy some text, then press the annotation shortcut again.",
                "--width=420",
            ],
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _close_after_successful_add(window) -> None:
    window.close()


def _show_list_page(notebook) -> None:
    notebook.set_current_page(1)


def _build_sublime_command(path: Path) -> list[str]:
    return ["subl", "--", str(path)]


def _launch_sublime(path: Path) -> None:
    subprocess.Popen(
        _build_sublime_command(path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _insert_marked_text(buffer, text: str, separator: str):
    start_mark = buffer.create_mark(None, buffer.get_end_iter(), True)
    buffer.insert(buffer.get_end_iter(), text)
    end_offset = buffer.get_char_count()
    buffer.insert(buffer.get_end_iter(), separator)
    end_mark = buffer.create_mark(None, buffer.get_iter_at_offset(end_offset), False)
    return start_mark, end_mark


def show_annotation_popup(
    *, candidates: list[TextCandidate], source: str, directory: Path
) -> Path | None:
    Gdk, Gtk, Pango = _load_gtk()

    class AnnotationWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title="Desktop Annotator")
            self.saved_path: Path | None = None
            self.entry_marks = []
            self.set_default_size(720, 620)
            self.set_position(Gtk.WindowPosition.MOUSE)
            self.set_keep_above(True)
            self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
            self.set_border_width(14)
            self.connect("destroy", Gtk.main_quit)
            self.connect("key-press-event", self._on_key_press)

            self.notebook = Gtk.Notebook()
            self.add(self.notebook)
            self._build_add_page()
            self._build_list_page()
            self._reload_list()
            self._install_accelerators()

        def _install_accelerators(self):
            accelerators = Gtk.AccelGroup()
            self.add_accel_group(accelerators)
            accelerators.connect(
                Gdk.KEY_l,
                Gdk.ModifierType.CONTROL_MASK,
                Gtk.AccelFlags.VISIBLE,
                self._open_list_accelerator,
            )
            accelerators.connect(
                Gdk.KEY_o,
                Gdk.ModifierType.CONTROL_MASK,
                Gtk.AccelFlags.VISIBLE,
                self._open_sublime_accelerator,
            )

        def _open_list_accelerator(self, *_args):
            _show_list_page(self.notebook)
            self.list_view.grab_focus()
            return True

        def _open_sublime_accelerator(self, *_args):
            if self.notebook.get_current_page() == 1:
                self._open_in_sublime()
                return True
            return False

        def _text_view(self, text: str = "", *, editable: bool = True):
            view = Gtk.TextView()
            view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            view.set_editable(editable)
            view.set_cursor_visible(editable)
            view.set_left_margin(10)
            view.set_right_margin(10)
            view.set_top_margin(8)
            view.set_bottom_margin(8)
            view.get_buffer().set_text(text)
            return view

        def _scroll_for(self, child, *, minimum_height: int):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_min_content_height(minimum_height)
            scroll.set_shadow_type(Gtk.ShadowType.IN)
            scroll.add(child)
            return scroll

        def _build_add_page(self):
            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            layout.set_border_width(14)
            self.notebook.append_page(layout, Gtk.Label(label="Add"))

            title = Gtk.Label()
            title.set_markup("<b>Add to the annotation list</b>")
            title.set_halign(Gtk.Align.START)
            layout.pack_start(title, False, False, 0)

            source_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            source_row.pack_start(Gtk.Label(label="Use"), False, False, 0)
            self.candidate_picker = Gtk.ComboBoxText()
            for candidate in candidates:
                self.candidate_picker.append_text(candidate.label)
            self.candidate_picker.set_active(0)
            self.candidate_picker.connect("changed", self._candidate_changed)
            source_row.pack_start(self.candidate_picker, False, False, 0)
            self.source_label = Gtk.Label(label=source)
            self.source_label.set_halign(Gtk.Align.START)
            self.source_label.set_ellipsize(Pango.EllipsizeMode.END)
            self.source_label.get_style_context().add_class("dim-label")
            source_row.pack_start(self.source_label, True, True, 0)
            layout.pack_start(source_row, False, False, 0)

            self.quote_view = self._text_view(candidates[0].text, editable=False)
            quote_scroll = self._scroll_for(self.quote_view, minimum_height=150)
            quote_scroll.set_max_content_height(210)
            layout.pack_start(quote_scroll, True, True, 0)

            prompt = Gtk.Label(label="Your comment")
            prompt.set_halign(Gtk.Align.START)
            layout.pack_start(prompt, False, False, 0)

            self.comment_view = self._text_view()
            comment_scroll = self._scroll_for(self.comment_view, minimum_height=120)
            layout.pack_start(comment_scroll, True, True, 0)

            footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.add_status = Gtk.Label(
                label="Ctrl+Enter adds · Ctrl+L opens list · Ctrl+1/2 switches source"
            )
            self.add_status.set_halign(Gtk.Align.START)
            self.add_status.get_style_context().add_class("dim-label")
            footer.pack_start(self.add_status, True, True, 0)

            close = Gtk.Button(label="Close")
            close.connect("clicked", lambda _button: self.close())
            footer.pack_start(close, False, False, 0)

            save = Gtk.Button(label="Add to list")
            save.get_style_context().add_class("suggested-action")
            save.connect("clicked", self._add_annotation)
            footer.pack_start(save, False, False, 0)
            layout.pack_start(footer, False, False, 0)

        def _build_list_page(self):
            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            layout.set_border_width(14)
            self.notebook.append_page(layout, Gtk.Label(label="List"))

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = Gtk.Label()
            title.set_markup("<b>Continuous annotation list</b>")
            title.set_halign(Gtk.Align.START)
            header.pack_start(title, True, True, 0)
            sublime = Gtk.Button(label="Open in Sublime")
            sublime.connect("clicked", self._open_in_sublime)
            header.pack_start(sublime, False, False, 0)
            copy = Gtk.Button(label="Copy all")
            copy.connect("clicked", self._copy_all)
            header.pack_start(copy, False, False, 0)
            save = Gtk.Button(label="Save edits")
            save.get_style_context().add_class("suggested-action")
            save.connect("clicked", self._save_edits)
            header.pack_start(save, False, False, 0)
            layout.pack_start(header, False, False, 0)

            list_scroll = Gtk.ScrolledWindow()
            list_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            list_scroll.set_shadow_type(Gtk.ShadowType.IN)
            self.list_view = self._text_view()
            self.list_view.set_monospace(True)
            self.list_view.set_left_margin(14)
            self.list_view.set_right_margin(14)
            self.list_view.set_top_margin(12)
            self.list_view.set_bottom_margin(12)
            list_scroll.add(self.list_view)
            layout.pack_start(list_scroll, True, True, 0)

            footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.list_status = Gtk.Label(
                label="Timestamps are display-only · Ctrl+Enter saves · Ctrl+O opens Sublime"
            )
            self.list_status.set_halign(Gtk.Align.START)
            self.list_status.get_style_context().add_class("dim-label")
            footer.pack_start(self.list_status, True, True, 0)
            close = Gtk.Button(label="Close")
            close.connect("clicked", lambda _button: self.close())
            footer.pack_start(close, False, False, 0)
            layout.pack_start(footer, False, False, 0)

        def _buffer_text(self, view) -> str:
            buffer = view.get_buffer()
            return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

        def _candidate(self) -> TextCandidate:
            return candidates[self.candidate_picker.get_active()]

        def _candidate_changed(self, _picker=None):
            candidate = self._candidate()
            self.quote_view.get_buffer().set_text(candidate.text)
            self.source_label.set_text(annotation_source(candidate.label, source))

        def _add_annotation(self, _button=None) -> None:
            candidate = self._candidate()
            try:
                self.saved_path = save_comment(
                    quote=candidate.text,
                    comment=self._buffer_text(self.comment_view),
                    source=annotation_source(candidate.label, source),
                    directory=directory,
                )
            except ValueError:
                self.add_status.set_text("Write a comment before adding this entry.")
                self.comment_view.grab_focus()
                return
            _close_after_successful_add(self)

        def _reload_list(self):
            buffer = self.list_view.get_buffer()
            buffer.set_text("")
            self.entry_marks = []
            annotations = parse_annotation_list(load_annotation_list(directory))
            if not annotations:
                buffer.set_text("No annotations yet. Add one from the Add tab.")
                self.list_view.set_editable(False)
                return
            self.list_view.set_editable(True)
            for index, annotation in enumerate(annotations):
                if index:
                    buffer.insert(buffer.get_end_iter(), "\n")
                anchor = buffer.create_child_anchor(buffer.get_end_iter())
                metadata = Gtk.Label(
                    label=f"{annotation.captured_at:%Y-%m-%d %H:%M}  ·  {annotation.source}"
                )
                metadata.set_halign(Gtk.Align.START)
                metadata.set_selectable(False)
                metadata.get_style_context().add_class("dim-label")
                metadata.set_margin_top(5)
                metadata.set_margin_bottom(5)
                self.list_view.add_child_at_anchor(metadata, anchor)
                buffer.insert(buffer.get_end_iter(), "\n")

                start_mark, end_mark = _insert_marked_text(
                    buffer, render_editable_body(annotation).rstrip(), "\n"
                )
                self.entry_marks.append((annotation, start_mark, end_mark))
            self.list_view.show_all()

        def _edited_annotations(self) -> list[Annotation]:
            buffer = self.list_view.get_buffer()
            edited = []
            for original, start_mark, end_mark in self.entry_marks:
                start = buffer.get_iter_at_mark(start_mark)
                end = buffer.get_iter_at_mark(end_mark)
                edited.append(parse_editable_body(original, buffer.get_text(start, end, True)))
            return edited

        def _save_edits(self, _button=None):
            try:
                annotations = self._edited_annotations()
            except ValueError:
                self.list_status.set_text("Quotes and comments cannot be empty.")
                return
            self.saved_path = save_edited_annotations(annotations, directory)
            self.list_status.set_text("Edits saved.")
            return True

        def _copy_all(self, _button=None):
            try:
                annotations = self._edited_annotations()
            except ValueError:
                self.list_status.set_text("Fix empty quotes or comments before copying.")
                return
            text = "\n".join(render_editable_body(annotation) for annotation in annotations)
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            clipboard.store()
            self.list_status.set_text("Copied quotes and comments without timestamps.")

        def _open_in_sublime(self, _button=None):
            if not self._save_edits():
                return
            try:
                _launch_sublime(self.saved_path)
            except OSError:
                self.list_status.set_text("Could not launch Sublime Text with the subl command.")
                return
            self.close()

        def _on_key_press(self, _widget, event):
            if event.keyval == Gdk.KEY_Escape:
                self.close()
                return True
            if event.state & Gdk.ModifierType.CONTROL_MASK:
                if event.keyval in (Gdk.KEY_1, Gdk.KEY_2):
                    index = 0 if event.keyval == Gdk.KEY_1 else 1
                    if index < len(candidates):
                        self.candidate_picker.set_active(index)
                        self.notebook.set_current_page(0)
                        self.comment_view.grab_focus()
                    return True
                if (
                    self.notebook.get_current_page() == 1
                    and event.state & Gdk.ModifierType.SHIFT_MASK
                    and event.keyval in (Gdk.KEY_c, Gdk.KEY_C)
                ):
                    self._copy_all()
                    return True
            if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                if event.state & Gdk.ModifierType.CONTROL_MASK:
                    if self.notebook.get_current_page() == 0:
                        self._add_annotation()
                    else:
                        self._save_edits()
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
    candidates = capture_text_candidates()
    if not candidates:
        _show_no_selection_message()
        return 1

    directory = Path(os.environ.get("ANNOTATIONS_DIR", "~/Annotations")).expanduser()
    show_annotation_popup(candidates=candidates, source=source, directory=directory)
    return 0
