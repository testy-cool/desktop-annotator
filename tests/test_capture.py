import unittest

from desktop_annotator.capture import (
    COPY_RESPONSE_TIMEOUT,
    capture_selected_text,
    capture_text_candidates,
    copy_focused_selection,
)


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


class FakeDesktop:
    """A focused application that answers Ctrl+C after a scripted delay.

    ``responses`` are the clipboard values read after the keystroke, in order.
    ``None`` means the sentinel is still there, i.e. the application has not
    answered yet. The clock only advances when the code under test sleeps, so
    tests can assert on how long the wait would really have taken.
    """

    def __init__(self, responses, *, can_write=True):
        self.responses = list(responses)
        self.can_write = can_write
        self.writes = []
        self.keystrokes = 0
        self.now = 0.0

    def read(self):
        if not self.keystrokes:
            return "previous clipboard"
        value = self.responses.pop(0) if self.responses else None
        return self.writes[0] if value is None else value

    def write(self, text):
        if not self.can_write:
            return False
        self.writes.append(text)
        return True

    def press_copy(self):
        self.keystrokes += 1

    def sleep(self, seconds):
        self.now += seconds

    def monotonic(self):
        return self.now

    def run(self):
        return copy_focused_selection(
            clipboard_reader=self.read,
            clipboard_writer=self.write,
            key_sender=self.press_copy,
            sleep=self.sleep,
            monotonic=self.monotonic,
        )


class CopyFocusedSelectionTests(unittest.TestCase):
    def test_returns_as_soon_as_the_application_answers(self):
        desktop = FakeDesktop([None, None, "copied from Firefox"])

        self.assertEqual(desktop.run(), "copied from Firefox")
        self.assertLess(desktop.now, 0.05)

    def test_waits_no_longer_than_the_response_deadline(self):
        desktop = FakeDesktop([])

        self.assertEqual(desktop.run(), "")
        self.assertGreaterEqual(desktop.now, COPY_RESPONSE_TIMEOUT)
        self.assertLess(desktop.now, COPY_RESPONSE_TIMEOUT * 1.5)

    def test_keeps_waiting_through_a_transient_empty_read(self):
        desktop = FakeDesktop([None, "", "copied after a stumble"])

        self.assertEqual(desktop.run(), "copied after a stumble")

    def test_restores_the_previous_clipboard_afterwards(self):
        desktop = FakeDesktop([None, "copied text"])

        desktop.run()

        self.assertEqual(desktop.writes[-1], "previous clipboard")

    def test_gives_up_when_the_clipboard_cannot_be_primed(self):
        desktop = FakeDesktop(["copied text"], can_write=False)

        self.assertEqual(desktop.run(), "")
        self.assertEqual(desktop.keystrokes, 0)


if __name__ == "__main__":
    unittest.main()
