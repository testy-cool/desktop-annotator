import unittest

from desktop_annotator.app import _close_after_successful_add, _load_gtk, _show_list_page


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


if __name__ == "__main__":
    unittest.main()
