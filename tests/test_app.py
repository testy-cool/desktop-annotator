import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from desktop_annotator.app import (
    _apply_entry_background,
    _build_sublime_command,
    _close_after_successful_add,
    _configure_list_word_wrap,
    _connect_gutter_draw,
    _create_entry_background_tags,
    _draw_entry_gutters,
    _insert_marked_text,
    _insert_entry_separator,
    _install_toggle_close,
    _load_gtk,
    _move_popup_to_right_monitor,
    _open_list_in_sublime,
    _schedule_list_scroll_to_bottom,
    _scroll_text_view_to_bottom,
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


class PopupToggleTests(unittest.TestCase):
    def test_toggle_request_schedules_the_existing_window_to_close(self):
        class ToggleInstance:
            callback = None

            def set_toggle_callback(self, callback):
                self.callback = callback

        class Window:
            def close(self):
                pass

        toggle_instance = ToggleInstance()
        window = Window()
        scheduled = []

        close_already_requested = _install_toggle_close(
            toggle_instance,
            window,
            idle_add=lambda callback: scheduled.append(callback),
        )
        toggle_instance.callback()

        self.assertFalse(close_already_requested)
        self.assertEqual(scheduled, [window.close])


class AnnotationListPresentationTests(unittest.TestCase):
    def test_gutter_paint_runs_after_the_text_view_default_draw(self):
        class View:
            connection = None

            def connect_after(self, signal_name, callback):
                self.connection = (signal_name, callback)

        view = View()
        callback = object()

        _connect_gutter_draw(view, callback)

        self.assertEqual(view.connection, ("draw", callback))

    def test_row_background_paints_both_gutters_in_its_matching_color(self):
        class Rectangle:
            def __init__(self, y, height):
                self.y = y
                self.height = height

        class Buffer:
            def get_iter_at_mark(self, mark):
                return mark

        class View:
            def get_buffer(self):
                return Buffer()

            def get_iter_location(self, iterator):
                return Rectangle(y=iterator, height=10)

            def buffer_to_window_coords(self, _window_type, x, y):
                return x, y

            def get_allocated_width(self):
                return 200

        class Color:
            red = 0.5
            green = 0.5
            blue = 0.5
            alpha = 0.09

        class Tag:
            def get_property(self, _name):
                return Color()

        class Context:
            rectangles = []
            color = None

            def set_source_rgba(self, *color):
                self.color = color

            def rectangle(self, *rectangle):
                self.rectangles.append(rectangle)

            def fill(self):
                pass

        class Gtk:
            class TextWindowType:
                TEXT = object()

        context = Context()

        _draw_entry_gutters(
            View(), context, [(10, 30)], [Tag()], Gtk, gutter_width=14
        )

        self.assertEqual(context.color, (0.5, 0.5, 0.5, 0.09))
        self.assertEqual(context.rectangles, [(0, 10, 14, 30), (186, 10, 14, 30)])

    def test_list_wraps_at_word_boundaries_without_horizontal_scrolling(self):
        class Gtk:
            class WrapMode:
                WORD = object()

            class PolicyType:
                NEVER = object()
                AUTOMATIC = object()

        class View:
            wrap_mode = None
            left_margin = None
            right_margin = None

            def set_wrap_mode(self, wrap_mode):
                self.wrap_mode = wrap_mode

            def set_left_margin(self, margin):
                self.left_margin = margin

            def set_right_margin(self, margin):
                self.right_margin = margin

        class Scroll:
            policy = None

            def set_policy(self, horizontal, vertical):
                self.policy = (horizontal, vertical)

        view = View()
        scroll = Scroll()

        _configure_list_word_wrap(view, scroll, Gtk)

        horizontal_policy, vertical_policy = scroll.policy
        self.assertEqual(view.wrap_mode, Gtk.WrapMode.WORD)
        self.assertEqual(view.left_margin, 0)
        self.assertEqual(view.right_margin, 0)
        self.assertEqual(horizontal_policy, Gtk.PolicyType.NEVER)
        self.assertEqual(vertical_policy, Gtk.PolicyType.AUTOMATIC)

    def test_bottom_scroll_includes_the_text_views_bottom_margin(self):
        class Adjustment:
            value = None

            def get_upper(self):
                return 500

            def get_page_size(self):
                return 120

            def set_value(self, value):
                self.value = value

        class Buffer:
            mark = object()

            def get_end_iter(self):
                return object()

            def create_mark(self, *_args):
                return self.mark

            def delete_mark(self, _mark):
                pass

        class View:
            adjustment = Adjustment()
            buffer = Buffer()

            def get_buffer(self):
                return self.buffer

            def scroll_to_mark(self, *_args):
                pass

            def get_vadjustment(self):
                return self.adjustment

        view = View()

        _scroll_text_view_to_bottom(view)

        self.assertEqual(view.adjustment.value, 380)

    def test_opening_list_page_schedules_scroll_to_buffer_end(self):
        scheduled = []
        view = object()

        did_schedule = _schedule_list_scroll_to_bottom(
            page_number=1,
            list_view=view,
            idle_add=lambda callback, argument: scheduled.append((callback, argument)),
        )

        self.assertTrue(did_schedule)
        self.assertEqual(len(scheduled), 1)
        callback, argument = scheduled[0]
        self.assertIs(argument, view)
        self.assertEqual(callback.__name__, "_scroll_text_view_to_bottom")

    def test_non_list_page_does_not_schedule_scroll(self):
        scheduled = []

        did_schedule = _schedule_list_scroll_to_bottom(
            page_number=0,
            list_view=object(),
            idle_add=lambda *_args: scheduled.append(True),
        )

        self.assertFalse(did_schedule)
        self.assertEqual(scheduled, [])

    def test_alternating_entry_tags_have_different_subtle_backgrounds(self):
        Gdk, Gtk, _Pango = _load_gtk()
        buffer = Gtk.TextBuffer()

        first, second = _create_entry_background_tags(buffer, Gdk)

        first_color = first.get_property("paragraph-background-rgba")
        second_color = second.get_property("paragraph-background-rgba")
        self.assertNotEqual(first_color.alpha, second_color.alpha)
        self.assertLess(max(first_color.alpha, second_color.alpha), 0.15)

    def test_both_zebra_rows_have_full_width_background_and_inner_padding(self):
        Gdk, Gtk, _Pango = _load_gtk()
        buffer = Gtk.TextBuffer()

        first, second = _create_entry_background_tags(buffer, Gdk)

        self.assertGreater(first.get_property("paragraph-background-rgba").alpha, 0.0)
        self.assertGreater(second.get_property("paragraph-background-rgba").alpha, 0.0)
        for tag in (first, second):
            self.assertEqual(tag.get_property("left-margin"), 14)
            self.assertEqual(tag.get_property("right-margin"), 14)

    def test_entry_separator_contains_two_visually_empty_lines(self):
        _Gdk, Gtk, _Pango = _load_gtk()
        buffer = Gtk.TextBuffer()
        first_start, first_end = _insert_marked_text(buffer, "first", "")

        _insert_entry_separator(buffer, first_end)
        _insert_marked_text(buffer, "second", "")

        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        first_text = buffer.get_text(
            buffer.get_iter_at_mark(first_start), buffer.get_iter_at_mark(first_end), True
        )
        self.assertEqual(text, "first\n\n\nsecond")
        self.assertEqual(first_text, "first")

    def test_entry_background_is_applied_to_its_complete_buffer_range(self):
        _Gdk, Gtk, _Pango = _load_gtk()
        buffer = Gtk.TextBuffer()
        buffer.set_text("first entry\n\nsecond entry")
        tag = buffer.create_tag(None)

        _apply_entry_background(buffer, tag, start_offset=0, end_offset=12)

        self.assertIn(tag, buffer.get_iter_at_offset(2).get_tags())
        self.assertNotIn(tag, buffer.get_iter_at_offset(15).get_tags())


class SublimeDraftSafetyTests(unittest.TestCase):
    def test_safe_draft_is_saved_before_external_editor_opens(self):
        window = Mock()
        window._save_edits.return_value = True
        path = Path("/tmp/annotations.md")
        events = []
        window._save_edits.side_effect = lambda: events.append("save") or True
        with patch("desktop_annotator.app._launch_sublime", side_effect=lambda path: events.append("open")):
            _open_list_in_sublime(window, path)
        self.assertEqual(events, ["save", "open"])
        window.close.assert_called_once_with()

    def test_unsafe_draft_stays_open_while_external_file_can_be_repaired(self):
        window = Mock()
        window._save_edits.return_value = None
        path = Path("/tmp/annotations.md")
        with patch("desktop_annotator.app._launch_sublime") as launch:
            _open_list_in_sublime(window, path)
        launch.assert_called_once_with(path)
        window.close.assert_not_called()
        window.list_status.set_text.assert_not_called()

    def test_editor_launch_failure_leaves_the_annotator_open(self):
        window = Mock()
        window._save_edits.return_value = True
        with patch("desktop_annotator.app._launch_sublime", side_effect=OSError("unavailable")):
            _open_list_in_sublime(window, Path("/tmp/annotations.md"))
        window.close.assert_not_called()
        self.assertIn("Could not launch", window.list_status.set_text.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
