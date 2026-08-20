import unittest
from pathlib import Path

from desktop_annotator.app import (
    _build_sublime_command,
    _close_after_successful_add,
    _insert_marked_text,
    _load_gtk,
    _move_popup_to_right_monitor,
    _show_list_page,
)


class GtkLoadingTests(unittest.TestCase):
    def test_loads_gdk_and_gtk_from_the_same_major_version(self):
        Gdk, Gtk, _Pango = _load_gtk()

        self.assertEqual(Gdk.MAJOR_VERSION, 3)
        self.assertEqual(Gtk.MAJOR_VERSION, 3)


class SuccessfulAddBehaviorTests(unittest.TestCase):
    def test_closes_the_capture_window_after_an_annotation_is_added(self):
        class RecordingWindow:
            closed = False

            def close(self):
                self.closed = True

        window = RecordingWindow()

        _close_after_successful_add(window)

        self.assertTrue(window.closed)

    def test_list_can_be_opened_on_demand(self):
        class RecordingNotebook:
            current_page = None

            def set_current_page(self, page):
                self.current_page = page

        notebook = RecordingNotebook()

        _show_list_page(notebook)

        self.assertEqual(notebook.current_page, 1)

    def test_builds_supported_sublime_file_command(self):
        path = Path("/tmp/annotations with spaces.md")

        command = _build_sublime_command(path)

        self.assertEqual(command, ["subl", "--", "/tmp/annotations with spaces.md"])

    def test_entry_marks_do_not_absorb_later_entries(self):
        _Gdk, Gtk, _Pango = _load_gtk()
        buffer = Gtk.TextBuffer()

        first_start, first_end = _insert_marked_text(buffer, "first entry", "\n\n")
        second_start, second_end = _insert_marked_text(buffer, "second entry", "\n")

        first_text = buffer.get_text(
            buffer.get_iter_at_mark(first_start), buffer.get_iter_at_mark(first_end), True
        )
        second_text = buffer.get_text(
            buffer.get_iter_at_mark(second_start), buffer.get_iter_at_mark(second_end), True
        )

        self.assertEqual(first_text, "first entry")
        self.assertEqual(second_text, "second entry")


class PopupPlacementTests(unittest.TestCase):
    def test_moves_popup_to_center_of_monitor_right_of_pointer_monitor(self):
        class Geometry:
            def __init__(self, x, y, width, height):
                self.x = x
                self.y = y
                self.width = width
                self.height = height

        class Monitor:
            def __init__(self, geometry):
                self.geometry = geometry

            def get_geometry(self):
                return self.geometry

        class Pointer:
            def get_position(self):
                return object(), 1200, 700

        class Seat:
            def get_pointer(self):
                return Pointer()

        class Display:
            monitors = [
                Monitor(Geometry(0, 0, 2560, 1440)),
                Monitor(Geometry(2560, 0, 1920, 1080)),
            ]

            def get_default_seat(self):
                return Seat()

            def get_n_monitors(self):
                return len(self.monitors)

            def get_monitor(self, index):
                return self.monitors[index]

        display = Display()

        class Gdk:
            class Display:
                @staticmethod
                def get_default():
                    return display

        class Window:
            position = None

            def move(self, x, y):
                self.position = (x, y)

        window = Window()

        moved = _move_popup_to_right_monitor(window, Gdk, width=720, height=620)

        self.assertTrue(moved)
        self.assertEqual(window.position, (3160, 230))


if __name__ == "__main__":
    unittest.main()
