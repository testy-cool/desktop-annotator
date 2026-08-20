import unittest

from desktop_annotator.app import _load_gtk


class GtkLoadingTests(unittest.TestCase):
    def test_loads_gdk_and_gtk_from_the_same_major_version(self):
        Gdk, Gtk, _Pango = _load_gtk()

        self.assertEqual(Gdk.MAJOR_VERSION, 3)
        self.assertEqual(Gtk.MAJOR_VERSION, 3)


if __name__ == "__main__":
    unittest.main()
