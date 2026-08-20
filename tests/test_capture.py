import unittest

from desktop_annotator.capture import capture_selected_text


class CaptureSelectedTextTests(unittest.TestCase):
    def test_prefers_the_x11_primary_selection(self):
        fallback_calls = []

        selected = capture_selected_text(
            primary_reader=lambda: "  selected in Firefox  ",
            clipboard_copy=lambda: fallback_calls.append(True) or "clipboard",
        )

        self.assertEqual(selected, "selected in Firefox")
        self.assertEqual(fallback_calls, [])

    def test_falls_back_to_copying_the_focused_application(self):
        selected = capture_selected_text(
            primary_reader=lambda: "\n",
            clipboard_copy=lambda: "  copied selection  ",
        )

        self.assertEqual(selected, "copied selection")

    def test_returns_empty_when_neither_capture_path_has_text(self):
        selected = capture_selected_text(
            primary_reader=lambda: "",
            clipboard_copy=lambda: "   ",
        )

        self.assertEqual(selected, "")


if __name__ == "__main__":
    unittest.main()
