import unittest

from desktop_annotator.capture import capture_selected_text, capture_text_candidates


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


class CaptureTextCandidatesTests(unittest.TestCase):
    def test_offers_selection_and_clipboard_when_they_differ(self):
        candidates = capture_text_candidates(
            primary_reader=lambda: "selected in Firefox",
            clipboard_reader=lambda: "previously copied text",
            clipboard_copy=lambda: self.fail("fallback copy should not run"),
        )

        self.assertEqual(
            [(candidate.label, candidate.text) for candidate in candidates],
            [
                ("Selected text", "selected in Firefox"),
                ("Clipboard", "previously copied text"),
            ],
        )

    def test_deduplicates_matching_selection_and_clipboard(self):
        candidates = capture_text_candidates(
            primary_reader=lambda: "same text",
            clipboard_reader=lambda: " same text ",
            clipboard_copy=lambda: self.fail("fallback copy should not run"),
        )

        self.assertEqual([(item.label, item.text) for item in candidates], [("Selected text", "same text")])

    def test_keeps_live_clipboard_when_fallback_copies_a_different_selection(self):
        candidates = capture_text_candidates(
            primary_reader=lambda: "",
            clipboard_reader=lambda: "live clipboard",
            clipboard_copy=lambda: "selection copied from focused app",
        )

        self.assertEqual(
            [(candidate.label, candidate.text) for candidate in candidates],
            [
                ("Selected text", "selection copied from focused app"),
                ("Clipboard", "live clipboard"),
            ],
        )

    def test_uses_clipboard_when_no_selection_can_be_captured(self):
        candidates = capture_text_candidates(
            primary_reader=lambda: "",
            clipboard_reader=lambda: "live clipboard",
            clipboard_copy=lambda: "",
        )

        self.assertEqual([(item.label, item.text) for item in candidates], [("Clipboard", "live clipboard")])


if __name__ == "__main__":
    unittest.main()
